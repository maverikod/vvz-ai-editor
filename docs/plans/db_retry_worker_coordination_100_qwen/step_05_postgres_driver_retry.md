# Step 05 - PostgreSQL driver retry

Previous: [Step 04](step_04_shared_retry_policy.md). Next: [Step 06](step_06_rpc_logical_write_retry.md).

Primary file: `code_analysis/core/database_driver_pkg/drivers/postgres.py`

Execution-path files that may also need changes:

- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_transactions.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`

## Goal

Retry safe self-managed PostgreSQL operations while preserving transaction boundaries and structured transient details.

## Required changes

1. In `PostgreSQLDriver.connect(config)`, create one `RetryPolicy` from [Step 04](step_04_shared_retry_policy.md). Store it on the driver instance.
2. Read `lock_timeout_seconds` and `statement_timeout_seconds` only from canonical driver config fields and pass them to `PostgreSQLTransactionManager` from [Step 03](step_03_postgres_transaction_timeouts.md).
3. Add private helper `_sleep_before_retry(attempt_1based: int) -> None` that sleeps using the stored retry policy.
4. Add private helper `_run_self_managed_with_retry(operation_name: str, func)`.
5. `execute()` and `execute_batch()` must call `_run_self_managed_with_retry(...)` only when the operation is self-managed.
6. Self-managed means `transaction_id` is missing, empty, or exactly `"local"` according to the existing driver convention.
7. External transaction means any non-empty `transaction_id` other than `"local"`. External transaction operations must not be retried by the driver.
8. Retry only `TransientDatabaseError` where `retryable=True` and `commit_outcome_unknown=False`.
9. Before every retry, call rollback best-effort on the active connection used by the failed self-managed operation. If rollback fails, stop retrying and raise a structured non-retryable driver error with the rollback failure chained.
10. Keep existing reconnect-on-connection-lost behavior, but do not retry an operation after connection loss unless rollback/cleanup completed.
11. Exhausted retries must raise `TransientDatabaseError` with `attempts=<max_attempts>` and unchanged `sqlstate`, `error_kind`, and `commit_outcome_unknown` fields.
12. Do not add watcher/indexer/project-lock behavior in the PostgreSQL driver.

## Log format

Log each retry attempt exactly once before sleeping:

```text
[DB_RETRY] backend=postgres layer=driver operation=<execute|execute_batch> attempt=<current>/<max> sqlstate=<sqlstate> error_kind=<error_kind>
```

## Forbidden

- Do not retry operations inside external transaction IDs.
- Do not retry if `commit_outcome_unknown=true`.
- Do not add watcher/indexer-specific logic.
- Do not implement project activity locks in PostgreSQL driver code.

## Verification

Unit test or controlled fake error must prove all of the following:

1. `execute_batch()` retries a self-managed retryable transient error.
2. `execute()` retries a self-managed retryable transient error.
3. External `transaction_id` operations are not retried.
4. Rollback is attempted before retry.
5. No retry occurs for `commit_outcome_unknown=true`.
6. The `[DB_RETRY]` log line is emitted with required fields.

Record command, expected result, actual result, and status in [Step 28](step_28_observations_document.md).
