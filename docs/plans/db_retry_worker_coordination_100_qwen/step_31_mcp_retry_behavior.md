# Step 31 - MCP retry behavior check

Previous: [Step 30](step_30_mcp_smoke_regression.md). Next: [Step 32](step_32_mcp_worker_coordination.md).

## Goal

Prove retry behavior through MCP, not only through unit tests.

## Required controlled scenario

Use exactly one deterministic transient scenario through an MCP command path:

1. Preferred: test-only MCP hook command that raises a retryable `TransientDatabaseError` once and then succeeds.
2. Acceptable: deterministic integration MCP command that exercises logical-write retry with a fake or controlled driver.
3. Acceptable only when stable: isolated temporary project with controlled PostgreSQL lock conflict.
4. Forbidden: accidental timing-only deadlock or lock-conflict scenario.

## Required behavior checks

1. Run the controlled scenario through MCP, not direct Python inspection.
2. Verify one of these outcomes:
   - operation succeeds after retry; or
   - operation returns structured error after exhausted attempts.
3. Verify returned data includes structured retry fields when an error is returned:
   - `sqlstate`
   - `error_kind`
   - `retryable`
   - `attempts`
   - `commit_outcome_unknown`
4. Verify `commit_outcome_unknown=True` is never retried and is returned with `retryable=False` when that scenario is tested.
5. Verify logical write retry includes `operation_name` when metadata is supplied.
6. Verify external `transaction_id` operations are not retried by driver-level code.

## Required log checks

Use a separate log-viewer MCP command after the behavior command.

Logs must contain `[DB_RETRY]` with:

- `backend`
- `layer`
- `operation`
- `attempt`
- `sqlstate`
- `error_kind`

Also verify there is no new raw unstructured `deadlock detected` failure in watcher/indexer logs for the controlled scenario.

## Queue rule

If the controlled scenario runs through queue, inspect both:

- outer `status` and `progress`;
- inner `result.command.result.success`.

If inner success is false, the operation failed even if outer queue status is completed.

## Forbidden

- Do not use accidental timing as the only deadlock trigger.
- Do not run destructive checks on `vast_srv`.
- Do not mark complete if only unit tests passed and no MCP behavior was checked.
- Do not use local direct Python execution as the behavior proof for this step.

## Observation requirement

Record command, expected result, actual result, log check command, log result, queue inner success when applicable, and status in [Step 28](step_28_observations_document.md).

## Completion criteria

MCP behavior proves retry or structured failure, logs prove `[DB_RETRY]` is emitted with structured fields, and queue inner result is inspected when queue is used.
