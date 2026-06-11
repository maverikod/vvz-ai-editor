
Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
-->

# Paginated cross-search: producer/assembler architecture

Working notes describing the structure and algorithm of the paginated
cross-search backend (`search_start search_type=cross paginated=true`).
Updated incrementally as each part lands.

## Goal

`search_start` must return fast (first result block ready) and never queue.
Results are written to the buffer as they are found, while heavier disk grep
continues in the background. Three concerns run concurrently:

- producer A — indexed search (semantic + fulltext), files already in the DB;
- producer B — disk grep, only files in the index gap (not indexed / changed);
- assembler C — drains the shared buffer into immutable result blocks.

## Components (reused, not reinvented)

- `RawFindingBuffer` (`core/search_session/raw_finding_buffer.py`) — one buffer
  directory; producers append findings, assembler drains them.
- `BlockAssembler` (`core/search_session/block_assembler.py`) — under a PID
  lock, packs findings into `block_N.json` up to `max_block_size_bytes`.
- `IndexCoverageService` (`core/index_coverage.py`) — splits candidate paths
  into indexed-unchanged vs index-gap via
  `filter_grep_candidates_with_reasons`.
- `is_supported_extension` (`core/structure_extraction/format_registry.py`) —
  extension prefilter so binary/generated files are skipped.

## Part 1 — atomic finding publish (DONE)

### Problem

Producers and the assembler share one buffer directory. If a producer is
mid-write on `finding.json` when the assembler lists and reads it, the
assembler can observe a partial (invalid) JSON file.

### Solution

`RawFindingBuffer.append_finding` publishes atomically:

1. write payload to `<finding_id>.json.tmp`;
2. `flush()` + `os.fsync()` the file descriptor;
3. `os.replace(<id>.json.tmp, <id>.json)` — atomic within one filesystem.

`list_findings()` filters on `suffix == ".json"`, so the `.tmp` sidecar is
invisible to the assembler until the rename completes. The assembler therefore
never sees a half-written finding. No lock is taken on the write path; the lock
remains assembler-only (one `run_once` cycle).

### Invariant

Writers never produce a visible `.json` that is not a complete finding.
Readers (assembler) act only on fully published `.json` files.

## Part 2 — prefilter + index-gap split (PENDING)

Planned: `list_project_files` by supported extensions →
`IndexCoverageService.filter_grep_candidates_with_reasons(skip_indexed_unchanged=True,
indexed_only=False)` → `indexed_paths` / `index_gap_paths`. `[TIMING] prefilter`.

## Part 3 — producer/assembler tasks (PENDING)

Planned: Task A (semantic+fulltext), Task B (grep over index-gap), Task C
(assembler loop). `search_start` polls for `block_1` then returns; A/B/C finish
in the background. `[TIMING]` at every phase boundary.
