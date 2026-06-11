# Step 18 - Base driver compatibility

Previous: [Step 17](step_17_sqlite_retry_compatibility.md). Next: [Step 19](step_19_client_transient_fallback.md).

File: `code_analysis/core/database_driver_pkg/drivers/base.py`

## Goal

Keep the driver interface backward-compatible while documenting retry boundaries.

## Required changes

1. Add or update docstrings on existing base driver methods that execute SQL or transactions.
2. The docstrings must state:
   - driver-level retry is allowed only for self-managed operations without external `transaction_id`;
   - operations with external `transaction_id` must not be retried by the driver;
   - logical-write retry belongs to the RPC layer from [Step 06](step_06_rpc_logical_write_retry.md);
   - driver implementations must not retry when commit outcome is unknown.
3. Do not add advisory-lock methods, placeholder lock methods, project-lock methods, or watcher/indexer methods in the base driver.
4. Do not add PostgreSQL SQLSTATE mapping here. That belongs to [Step 02](step_02_postgres_error_classification.md).
5. If a signature change is unavoidable for retry policy propagation, update all concrete drivers in the same step and prove imports/type checks still pass. Prefer no signature changes.

## Forbidden

- No PostgreSQL-specific logic in the base driver.
- No watcher/indexer imports.
- No advisory-lock or project-activity-lock API in the base driver.
- No breaking abstract method signature changes unless all drivers are updated and tested in the same step.

## Verification

Run type/import tests and a read/CST check for updated docstrings. Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
