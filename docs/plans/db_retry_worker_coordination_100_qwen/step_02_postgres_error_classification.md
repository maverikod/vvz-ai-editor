# Step 02 — PostgreSQL error classification

Previous: [Step 01](step_01_exceptions_contract.md). Next: [Step 03](step_03_postgres_transaction_timeouts.md).

File: `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`

## Goal
Preserve PostgreSQL SQLSTATE and raise structured transient errors. Do not retry in this file.

## Required changes
1. Import `DatabaseErrorInfo`, `TransientDatabaseError`, and `DriverOperationError` from [Step 01](step_01_exceptions_contract.md).
2. Add `classify_postgres_error(exc: BaseException) -> DatabaseErrorInfo`.
3. Extract SQLSTATE with:
   - `getattr(exc, "sqlstate", None)`
   - fallback `getattr(getattr(exc, "diag", None), "sqlstate", None)`
4. Classification:
   - `40P01` → `error_kind="deadlock"`, `retryable=True`
   - `40001` → `error_kind="serialization_failure"`, `retryable=True`
   - `55P03` → `error_kind="lock_not_available"`, `retryable=True`
   - `57014` → `error_kind="query_canceled"`; retryable only if message clearly indicates timeout: `lock timeout`, `statement timeout`, or `canceling statement due to statement timeout`
   - all other SQLSTATE values → `error_kind="postgres_error"`, `retryable=False`
5. In `run_execute()` and `run_execute_batch()`, catch non-driver exceptions, classify them, and raise `TransientDatabaseError` only when `retryable=True`.
6. For non-retryable errors, raise `DriverOperationError` with original exception chained.
7. For commit errors, classify too. If commit outcome may be unknown, do not allow retry: use details with `commit_outcome_unknown=True` and `retryable=False`.

## Forbidden
- Do not add sleep or retry here.
- Do not parse `deadlock detected` outside `classify_postgres_error`.
- Do not convert SQLSTATE to a plain string-only error.

## Verification
Use CST/query or tests to confirm `classify_postgres_error` exists and `run_execute_batch` raises `TransientDatabaseError` for retryable PostgreSQL SQLSTATE.
