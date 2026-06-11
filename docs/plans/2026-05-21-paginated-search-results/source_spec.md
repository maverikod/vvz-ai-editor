# Paginated Search and Universal Tree Query Source Specification

## 1. Purpose and Scope

{zhp1} This plan defines changes to project search so that indexed search, direct file search, structural XPath-like filtering, paginated result storage, and preview integration use one consistent model.

{dsy4} The same search paging mechanism must support full-text search, semantic search, direct grep/text search, structural grep, project cross-search, and future XPath-like tree search.

## 2. Indexed and Dynamic Search Sources

{ulzd} The search system must support two paths for forming the initial result set. The first path uses the database/index when a file is already indexed and has not changed since indexing. The second path uses direct processing of project files when a file is missing from the database, stale in the database, newer on disk than in the index, or when the database/index is unavailable.

{5l14} Before executing a search, the system must build the list of files known to the database and the list of files present on disk. The intersection of those lists, after freshness validation, is the set of files that can be processed through the database/index. The difference between the disk file list and the fresh indexed set is the dynamic file set that must be processed directly from disk or from a draft session.

{vmo8} Freshness validation must use checksums and/or modification metadata. If a file is present in the database but its indexed checksum or modification state does not match the current file, that file must be removed from the indexed set and processed dynamically.

{jq0g} Files processed through the database must not be rescanned directly when their indexed state is current. Direct scanning exists to cover missing, stale, unindexed, draft, or unavailable-index cases. This prevents grep/direct search from duplicating full-text database search for unchanged indexed files.

## 3. Search Job Paging Model

{uj1g} Search result generation must not return one large unbounded response. Results must be grouped into result blocks written into a job result directory associated with a search job identifier (job_id). A result block is a bounded slice of the raw search output whose serialized size must not exceed the configured maximum block size in bytes. Block boundaries must fall between whole search results: a block always contains an integer number of complete results and never splits a single result across blocks. If a single result on its own exceeds the configured maximum block size, that result forms one block by itself and the size limit is exceeded for that block, because result integrity takes precedence over the size limit. The `search_start` command blocks until the directory index and the first result block are written to disk, then returns the job_id and a reference to the job result endpoint.

{4cv1} The job result directory must contain a directory index that lists every result block currently written for the job, in order, and an explicit completeness marker. The completeness marker must distinguish two states: search still running, meaning more blocks may appear, and search finished, meaning the listed blocks are final and no further blocks will be added. The index is the single mutable artifact of the job: when a new block is written, only the index is updated to append the new block entry, while previously written blocks remain immutable. Reading the endpoint with the job_id returns this index, giving the client immediate visibility of all available blocks and the current completeness state in one read.

{lann} After `search_start` returns, remaining result generation continues in the background. The client retrieves any block directly by its position number against the job result endpoint with the same job_id; random access to any already-listed block is allowed and no sequential traversal is required. To follow progress, the client re-reads the index: while the completeness marker reports search still running, new block entries may continue to appear and the client polls the index until either a needed block is listed or the marker reports search finished. When the marker reports search finished, the set of blocks listed in the index is final.

{pwy8} Tree-query results must participate in the same paging mechanism as other search sources. XPath-like search over a large set of files may produce early blocks while the remaining tree validation and node filtering continue in the background.

{g9xv} Result blocks must be produced by a buffered producer/assembler protocol so that the main search thread is never blocked by block sizing. The job result directory must contain a raw finding buffer, a dedicated accumulation subdirectory. On producing each finding the main search thread writes that finding to the buffer as one separate file, sets the manifest status to running, spawns a parallel block-assembler thread, and continues searching without waiting. The assembler thread, on entry, inspects a lock file in the buffer: if a valid lock held by a live owner process exists it exits immediately; if the lock is stale because its owner PID is no longer alive it reclaims the lock; otherwise it creates a lock file recording its own owner PID. Holding the lock, the assembler loops: it counts the findings currently in the buffer and reads the manifest status; if the status is not completed and the buffered volume is below the maximum block size, it releases the lock and exits; if the buffered volume reaches the maximum block size or the status is completed, it forms one result block of whole findings, atomically publishes the block into the job result directory, atomically appends the block entry to the directory index and updates the manifest, then deletes the assembled findings from the buffer. The assembler repeats this loop under the same lock until the buffer can no longer fill a block. When the manifest status is completed and the buffer is empty, the assembler sets the index completeness marker to search finished, deletes the raw finding buffer and the lock, and exits; the job result directory with its blocks and index is retained for the client and removed only later by the background job cleaner under TTL, never by the search itself. When the search yields no further findings, the main thread writes the final finding, sets the manifest status to completed, then runs the assembler one final time and waits for it to finish before exiting, so that no trailing findings are left unassembled.

## 4. Search Response Lifetime and Configuration

{xxer} Each job result directory must contain a service metadata file recording the last access time. Reading the directory index, any result block, or the search status for that job must update this last access time.

{oa6t} The system configuration must include two related settings. The first is a search response TTL setting that controls how long inactive job result directories live after last access. The second is a maximum result block size setting, expressed in bytes, that bounds the serialized size of a single result block. Each setting must have a code constant providing its default value. The configuration generator must emit both settings, and the configuration validator must reject missing, invalid, non-integer, zero, negative, or out-of-range values for each according to the declared policy. The maximum result block size is distinct from the existing per-result preview size limit: the preview limit bounds one rendered result, while the block size bounds a group of whole results assembled into one block.

## 5. Universal Tree Representation

{7qgh} File formats are divided into tree formats and text formats. Tree formats include JSON, YAML, Python CST, Markdown structure, and any other format represented as a tree. Text files must also be represented uniformly as trees: a text file is a set of paragraphs, and each paragraph is a set of lines.

