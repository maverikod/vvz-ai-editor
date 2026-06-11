# Step 25 - Watcher/indexer coordination tests

Previous: [Step 24](step_24_tests_worker_activity.md). Next: [Step 26](step_26_tests_sqlite_retry.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md), [Step 14](step_14_watcher_coordination.md), [Step 15](step_15_ignore_purge_metadata.md), and [Step 16](step_16_indexer_coordination.md).

File: `tests/test_watcher_indexer_project_coordination.py`

## Goal

Prove watcher and indexer obey project-scoped coordination, preserve watcher write ordering, route auto-created projects through the normal indexer path, and do not globally block unrelated projects.

## Test data requirements

Use test projects only. Do not use `vast_srv`.

Each test must use at least two project IDs when proving non-global behavior:

- project `A`: busy/blocked project;
- project `B`: unrelated project that must continue.

## Required test group 1 - same-project mutation exclusion

1. `test_indexer_skips_project_owned_by_watcher`
   - Given watcher owns project `A` with a non-expired lease.
   - When indexer attempts to process project `A`.
   - Then indexer skips/defer project `A`.
   - Then file rows, chunks, vectors, and indexing flags for project `A` are unchanged.

2. `test_watcher_skips_project_owned_by_indexer`
   - Given indexer owns project `A` with a non-expired lease.
   - When watcher attempts `watcher_staging`, `watcher_inserting_new_files`, `watcher_updating_changed_files`, or `watcher_marking_deleted_files` for project `A`.
   - Then watcher skips project `A`.
   - Then DB rows for project `A` are unchanged.

3. `test_mutating_command_owner_blocks_watcher_and_indexer`
   - Given owner type `command` owns project `A` with `activity=command_mutation`.
   - Then watcher and indexer both skip/defer project `A`.

## Required test group 2 - different projects are not globally blocked

1. `test_watcher_owned_project_does_not_block_indexer_on_other_project`
   - Given watcher owns project `A`.
   - When indexer processes project `B`.
   - Then project `B` processing proceeds and mutates only project `B` rows.

2. `test_indexer_owned_project_does_not_block_watcher_on_other_project`
   - Given indexer owns project `A`.
   - When watcher processes project `B`.
   - Then project `B` watcher flow proceeds and mutates only project `B` rows.

3. `test_busy_project_does_not_stop_whole_watch_dir_cycle`
   - Given one discovered project is busy and another discovered project is free.
   - When watcher runs one cycle.
   - Then watcher skips only the busy project and still processes the free project.

## Required test group 3 - watcher staged candidate set

1. Filesystem scan results are converted into a staged candidate set per `project_id`.
2. Candidate paths are normalized to project-relative POSIX paths.
3. Paths outside the target project root are rejected before staging.
4. Ignore patterns are applied before DB mutation.
5. Ignore-exception patterns are applied after ignore patterns and can re-include matching paths.
6. Staging is transaction-local or identified by `scan_cycle_id` and cannot leak stale rows into a later cycle.

## Required test group 4 - watcher write ordering

1. New file rows are inserted before changed rows are updated.
2. New file rows are inserted before absent rows are marked/deleted.
3. Existing unchanged rows are not updated.
4. Changed rows update only their own file metadata/indexing flags.
5. Deleted/absent rows are marked/deleted only after the staged candidate set is available.
6. Chunks are invalidated/deleted only for rows confirmed as changed or deleted.
7. Watcher never mutates rows for a project whose lease was not acquired.

## Required test group 5 - idempotency and retry safety

1. Re-running the same watcher logical write after a transient retry does not duplicate file rows.
2. Re-running the same watcher logical write does not delete active files.
3. Re-running the same watcher logical write does not invalidate chunks for unchanged files.
4. Unknown commit outcome is not retried blindly and returns structured error from earlier retry-contract steps.

## Required test group 6 - backend equivalence

Run equivalent staging/insert/update/delete behavior tests for SQLite and PostgreSQL paths when PostgreSQL test configuration is available.

If PostgreSQL test configuration is unavailable, skip PostgreSQL-specific tests with explicit reason. SQLite tests remain mandatory.

Required assertions:

1. PostgreSQL path does not use SQLite-only constructs such as `julianday('now')` directly.
2. SQLite path does not use PostgreSQL-only syntax unless hidden behind a backend-specific helper.
3. Placeholder handling is correct for both backends through the selected DB abstraction.

## Required test group 7 - auto-created project indexing path

Watcher-launched daemon auto-indexing must not remain as an active mutation path.

Test cases:

1. When watcher auto-creates a project, it must not start a daemon thread that directly runs `UpdateIndexesMCPCommand`.
2. The auto-created project must be marked or queued for the normal indexer path.
3. The normal indexer path must acquire `owner_type=indexer` and `activity=indexer_processing` before mutating files/chunks/index/vector state.
4. No production mutation path should use `owner_type=auto_indexing`.

## Logging assertions

Capture logs and verify `[WORKER_COORD]` records for acquire, skip, heartbeat, and release paths.

Skip log must include:

```text
[WORKER_COORD] watcher skip project_id=<id> reason=<activity> owner_type=<blocking_owner_type>
```

Indexer skip logs must include `project_id`, `owner_type=indexer`, `activity=indexer_processing`, and blocking owner fields when available.

## Forbidden

- Do not use destructive operations on `vast_srv`.
- Do not edit `.venv`, `venv`, `site-packages`, or installed packages.
- Do not fake success only through queue job completion; inspect command result success fields where MCP/queue is used.
- Do not keep tests that pass while watcher daemon auto-indexing still mutates DB/index/chunk state directly.

## Verification

Run this test file directly and record output.

Then verify via a separate read/CST command that the test file and source changes exist.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
