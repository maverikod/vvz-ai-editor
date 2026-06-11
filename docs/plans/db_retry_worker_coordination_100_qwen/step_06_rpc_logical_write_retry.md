# Step 06 - RPC logical write retry

Previous: [Step 05](step_05_postgres_driver_retry.md). Next: [Step 07](step_07_rpc_base_structured_errors.md).

Primary file: `code_analysis/core/database_driver_pkg/rpc_handlers_schema.py`

Related files that may need small changes:

- `code_analysis/core/database/logical_write_program.py`
- `code_analysis/core/database/logical_write_submit.py`
- `code_analysis/core/database_client/client_operations.py`

## Goal

Retry the whole logical write transaction, never an individual SQL statement or one `execute_batch` call inside a failed transaction attempt.

## Required changes

1. Rewrite `handle_execute_logical_write_operation()` as a retry loop around the whole transaction.
2. Read metadata from RPC params:
   - `operation_name: str | None`
   - `project_id: str | None`
   - `lock_scope: str`
3. Defaults: `operation_name=None`, `project_id=None`, `lock_scope="none"`.
4. Allowed `lock_scope` values in this step are exactly `"none"`, `"project_write"`, and `"project_read"`. This step only forwards/logs the value. It must not implement project lock acquisition.
5. For each attempt, execute the full sequence from the beginning:
   - `begin_transaction()`
   - optional deferred constraints setup, preserving existing behavior
   - every batch in original order
   - `commit_transaction()`
   - success response
6. On `TransientDatabaseError` with `retryable=True` and `commit_outcome_unknown=False`, rollback best-effort, log `[DB_RETRY]`, sleep by [Step 04](step_04_shared_retry_policy.md), then repeat the full sequence from `begin_transaction()`.
7. On exhausted attempts, return `ErrorResult(error_code=DATABASE_ERROR, description=str(e), data=e.to_details(operation_name, attempts))`.
8. On `commit_outcome_unknown=true`, rollback best-effort, do not retry, and return structured error data with `retryable=false` and `commit_outcome_unknown=true`.
9. Rollback failure after a transient error must be recorded in logs and must stop retrying if transaction cleanup cannot be guaranteed.

## Log format

```text
[DB_RETRY] backend=<driver> layer=rpc operation=execute_logical_write_operation operation_name=<name> attempt=<current>/<max> sqlstate=<sqlstate> error_kind=<error_kind>
```

## Forbidden

- No watcher-specific names in RPC code.
- No project activity lock acquisition in this step.
- No retry of a single `execute_batch` inside one transaction attempt.
- No blind retry after unknown commit outcome.
- No filesystem or network side effects inside the retried transaction loop.

## Verification

Fake-driver test must prove all of the following:

1. First failed transaction is rolled back.
2. Second attempt starts with a new `begin_transaction()`.
3. Second attempt reruns all batches from the beginning and in original order.
4. Commit-unknown failure is not retried.
5. Exhausted attempts return structured details.
6. `operation_name` appears in `[DB_RETRY]` log when metadata is supplied.

Record command, expected result, actual result, and status in [Step 28](step_28_observations_document.md).
