# Step 03 - PostgreSQL transaction timeouts

Previous: [Step 02](step_02_postgres_error_classification.md). Next: [Step 04](step_04_shared_retry_policy.md).

File: `code_analysis/core/database_driver_pkg/drivers/postgres_transactions.py`

## Goal

Apply configured PostgreSQL transaction timeouts at transaction start without hardcoded values.

## Required changes

1. Extend `PostgreSQLTransactionManager` constructor to accept `lock_timeout_seconds: float | None` and `statement_timeout_seconds: float | None`.
2. Store these values as private fields.
3. In `begin_transaction()`, after opening the transaction connection and before returning `transaction_id`, execute timeout setup on the transaction connection:
   - `SET LOCAL lock_timeout = '<milliseconds>ms'` when `lock_timeout_seconds > 0`.
   - `SET LOCAL statement_timeout = '<milliseconds>ms'` when `statement_timeout_seconds > 0`.
4. Convert seconds to integer milliseconds with `int(seconds * 1000)`.
5. Treat `None`, zero, and negative timeout values as unset in this file. Range validation belongs to [Step 10](step_10_config_validator.md).
6. If timeout setup fails, rollback and close the transaction connection, remove `transaction_id` from every internal transaction map, and raise a wrapped driver error preserving the original exception as the cause.
7. Do not add project-lock, advisory-lock, watcher, or indexer methods in this step.

## Forbidden

- Do not hardcode timeout values.
- Do not implement advisory-lock behavior.
- Do not add placeholder lock APIs.
- Do not call watcher/indexer code from this file.

## Verification

Use a CST/read command to verify timeout fields and both `SET LOCAL` statements are present. Run existing transaction tests if available. Record command, expected result, actual result, and status in [Step 28](step_28_observations_document.md).
