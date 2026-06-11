# Step 13 - Worker activity coordinator

Previous: [Step 12](step_12_activity_lock_migrations.md). Next: [Step 14](step_14_watcher_coordination.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md).

File: `code_analysis/core/worker_project_activity.py`

## Goal

Provide one race-safe project-scoped activity lease coordinator for watcher, indexer, and mutating command paths.

## Design rule

Do not serialize the whole server. Coordination is scoped by `project_id`.

At any moment, only one worker pipeline may mutate one `project_id`, but unrelated projects must be able to proceed independently.

The project lease is a high-level mutation ownership guard. Inside the lease, operations must still update only the rows or logical blocks they actually change.

## Public API

- `try_acquire_project_activity(database, project_id, owner_type, owner_id, activity, ttl_seconds) -> bool`
- `heartbeat_project_activity(database, project_id, owner_type, owner_id, activity, ttl_seconds) -> bool`
- `release_project_activity(database, project_id, owner_type, owner_id) -> bool`
- `get_project_activity(database, project_id) -> dict[str, Any] | None`

These APIs must use the table from [Step 11](step_11_schema_activity_locks.md) and must not expose raw SQL to watcher/indexer code.

## Owner and activity values

Allowed `owner_type` values are exactly:

- `watcher`
- `indexer`
- `command`

Allowed `activity` values are exactly:

- `watcher_staging`
- `watcher_inserting_new_files`
- `watcher_updating_changed_files`
- `watcher_marking_deleted_files`
- `watcher_queueing`
- `indexer_processing`
- `command_mutation`

`auto_indexing` is not an allowed production owner type. Step 16 removes watcher-launched daemon auto-indexing and routes auto-created projects through the normal indexer path.

## Lease rules

1. Acquire must be atomic.
2. Acquire succeeds if no row exists for `project_id`.
3. Acquire succeeds if an existing row for `project_id` has `lease_until < now`.
4. Acquire succeeds if the same `owner_type` and `owner_id` already own the row; in this case refresh `heartbeat_at`, `lease_until`, and `activity`.
5. Acquire returns `False` if a different active owner holds the same `project_id`.
6. Release returns `True` and removes or clears the row only when `owner_type` and `owner_id` match the current owner.
7. Release returns `False` and leaves the row unchanged when the caller is not the current owner.
8. Heartbeat returns `True` only for the current owner and extends `lease_until`.
9. Heartbeat returns `False` if the lease is absent, expired, or owned by another owner.
10. No API waits indefinitely. Waiting/retry loops are forbidden in the coordinator.
11. The existing watcher `LockManager` remains a watch-dir process guard and is not replaced by this API.

## Time source

Use application-side Unix epoch seconds from `time.time()` for `acquired_at`, `heartbeat_at`, and `lease_until`. Do not rely on backend-specific time functions for canonical lease values.

## Row and logical-block write rule

The coordinator grants project-level mutation permission only. It does not mean every table row for the project is held for the whole operation.

Callers must keep write sets narrow:

1. For new files, insert only missing `files` rows for the current staged candidate set.
2. For changed files, update only rows whose metadata or content state changed.
3. For deleted files, update only rows present in DB and absent from the staged candidate set.
4. For indexer work, update only file rows selected for indexing and dependent chunks/vector state.
5. Do not delete or invalidate chunks for rows that were not confirmed changed or deleted.

## Backend implementation requirements

1. Implement both SQLite and PostgreSQL behavior.
2. Backend-specific SQL must be isolated inside `worker_project_activity.py` or a storage-layer helper called only by this module.
3. PostgreSQL path must use an atomic `INSERT ... ON CONFLICT ... WHERE lease_until < now OR owner matches` style operation or an equivalent transactionally atomic update/insert sequence.
4. SQLite path must use an atomic transaction with conditional insert/update semantics that prevents two owners from acquiring the same active project.
5. Do not use PostgreSQL advisory locks in this plan.
6. Do not put filesystem side effects inside retried DB write blocks.

## Logging

On acquire success, acquire busy, heartbeat success/failure, release success/failure, log with prefix `[WORKER_COORD]`.

Minimum fields:

- `project_id`
- `owner_type`
- `owner_id`
- `activity`
- `result`

For busy/skip, include current owner fields if they can be read without waiting.

## Verification

Run [Step 24](step_24_tests_worker_activity.md).

Required proof:

1. Same project cannot be acquired by two active owners concurrently.
2. The same owner can heartbeat and refresh its own lease.
3. Expired lease can be acquired by another owner.
4. Different `project_id` values are not globally serialized.
5. Release by a different owner fails and does not clear the row.
6. Invalid `owner_type` and invalid `activity` are rejected before DB mutation.
7. SQLite and PostgreSQL paths pass the same behavior tests.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
