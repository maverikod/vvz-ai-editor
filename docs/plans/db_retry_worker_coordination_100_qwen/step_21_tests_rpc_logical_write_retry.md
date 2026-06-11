# Step 21 - Unit tests for logical write retry

Previous: [Step 20](step_20_tests_transient_errors.md). Next: [Step 22](step_22_tests_config_validator.md).

File: `tests/test_rpc_logical_write_retry.py`

## Goal

Prove RPC retries the whole logical write transaction and never retries only one SQL statement or one batch inside a failed transaction attempt.

## Required tests

1. `test_retry_replays_whole_transaction_from_beginning`
   - Fake driver attempt 1: `begin_transaction` succeeds; first or second `execute_batch` raises `TransientDatabaseError(sqlstate="40P01", error_kind="deadlock", retryable=True)`.
   - Verify rollback is called for attempt 1.
   - Fake driver attempt 2: a new `begin_transaction` is called.
   - Verify all batches execute again from the beginning and in original order.
   - Verify commit succeeds and response is success.

2. `test_retry_does_not_replay_only_failed_batch`
   - Use at least two batches.
   - Make attempt 1 fail on batch 2.
   - Verify attempt 2 executes batch 1 again before batch 2.

3. `test_commit_outcome_unknown_is_not_retried`
   - Fake driver raises `TransientDatabaseError(commit_outcome_unknown=True, retryable=False)` during commit.
   - Verify no second `begin_transaction` occurs.
   - Verify rollback best-effort is attempted.
   - Verify response data has `commit_outcome_unknown=True` and `retryable=False`.

4. `test_exhausted_attempts_returns_structured_details`
   - All attempts fail with retryable transient error.
   - Verify final response has `attempts=<max>` and structured details from Step 01.

5. `test_operation_name_is_forwarded_to_error_details_and_logs`
   - Supply `operation_name` metadata.
   - Verify final error details and `[DB_RETRY]` log include the operation name.

6. `test_project_id_and_lock_scope_are_metadata_only_in_this_step`
   - Supply `project_id` and `lock_scope` metadata.
   - Verify they are accepted/forwarded as metadata.
   - Verify this step does not acquire project activity locks.

7. `test_rollback_failure_stops_retry`
   - Fake rollback raises after a retryable transient error.
   - Verify no further transaction attempt occurs.
   - Verify response is structured failure, not false success.

## Implementation notes

- Use fake driver and handler instance. No real DB required.
- Reuse details contract from [Step 01](step_01_exceptions_contract.md).
- Retry policy source must be compatible with [Step 04](step_04_shared_retry_policy.md).
- Capture logs to assert `[DB_RETRY]` fields.

## Forbidden

- Do not require a live database.
- Do not implement or test project activity lock acquisition in this step.
- Do not accept a test that only verifies final success without verifying full transaction replay order.

## Verification

Run this test file and record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
