# Step 17 - SQLite retry compatibility

Previous: [Step 16](step_16_indexer_coordination.md). Next: [Step 18](step_18_base_driver_compatibility.md).

File: `code_analysis/core/database_driver_pkg/drivers/sqlite.py`

## Goal

Keep SQLite compatible with the new retry/error contract without PostgreSQL-specific behavior.

## Required changes

1. Use the shared retry policy from [Step 04](step_04_shared_retry_policy.md) only for SQLite self-managed write operations.
2. Self-managed means no external `transaction_id`, matching the current SQLite driver convention.
3. Operations with external `transaction_id` must not be retried by driver-level SQLite code.
4. Retry only SQLite transient busy/locked cases:
   - exception message contains `database is locked`;
   - exception message contains `database is busy`;
   - SQLite busy/locked error codes if the current driver exposes them.
5. Structured details for SQLite transient errors must be:
   - `sqlstate=None`;
   - `error_kind="sqlite_locked"` or `error_kind="sqlite_busy"`;
   - `retryable=True`;
   - `commit_outcome_unknown=False` unless a commit failure makes the outcome unknown.
6. If commit outcome may be unknown, do not retry and return/raise structured details with `commit_outcome_unknown=True` and `retryable=False`.
7. Before every retry, rollback/cleanup the failed self-managed operation best-effort. If cleanup cannot be guaranteed, stop retrying.
8. Do not implement advisory-lock, project-lock, or watcher/indexer behavior in SQLite driver code.

## Forbidden

- No PostgreSQL SQLSTATE in SQLite code.
- No PostgreSQL-specific SQL.
- No retry around filesystem operations.
- No advisory-lock placeholder implementation.
- No project activity lock implementation in this driver.

## Verification

Run [Step 26](step_26_tests_sqlite_retry.md). Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
