# Step 14 — `code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py`

## Goal
Make `get_database_status` counters internally consistent, or explicitly document which counters are non-additive and why.

## Why this step exists
Current runtime status showed an inconsistent state:

```text
active files: 2053
indexed: 2052 / 2053 = 99.95%
needing_indexing: 15
```

If `indexed` and `needing_indexing` are intended to be complementary states, this is impossible. If they are not complementary, the command must expose clearer state names and documentation.

## Current code checked before this step
`code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py` currently defines:

```python
_WHERE_FILES_INDEXED = (
    "((needs_chunking = 0 OR needs_chunking IS NULL) OR "
    "EXISTS (SELECT 1 FROM ast_trees WHERE ast_trees.file_id = files.id))"
)
```

`files_indexed` uses this AST-aware predicate.

But `files_needing_indexing` currently uses:

```sql
AND needs_chunking = 1
```

That is not the inverse of `_WHERE_FILES_INDEXED`. It counts files that need chunking, not files that need structural indexing. This likely explains the runtime contradiction.

Also `files_needing_chunking` currently uses:

```sql
AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = files.id)
```

while `needing_chunking_sample` uses the same no-chunks predicate. This is a chunking backlog, not an indexing backlog.

## Exact file to edit
`code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py`

## Required code search before edits
Use MCP source search/read tools before editing:

```text
fulltext_search(query="_WHERE_FILES_INDEXED needs_chunking needing_indexing get_database_status_build")
fulltext_search(query="needing_indexing_sample needing_chunking_sample code_chunks ast_trees")
file_structure(file_path="code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py")
read_project_text_file(file_path="code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py", ...)
```

If exact `fulltext_search` returns no results, read the candidate file directly.

## Required investigation
1. List every counter in `build_status_ops` and the predicate used for it:
   - `total_files`
   - `deleted_files`
   - `active_files`
   - `files_indexed`
   - `files_needing_indexing`
   - `files_needing_chunking`
   - `files_with_chunks`
   - `total_chunks`
   - `vectorized_chunks`
   - `not_vectorized_chunks`
2. Decide the meaning of `indexed`:
   - structural AST indexed;
   - or fully chunked/vector-ready;
   - or legacy `needs_chunking cleared`.
3. Decide the meaning of `needing_indexing`:
   - files without structural AST;
   - files with stale mtime;
   - files where indexing failed;
   - or files with `needs_chunking = 1`.
4. Decide the meaning of `needing_chunking`:
   - files without code_chunks;
   - files with docstrings and no chunks;
   - files explicitly flagged for chunking;
   - or all files with no chunks even if not eligible.
5. Check whether ignored/non-allowlisted paths are filtered consistently using `_sql_path_ok_status(...)`.
6. Check whether project-level stats and global stats use the same semantics.

## Required fix direction
Do not hide the inconsistency by renaming only. First make predicates coherent.

Preferred state model:

```text
structural_indexed:
  active normal files with AST row or equivalent structural index marker.

needing_indexing:
  active normal files that do NOT satisfy structural_indexed.

chunked:
  active normal files with at least one code_chunks row.

needing_chunking:
  active normal files eligible for chunking but without chunks, or explicitly documented as active normal files without chunks.
```

If `needing_chunking` intentionally includes files that are already structurally indexed, make that explicit in field names or documentation.

## Concrete likely change
Replace global `files_needing_indexing` query from:

```sql
AND needs_chunking = 1
```

to the inverse of `_WHERE_FILES_INDEXED`, for example:

```sql
AND NOT <_WHERE_FILES_INDEXED>
```

Also update `needing_indexing_sample` to use the same structural-indexing predicate, not `f.needs_chunking = 1`.

Do the same for project-level stats if project-level `needing_indexing` is added later.

## Required output fields
Keep existing fields for compatibility, but consider adding explicit new fields if needed:

```text
structural_indexed
needing_structural_indexing
chunked
needing_chunking
```

If new fields are added, keep old fields as aliases for one release and document the alias.

## Must not do
- Do not change watcher/indexer behavior in this step.
- Do not change chunk creation logic in this step.
- Do not change schema in this step.
- Do not remove ignore filtering from status aggregates.
- Do not make `needing_indexing` mean `needs_chunking` without documenting it.

## Tests to add/update
Create or update status tests:

1. File with no AST and no chunks:
   - counted as `needing_indexing`.
2. File with AST but no chunks:
   - counted as `indexed` / `structural_indexed`;
   - not counted as `needing_indexing`;
   - may be counted as `needing_chunking` depending on chosen semantics.
3. File with chunks:
   - counted as `chunked`.
4. Ignored `.venv` non-allowlisted file:
   - excluded from normal aggregates.
5. Runtime invariant test:
   - `active_normal_files = indexed + needing_indexing` if no explicit failed/other states are modeled;
   - otherwise explicit `other_state` counter must explain the difference.

Suggested files:
- `tests/test_get_database_status_ops_dialect.py`
- `tests/test_get_database_status_ignored_paths.py`
- new `tests/test_get_database_status_counter_consistency.py`

## Runtime verification
After restart:

```text
get_database_status
```

Expected examples:

```text
active: N
indexed + needing_indexing == active
```

or, if additional states exist:

```text
indexed + needing_indexing + failed_or_other == active
```

Also verify:

```text
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- no new worker errors;
- chunking/vectorization continue.

## Bug report
Command:
`get_database_status`

Expected:
Status counters use consistent predicates. If `indexed` means structural-indexed, then `needing_indexing` is its inverse over active normal files, or differences are explained by explicit failed/other counters.

Actual:
Runtime showed `active=2053`, `indexed=2052`, but `needing_indexing=15`.

Error:
Behavioral/status inconsistency. No worker exception.

Root cause hypothesis:
`indexed` uses AST-aware `_WHERE_FILES_INDEXED`, while `needing_indexing` still uses `needs_chunking = 1`, which is a chunking/vectorization backlog flag, not structural indexing backlog.

Fix:
Align predicates and sample queries; add regression tests.

Post-fix verification:
`get_database_status` counters must be internally consistent or explicitly non-additive with documented fields.

Status:
Open.

## References
- Index: `00-index.md`
- Vectorization cycle: `11-code_analysis_core_vectorization_worker_pkg_processing_cycle_projects.md`
- Ignore policy: `04-code_analysis_core_project_ignore_policy.md`
- Schema map: `schema_identity_map.md`
