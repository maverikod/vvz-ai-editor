# Step 07 — RPC base structured errors

Previous: [Step 06](step_06_rpc_logical_write_retry.md). Next: [Step 08](step_08_logical_write_metadata_type.md).

File: `code_analysis/core/database_driver_pkg/rpc_handlers_base.py`

## Goal
Return structured transient error details for plain `execute` and `execute_batch` RPC calls.

## Required changes
1. In `handle_execute()`, catch `TransientDatabaseError` before generic exceptions.
2. In `handle_execute_batch()`, catch `TransientDatabaseError` before generic exceptions.
3. Return `ErrorResult` with:
   - `error_code=ErrorCode.DATABASE_ERROR`
   - `description=str(e)`
   - `data=e.to_details(attempts=e.attempts)`
4. For ordinary `DriverOperationError`, keep existing string description behavior but include minimal `data={"retryable": false, "error_kind": "non_retryable"}` if the result type supports data.

## Forbidden
- Do not add logical-write retry here. That belongs to [Step 06](step_06_rpc_logical_write_retry.md).
- Do not parse strings such as `deadlock detected`.
- Do not introduce watcher/indexer-specific fields.

## Verification
Add/execute a test or CST check confirming both handlers mention `TransientDatabaseError` and return details fields: `sqlstate`, `error_kind`, `retryable`, `attempts`, `commit_outcome_unknown`.
