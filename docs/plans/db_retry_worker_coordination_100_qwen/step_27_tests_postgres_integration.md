# Step 27 - PostgreSQL integration contract tests

Previous: [Step 26](step_26_tests_sqlite_retry.md). Next: [Step 28](step_28_observations_document.md).

File: `tests/test_postgres_retry_contract_integration.py`

## Goal

Verify the PostgreSQL retry contract at integration level when a PostgreSQL test environment is available.

## Required tests

1. `test_postgres_config_missing_skips_with_explicit_reason`
   - If PostgreSQL test config is unavailable, skip PostgreSQL integration tests with an explicit reason.
   - Unit tests from [Step 20](step_20_tests_transient_errors.md) remain mandatory and must not be skipped by this condition.

2. `test_postgres_sqlstate_survives_to_transient_error`
   - If PostgreSQL is available, create a controlled retryable PostgreSQL error.
   - Verify SQLSTATE survives from PostgreSQL exception to `TransientDatabaseError`.
   - Verify `sqlstate`, `error_kind`, `retryable`, and `commit_outcome_unknown` are present.

3. `test_postgres_rpc_error_result_has_structured_details`
   - Run a controlled failing logical-write operation through the RPC handler path.
   - Verify `ErrorResult.data` contains `sqlstate`, `error_kind`, `retryable`, `attempts`, and `commit_outcome_unknown`.

4. `test_postgres_retry_log_has_required_fields`
   - Verify retry logs contain `[DB_RETRY]` with backend, layer, operation, attempt, SQLSTATE, and error kind.

5. `test_postgres_timeout_57014_policy`
   - If a controlled timeout scenario is available, verify SQLSTATE `57014` caused by configured timeout is retryable.
   - Verify manual/external cancel is not classified as retryable unless the classifier can prove it is timeout-related.

6. `test_postgres_external_transaction_not_retried_by_driver`
   - Operations with external `transaction_id` are not retried by driver-level code.
   - Logical-write retry, if applicable, happens only at RPC layer.

7. `test_postgres_commit_outcome_unknown_not_retried`
   - Unknown commit outcome is not retried blindly.
   - Structured details contain `commit_outcome_unknown=True` and `retryable=False`.

## Controlled scenario requirements

Use deterministic scenarios only:

- preferred: fake psycopg exception integration around real driver classification and retry code;
- acceptable: real controlled PostgreSQL transaction conflict that deterministically produces lock/deadlock/serialization behavior;
- forbidden: accidental timing-only deadlock tests.

## Forbidden

- Do not require destructive project operations.
- Do not use `vast_srv`.
- Do not make tests flaky by depending on accidental timing only.
- Do not parse raw text such as `deadlock detected` outside PostgreSQL classification code.
- Do not report skipped PostgreSQL integration tests as passed.

## Verification

Run this test file or confirm it is skipped with a clear reason. Record command, expected result, actual result, skip reason if any, and status in [Step 28 observations](step_28_observations_document.md).