{cgms} For every supported file, the system must create and maintain a tree file or tree sidecar that contains stable node identifiers comparable to the stable identifiers used by Python CST sidecars. The tree representation must be available for JSON, YAML, Python CST, Markdown, and text files.

{ygmh} Before any structural processing, the system must check whether the file tree exists and whether it is valid for the current file content. Tree validity must be checked using checksums, following the same principle used by CST sidecar validation. If the tree file does not exist or is not valid, it must be recreated before structural analysis proceeds.

{heid} The system must preserve stable node identity across indexer, database-backed search, dynamic search, and preview. If stable node identity cannot be guaranteed for a result, that result must not expose an unstable node identifier as preview-compatible.

## 6. XPath-like Filtering Across Sources

{41c7} XPath-like analysis must operate on the validated tree representation, not on ad-hoc text. After the tree is validated or recreated, the XPath-like engine filters the list of tree nodes and returns only matching nodes.

{om7b} XPath-like filtering is a universal structural filter, not a separate implementation per source. The same code must work with different sources: indexed database structural data, in-memory structures created by the indexer, dynamically created trees for files not yet processed by the indexer, and draft-session content.

{g9of} For files that are already in the database and still current, XPath-like filtering must be applied to the database-backed structural representation. For files that are stale or absent from the database, the same filtering code must be applied to the dynamically created tree. For files currently being processed by the indexer, the same filtering code must be usable with the indexer's in-memory structure before vectorization or database persistence.

{wgzg} The indexer must use the same tree construction and XPath-like filtering code as runtime search. The source of the tree may differ, but the structure model, node identifiers, and selector semantics must remain consistent.

{yr60} Dynamic file processing must use the same tree construction path as the indexer, excluding vectorization. Vectorization is a separate downstream phase and must not be required for tree creation, XPath filtering, direct dynamic search, or preview generation.

## 7. Preview-Compatible Result Nodes

{8c3h} Each node returned by XPath-like filtering must be representable through universal_file_preview. A result node must include enough information to call universal_file_preview with the relevant file path and node identifier or selector. For draft-session results, the preview reference must also include the session identifier.

{dim0} The universal_file_preview command is the canonical presentation mechanism for search result nodes. Search results should not invent a separate display model for nodes. They must return preview-compatible references and allow the client to inspect the node through universal_file_preview.

{olx9} Structural grep and XPath-like search must share the same tree model. Text grep may still exist as a standalone line search mode, but when grep participates in project cross-search as structural evidence, it must return nodes or blocks from the validated tree representation.

## 8. Dynamic Scanning Policy

{3454} By default, direct dynamic processing must scan only known supported formats. Broad CLI-like scanning of arbitrary files must be opt-in and must not include logs, virtual environments, build directories, or binary-like files unless explicitly allowed by policy.

{6fcd} fs_grep must support two explicit operating modes. The first mode is classic line grep, which returns line-oriented text matches and is suitable for direct standalone inspection. The second mode uses universal_file_preview-compatible structural representation: it validates or creates the file tree, maps matches to tree nodes or blocks, and returns preview-compatible node references or selectors. The preview-compatible structural mode must be the default mode. Classic line grep must be opt-in and must not be used as structural evidence inside project cross-search unless its results are converted to validated preview-compatible nodes.

## 9. Search Status, Timeout, and Cancellation

{5tnm} Search status must expose whether generation is running, completed, failed, cancelled, or timed out. It must also expose the current phase, such as indexed search, dynamic file discovery, tree validation, tree reconstruction, XPath filtering, block writing, or completion.

{ilmi} Hard timeout and cancellation rules must apply to dynamic scanning, tree reconstruction, XPath filtering, structural enrichment, and block generation. A timed-out dynamic or structural phase must not contribute partial invalid structural evidence.



## 10. Job Directory, Process Identity, and Cleanup

{hpqf} When a model or client starts a search, the server must immediately create a dedicated job result directory before search execution begins. The directory stores the job manifest, the directory index, result blocks, and service metadata for that search job.

{nyox} Job manifest data must include progress metrics derived from the running search context, such as produced result count, written block count, scanned file count, warning count, and error count.


{br58} Search result records are written progressively into result blocks by the running search process. Clients retrieve ready blocks through ordinary HTTP requests to the job result endpoint; the implementation must not require streaming transport for normal result inspection.

{6cni} Every successful HTTP access to the directory index, a result block, or the search status must refresh the job last-access timestamp. This timestamp controls inactivity-based TTL cleanup and is separate from the writer heartbeat timestamp.

{6diy} The job manifest must include the identity of the main server process that owns the job. At minimum this identity includes main_pid and process_start_time; host and instance_id may also be stored when available. If the main_pid no longer exists, or if the process_start_time does not match because the PID was reused, the job is dead or orphaned.


{ymk7} A running search must update a heartbeat timestamp in the job manifest. A running job whose heartbeat is older than the hard timeout must be treated as timed out or orphaned even if its last-access timestamp was recently refreshed.

{7u1o} A background job cleaner must periodically inspect job result directories and remove jobs that are expired, closed, completed beyond TTL, failed beyond TTL, cancelled beyond TTL, timed out beyond policy, or dead/orphaned by process identity and heartbeat checks. The cleaner must not delete a live running job whose process identity and heartbeat are valid.

{tuj9} The plan must extend existing working search behavior instead of replacing it.

{3crm} Current behavior remains the default for existing callers.

{ebj8} Paginated job-backed behavior is opt-in or exposed through compatible bridge commands.

{2w6w} Migration must preserve current validation, schemas, queue behavior, timeouts, direct payloads, structural results, and preview references.

{rn07} The implementation plan must mark each behavior as existing or new and must avoid duplicating working search logic.
