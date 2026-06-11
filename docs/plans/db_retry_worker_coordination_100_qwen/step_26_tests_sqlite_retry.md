# Step 26 - SQLite retry tests

Previous: [Step 25](step_25_tests_watcher_indexer_coordination.md). Next: [Step 27](step_27_tests_postgres_integration.md).

File: `tests/test_sqlite_retry_compatibility.py`

## Goal

Prove SQLite remains compatible with the new retry/error contract from [Step 17](step_17_sqlite_retry_compatibility.md).

## Required tests

1. `test_self_managed_database_locked_is_retried`
   - Given a self-managed SQLite write operation raises `database is locked` once and then succeeds.
   - Then the driver retries according to the shared retry policy.
   - Then rollback/cleanup is attempted before retry.

2. `test_self_managed_database_busy_is_retried`
   - Given a self-managed SQLite write operation raises `database is busy` once and then succeeds.
   - Then the driver retries according to the shared retry policy.
   - Then rollback/cleanup is attempted before retry.

3. `test_sqlite_transient_details_are_structured`
   - Structured transient details must contain:
     - `sqlstate=None`;
     - `error_kind=sqlite_locked` or `error_kind=sqlite_busy`;
     - `retryable=True`;
     - `commit_outcome_unknown=False`.

4. `test_sqlite_syntax_error_is_not_retryable`
   - Ordinary SQLite syntax error is not retried.
   - Structured details, if returned, must have `retryable=False`.

5. `test_sqlite_integrity_error_is_not_retryable`
   - SQLite integrity error is not retried.
   - Structured details, if returned, must have `retryable=False`.

6. `test_external_transaction_id_is_not_retried`
   - Operation with external `transaction_id` is not retried by driver-level SQLite code.

7. `test_commit_outcome_unknown_is_not_retried`
   - Commit failure that may have unknown outcome is not retried.
   - Structured details must have `commit_outcome_unknown=True` and `retryable=False`.

8. `test_retry_delay_uses_shared_policy`
   - Retry delay uses [Step 04](step_04_shared_retry_policy.md), not separate hardcoded config names.
   - Monkeypatch sleep so the test is deterministic.

9. `test_no_project_lock_or_advisory_lock_behavior_in_sqlite_driver`
   - SQLite retry implementation does not add advisory-lock, project-lock, watcher, or indexer behavior.

## Implementation notes

- Use fake connection/cursor or a temporary SQLite database.
- Keep tests deterministic by monkeypatching sleep.
- Test changes from [Step 17](step_17_sqlite_retry_compatibility.md).
- Do not require PostgreSQL for this file.

## Forbidden

- Do not edit `.venv`, `venv`, `site-packages`, or installed packages.
- Do not use `vast_srv`.
- Do not accept a test that only checks string output and not structured retry details.

## Verification

Run this test file and record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
