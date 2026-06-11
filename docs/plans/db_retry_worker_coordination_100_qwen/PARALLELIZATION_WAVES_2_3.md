# Parallelization waves 2-3

Previous: [Waves 0-1](PARALLELIZATION_WAVES_0_1.md). Next: [Waves 4-6](PARALLELIZATION_WAVES_4_6.md).

## Wave 2: driver and RPC retry

### Agent C: PostgreSQL driver retry

Starts after Agents A and B are merged.

Owns:
- Step 05 PostgreSQL driver retry.

Files:
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`

Waits for:
- Agent A: `TransientDatabaseError`, `DatabaseErrorInfo`, PostgreSQL classification.
- Agent B: `RetryPolicy`, PostgreSQL transaction timeout constructor.

Blocks:
- Agent D real-driver integration path.
- Step 31 MCP retry behavior checks.

Deliverable:
- Self-managed `execute` and `execute_batch` retry transient DB errors.
- External `transaction_id` operations are not retried at driver level.
- Rollback happens before retry.
- No retry happens when commit outcome is unknown.
- `[DB_RETRY] backend=postgres layer=driver ...` log exists.

### Agent D: RPC retry and structured base errors

Starts after Agent A and Agent B. Prefer starting after Agent C is merged, but fake-driver tests may be drafted earlier.

Owns:
- Step 06 RPC logical write retry.
- Step 07 RPC base structured errors.
- Step 21 logical write retry tests.

Files:
- `code_analysis/core/database_driver_pkg/rpc_handlers_schema.py`
- `code_analysis/core/database_driver_pkg/rpc_handlers_base.py`
- `tests/test_rpc_logical_write_retry.py`

Waits for:
- Agent A: structured transient details.
- Agent B: retry policy.
- Prefer Agent C for full integration consistency.

Blocks:
- Step 31 MCP retry behavior.
- Watcher ignore purge metadata usefulness in Step 15.

Deliverable:
- Logical write retry repeats the whole transaction.
- Plain `execute` and `execute_batch` RPC handlers return structured transient error details.
- Unknown commit outcome is not retried.

## Wave 3: client metadata and config

### Agent E: logical-write metadata

Can start immediately after metadata names are accepted.

Owns:
- Step 08 logical write metadata type.
- Step 09 client metadata forwarding.
- Step 23 metadata forwarding tests.

Files:
- `code_analysis/core/database/logical_write_program.py`
- `code_analysis/core/database_client/client_operations.py`
- `tests/test_logical_write_program_metadata.py`

Can run in parallel with:
- Agent C.
- Agent D.
- Agent F.
- Agent G.

Blocks:
- Agent J Step 15 ignore purge metadata.
- Operation-name verification in Step 31.

Deliverable:
- `operation_name`, `project_id`, and `lock_scope` are optional metadata fields.
- Client forwards metadata without retrying.

### Agent F: config validator

Can start after canonical config names are fixed in Step 04 and README.

Owns:
- Step 10 config validator.
- Step 22 config validator tests.

Files:
- `code_analysis/core/config_validator/section_database_driver.py`
- `tests/test_database_driver_config_validator_retry.py`

Can run in parallel with:
- Agent C.
- Agent D.
- Agent E.
- Agent G.

Blocks:
- Final config acceptance.

Deliverable:
- Canonical retry and timeout names are accepted and validated.
- Deprecated aliases are rejected.
- Old configs without new fields still pass.

## Wave 2-3 merge rule

Merge Agent E and Agent F when their tests pass; they do not need to wait for Agent C unless imports require it. Merge Agent D after Agent A and Agent B at minimum, and preferably after Agent C to reduce integration churn.
