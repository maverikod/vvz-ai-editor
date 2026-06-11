# Step 08 — Logical write metadata type

Previous: [Step 07](step_07_rpc_base_structured_errors.md). Next: [Step 09](step_09_client_metadata_forwarding.md).

File: `code_analysis/core/database/logical_write_program.py`

Goal: extend logical write programs with neutral metadata used by RPC logging and future lock scopes.

Required changes:
1. Import `Literal` from `typing`.
2. Extend `LogicalWriteProgramV1(TypedDict, total=False)` with optional fields: `operation_name: str`, `project_id: str`, `lock_scope: Literal["none", "project_write", "project_read"]`.
3. Keep `batches` and `defer_constraints` unchanged.
4. Missing metadata must preserve old behavior. Treat missing `lock_scope` as `"none"`.

Forbidden: do not change the `batches` structure. Do not add retry or DB logic here.

Verification: use CST/read command to confirm the three fields are present and existing imports still work.
