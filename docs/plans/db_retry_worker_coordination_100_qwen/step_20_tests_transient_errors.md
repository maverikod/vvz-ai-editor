# Step 20 - Unit tests for transient errors

Previous: [Step 19](step_19_client_transient_fallback.md). Next: [Step 21](step_21_tests_rpc_logical_write_retry.md).

File: `tests/test_database_driver_transient_errors.py`

## Goal

Prove the structured transient error contract and PostgreSQL classification rules without requiring a live PostgreSQL server.

## Required tests

1. `test_deadlock_sqlstate_is_retryable`
   - Fake PostgreSQL exception with `sqlstate="40P01"`.
   - Expected: `error_kind="deadlock"`, `retryable=True`, `commit_outcome_unknown=False`.

2. `test_serialization_failure_sqlstate_is_retryable`
   - Fake PostgreSQL exception with `sqlstate="40001"`.
   - Expected: `error_kind="serialization_failure"`, `retryable=True`, `commit_outcome_unknown=False`.

3. `test_lock_not_available_sqlstate_is_retryable`
   - Fake PostgreSQL exception with `sqlstate="55P03"`.
   - Expected: `error_kind="lock_not_available"`, `retryable=True`, `commit_outcome_unknown=False`.

4. `test_query_canceled_timeout_is_retryable`
   - Fake PostgreSQL exception with `sqlstate="57014"` and message containing timeout text.
   - Expected: `error_kind="query_canceled"`, `retryable=True`.

5. `test_query_canceled_manual_cancel_is_not_retryable`
   - Fake PostgreSQL exception with `sqlstate="57014"` and message indicating manual or external cancel.
   - Expected: `error_kind="query_canceled"`, `retryable=False`.

6. `test_unknown_sqlstate_is_not_retryable`
   - Fake PostgreSQL exception with unknown SQLSTATE.
   - Expected: `error_kind="postgres_error"`, `retryable=False`.

7. `test_sqlstate_can_be_read_from_diag_fallback`
   - Fake PostgreSQL exception has no direct `.sqlstate`, but has `.diag.sqlstate`.
   - Expected: classifier uses the fallback value.

8. `test_transient_database_error_to_details_schema`
   - `TransientDatabaseError.to_details()` returns exactly the stable fields required by Step 01:
     - `sqlstate`
     - `error_kind`
     - `retryable`
     - `attempts`
     - `operation_name`
     - `commit_outcome_unknown`

9. `test_database_error_details_handles_transient_and_non_transient`
   - Transient errors return structured details.
   - Non-transient errors return `retryable=False` and a stable `error_kind`.

## Implementation notes

- Use fake exception objects with `sqlstate`, optional `diag.sqlstate`, and message fields.
- Do not require a live PostgreSQL server for these unit tests.
- Import classifier from [Step 02](step_02_postgres_error_classification.md).
- Do not inspect raw PostgreSQL text outside the classifier under test.

## Forbidden

- Do not require live PostgreSQL for this test file.
- Do not make tests depend on localized PostgreSQL error text except the timeout/manual-cancel examples required by Step 02.
- Do not accept string-only errors without structured fields.

## Verification

Run this test file and record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
