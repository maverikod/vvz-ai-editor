# Step 16 - Indexer coordination

Previous: [Step 15](step_15_ignore_purge_metadata.md). Next: [Step 17](step_17_sqlite_retry_compatibility.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md).

Files:

- indexing worker files that select and mutate files/chunks/indexing flags
- watcher auto-create path that currently starts auto-indexing
- helper module if needed to centralize indexer project lease handling

## Goal

Make indexer obey the same project-scoped mutation lease as watcher, while mutating only selected file rows and dependent chunk/vector state.

## Mandatory design decision

Watcher-launched daemon auto-indexing must be removed from the watcher mutation path. Newly auto-created projects must be marked or queued for the normal indexer path. Do not keep a separate watcher daemon thread that directly runs indexing work.

## Required behavior

1. Before mutating file indexing flags, chunks, vector state, or derived index data for a project, acquire the Step 13 project activity lease.
2. Use `owner_type="indexer"` for the normal indexer worker.
3. Use `activity="indexer_processing"`.
4. If acquire fails, skip that project for the current cycle. Do not wait indefinitely and do not mutate partial rows.
5. Release in `finally` for every acquired lease.
6. Heartbeat during long indexing, chunk, and vector phases.
7. Auto-created projects from watcher must enter this normal indexer path before any DB/index/chunk mutation.

## Row and logical-block write rule

The project lease prevents another worker from mutating the same project, but the indexer must still keep its write set narrow:

1. Select only file rows that need indexing or chunk/vector refresh.
2. Update only selected file rows.
3. Delete or rebuild only chunks and vector state for selected file rows.
4. Do not clear chunks for the whole project unless the command is an explicit whole-project rebuild and acquires a project lease with `activity="command_mutation"` or a separately documented full-project indexing activity.
5. Keep read-only analysis outside write transactions where possible.

## Auto-indexing migration requirement

1. Remove direct watcher daemon thread indexing.
2. Replace it with one of these concrete non-mutating watcher outputs:
   - set existing DB flags that the normal indexer already consumes; or
   - enqueue existing normal indexer work through the existing supported queue path.
3. The selected replacement must be documented in Step 28 observations with exact code path and verification command.
4. No `owner_type="auto_indexing"` production path should remain after this step. If compatibility code remains temporarily, it must be dead or test-only and must not mutate DB/index/chunk state.

## Backend and retry requirements

1. Do not implement transient DB retry logic in the indexer. Use the DB retry/RPC contract from previous steps.
2. Do not parse SQLSTATE in indexer code.
3. Do not use direct `project_activity_locks` SQL outside the coordinator API.
4. Do not put filesystem or network side effects inside retried DB transactions.

## Logging

Use Step 13 `[WORKER_COORD]` logging for acquire, skip, heartbeat, release, and release failure.

## Verification

Run [Step 25](step_25_tests_watcher_indexer_coordination.md) and [Step 32](step_32_mcp_worker_coordination.md).

Required proof:

1. Indexer skips or defers when watcher owns the same `project_id`.
2. Watcher skips or defers when indexer owns the same `project_id`.
3. Different projects are not globally blocked.
4. Indexer mutates only selected file rows and dependent chunks/vector state.
5. Watcher no longer launches an uncoordinated indexing daemon thread.
6. Auto-created projects are processed through the normal indexer path.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
