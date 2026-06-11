# Step 09 — Client metadata forwarding

Previous: [Step 08](step_08_logical_write_metadata_type.md). Next: [Step 10](step_10_config_validator.md).

File: `code_analysis/core/database_client/client_operations.py`

Goal: pass logical-write metadata to RPC without adding client-side retry.

Required changes:
1. In `execute_logical_write_operation()`, keep current `batches` conversion unchanged.
2. If present in `program`, forward `operation_name`, `project_id`, and `lock_scope` into `rpc_params`.
3. Validate only simple types: `operation_name` and `project_id` must be strings when present; `lock_scope` must be one of `none`, `project_write`, `project_read`.
4. Keep `defer_constraints` behavior unchanged.
5. Log `[CHAIN] client execute_logical_write_operation n_batches=<n> operation_name=<name> project_id=<id>`.

Forbidden: do not add sleep, retry, SQLSTATE parsing, or watcher/indexer business logic in the client.

Verification: fake RPC client test or CST check must show metadata is included in params and invalid `lock_scope` raises `ValueError`.
