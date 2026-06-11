# Step 14 - Watcher coordination

Previous: [Step 13](step_13_worker_activity_coordinator.md). Next: [Step 15](step_15_ignore_purge_metadata.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md).

File: `code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py`

## Goal

Prevent watcher from mutating a project currently owned by indexer, auto-indexing, a mutating command, or another watcher, without blocking unrelated projects.

## Current source fact

`scan_watch_dir()` currently discovers all projects under a watched directory, calls `scan_directory(...)` once for the whole `watch_dir`, computes per-project deltas, and then queues changes. The existing `LockManager` must remain as the watch-dir process guard.

## Mandatory strategy

Use this strategy only:

1. Keep project discovery and filesystem scanning read-only with respect to per-project DB mutation state.
2. Do not acquire a project activity lease for the whole watch-dir scan.
3. After the scan produces per-project data, process DB mutation phases one `project_id` at a time.
4. Acquire a project activity lease only for the currently mutated `project_id`.
5. Release that project lease before moving to the next project.
6. If the lease cannot be acquired for one project, skip only that project for the current cycle and continue with other projects.

This step must not implement an all-project lease and must not serialize the whole watch-dir cycle behind one project lock.

## Required changes

1. Import coordinator API from [Step 13](step_13_worker_activity_coordinator.md).
2. Generate a stable watcher `owner_id` for the process/cycle, for example `watcher:<pid>:<cycle_id>`.
3. Ensure pure filesystem scan code does not write `files`, `chunks`, indexing flags, vector state, or project metadata.
4. Before each per-project DB write phase, acquire project activity with `owner_type="watcher"` and one precise activity:
   - `watcher_staging`
   - `watcher_inserting_new_files`
   - `watcher_updating_changed_files`
   - `watcher_marking_deleted_files`
   - `watcher_queueing`
5. If acquire fails, skip that `project_id` for the current cycle and do not mutate its DB rows.
6. Release in `finally` for every acquired project lease.
7. Heartbeat during long staging, insert, update, delete, and queue phases.
8. Remove uncoordinated watcher-launched auto-indexing. Newly auto-created projects must be marked/enqueued for the normal indexer path instead of starting a daemon indexing thread from watcher.
9. Preserve existing ignore and ignore-exception behavior when building the staged candidate set.
10. Replace or validate direct watcher SQL that uses backend-specific placeholders or `julianday('now')`; PostgreSQL behavior must be verified.

## Watcher write order

For each coordinated project mutation flow, execute phases in this exact order:

1. Build staged candidate set from filesystem paths that pass ignore rules and ignore exceptions.
2. Insert new file rows using backend-aware insert-from-staging or anti-join logic.
3. Update changed file rows.
4. Mark/delete absent file rows.
5. Invalidate/delete chunks only for rows confirmed changed or deleted.

## Logging

On skip:

```text
[WORKER_COORD] watcher skip project_id=<id> reason=<activity> owner_type=<blocking_owner_type>
```

On acquire/release/heartbeat, use the Step 13 `[WORKER_COORD]` format.

## Forbidden

- No SQLSTATE parsing in watcher.
- No retry policy implementation in watcher.
- No direct manipulation of `project_activity_locks` outside the coordinator API.
- No global server-wide mutex for all projects.
- No all-project lease for an entire watch-dir cycle.
- No chunk deletion for rows not confirmed changed/deleted.
- No watcher daemon thread that mutates DB/index/chunk state without the normal indexer path.

## Verification

Run tests from [Step 25](step_25_tests_watcher_indexer_coordination.md) and MCP log check from [Step 32](step_32_mcp_worker_coordination.md).

Required proof:

1. Watcher does not mutate a project while indexer owns the same project lease.
2. A busy project does not stop watcher from processing other safe projects.
3. New files are inserted before changed/deleted rows are processed.
4. Ignore exceptions are honored in the staged candidate set.
5. Watcher no longer starts an uncoordinated auto-indexing daemon thread.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
