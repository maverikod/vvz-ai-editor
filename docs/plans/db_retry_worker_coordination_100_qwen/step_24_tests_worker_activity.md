# Step 24 - Worker activity tests

Previous: [Step 23](step_23_tests_logical_write_metadata.md). Next: [Step 25](step_25_tests_watcher_indexer_coordination.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md) and [Step 13](step_13_worker_activity_coordinator.md).

File: `tests/test_worker_project_activity.py`

## Goal

Prove the project-scoped activity coordinator is race-safe, backend-compatible, validates owner/activity values, and does not globally serialize unrelated projects.

## Test scope

Tests must exercise `code_analysis/core/worker_project_activity.py` through a real database object or the real database abstraction used by production code. Pure in-memory mocks are allowed only for narrow validation tests; they are not sufficient for atomicity or backend behavior.

## Required SQLite tests

1. `test_acquire_empty_project_lock_succeeds`
   - Given no existing activity row for `project_id=A`.
   - When owner `watcher:w1` acquires lease with `activity=watcher_staging`.
   - Then acquire returns `True` and `get_project_activity(A)` returns owner, activity, `heartbeat_at`, and future `lease_until`.

2. `test_same_owner_can_refresh_lease`
   - Given owner `watcher:w1` holds project `A`.
   - When the same owner heartbeats with `activity=watcher_inserting_new_files`.
   - Then heartbeat returns `True`, `lease_until` increases, and only one row exists for project `A`.

3. `test_foreign_owner_same_project_is_blocked`
   - Given owner `watcher:w1` holds project `A` with a non-expired lease.
   - When owner `indexer:i1` attempts to acquire project `A`.
   - Then acquire returns `False` and current owner remains `watcher:w1`.

4. `test_expired_lease_can_be_taken_over`
   - Given owner `watcher:w1` holds project `A` with expired `lease_until`.
   - When owner `indexer:i1` acquires project `A`.
   - Then acquire returns `True` and current owner becomes `indexer:i1`.

5. `test_release_requires_same_owner`
   - Given owner `watcher:w1` holds project `A`.
   - When owner `indexer:i1` tries to release project `A`.
   - Then release returns `False` and current owner remains `watcher:w1`.

6. `test_owner_release_clears_or_removes_row`
   - Given owner `watcher:w1` holds project `A`.
   - When the same owner releases project `A`.
   - Then release returns `True` and `get_project_activity(A)` returns `None` or an explicitly inactive/expired row documented by the implementation.

7. `test_different_projects_are_not_globally_blocked`
   - Given owner `watcher:w1` holds project `A`.
   - When owner `indexer:i1` acquires project `B`.
   - Then acquire for `B` returns `True`.

8. `test_allowed_owner_type_and_activity_validation`
   - Invalid `owner_type` must raise `ValueError` or return a documented structured failure before DB mutation.
   - Invalid `activity` must raise `ValueError` or return a documented structured failure before DB mutation.
   - After each invalid call, `project_activity_locks` must remain unchanged.

9. `test_heartbeat_requires_current_owner`
   - Given owner `watcher:w1` holds project `A`.
   - When owner `watcher:w2` or `indexer:i1` heartbeats project `A`.
   - Then heartbeat returns `False` and lease values remain unchanged.

10. `test_atomic_acquire_race_same_project`
   - Use two database connections or two concurrent tasks/threads against the same SQLite test database.
   - Both owners attempt to acquire the same active `project_id`.
   - Exactly one acquire returns `True`.

## Required PostgreSQL tests

If PostgreSQL test configuration is available, run the same behavior tests against PostgreSQL.

If PostgreSQL test configuration is unavailable, skip PostgreSQL tests with an explicit skip reason. The SQLite tests remain mandatory and must pass.

## Row/block semantics assertions

The coordinator itself must not load, update, or delete `files`, `chunks`, vector tables, or project rows.

Add assertions or query checks proving:

1. Acquiring a project lease changes only `project_activity_locks`.
2. Heartbeat changes only `project_activity_locks`.
3. Release changes only `project_activity_locks`.
4. No test expects whole-project file/chunk locking as a coordinator side effect.

## Logging tests

Verify that acquire success, acquire busy, heartbeat success/failure, and release success/failure emit `[WORKER_COORD]` logs with:

- `project_id`
- `owner_type`
- `owner_id`
- `activity`
- `result`

## Forbidden

- Do not use destructive operations on `vast_srv`.
- Do not edit `.venv`, `venv`, `site-packages`, or installed packages.
- Do not rely only on in-memory mocks for atomicity proof.
- Do not mark PostgreSQL behavior as passed when it was skipped.

## Verification

Run the new test file directly and record the command output.

Then run a separate read/CST command to verify both the test file and `code_analysis/core/worker_project_activity.py` exist.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
