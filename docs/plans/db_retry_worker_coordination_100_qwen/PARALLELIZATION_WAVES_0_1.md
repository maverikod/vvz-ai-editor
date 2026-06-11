# Parallelization waves 0-1

Previous: [Parallelization index](PARALLELIZATION.md). Next: [Waves 2-3](PARALLELIZATION_WAVES_2_3.md).

## Wave 0: coordination

Agent Lead can start immediately.

Owns:
- Step 28 observations document.
- Merge coordination.
- Final evidence collection for Steps 35-36.

Files:
- `docs/observations/db_retry_worker_coordination.md`
- `docs/observations/db_retry_worker_coordination_final_report.md` after execution.

Blocks:
- Final acceptance.
- Final report.

Notes:
- This agent does not implement source code changes.
- This agent checks that every other agent records actual commands and verification results.

## Wave 1: core DB contract

### Agent A: transient exceptions and PostgreSQL classifier

Can start immediately.

Owns:
- Step 01 exceptions contract.
- Step 02 PostgreSQL error classification.
- Step 20 transient error tests.

Files:
- `code_analysis/core/database_driver_pkg/exceptions.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `tests/test_database_driver_transient_errors.py`

Blocks:
- Agent C: PostgreSQL driver retry.
- Agent D: RPC retry and structured errors.
- Agent H: SQLite/base/client compatibility.

Deliverable:
- Structured `TransientDatabaseError` and `DatabaseErrorInfo` exist.
- PostgreSQL SQLSTATE classification exists.
- Unit tests prove SQLSTATE policy.

### Agent B: retry policy and transaction timeouts

Can start immediately in parallel with Agent A.

Owns:
- Step 03 PostgreSQL transaction timeouts.
- Step 04 shared retry policy.

Files:
- `code_analysis/core/database_driver_pkg/drivers/postgres_transactions.py`
- `code_analysis/core/retry_policy.py`

Blocks:
- Agent C: PostgreSQL driver retry.
- Agent H: SQLite retry compatibility.

Deliverable:
- Shared retry policy exists.
- PostgreSQL transaction manager accepts timeout config and applies `SET LOCAL` values.

## Wave 1 merge rule

Merge Agent A and Agent B before Agent C starts. Agent E, F, and G may already work in parallel because they do not edit the same files.
