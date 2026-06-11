# Step 01 — Exceptions contract

Previous: [README](README.md). Next: [Step 02](step_02_postgres_error_classification.md).

File: `code_analysis/core/database_driver_pkg/exceptions.py`

## Goal
Create one stable structured contract for transient database errors. Upper layers must not parse strings such as `deadlock detected`.

## Required changes
1. Add `DatabaseErrorInfo` as `dataclass(frozen=True)` with fields:
   - `sqlstate: str | None`
   - `error_kind: str`
   - `retryable: bool`
   - `message: str`
   - `commit_outcome_unknown: bool = False`
2. Add `TransientDatabaseError(DriverOperationError)` with fields:
   - `sqlstate: str | None`
   - `error_kind: str`
   - `retryable: bool = True`
   - `original_error: BaseException | None`
   - `attempts: int | None = None`
   - `commit_outcome_unknown: bool = False`
3. Add method `to_details(operation_name: str | None = None, attempts: int | None = None) -> dict[str, Any]`.
4. Add helper `database_error_details(exc, operation_name=None, attempts=None) -> dict[str, Any]`.
5. Preserve all existing exception classes and imports.

## Exact details schema
```json
{
  "sqlstate": "40P01",
  "error_kind": "deadlock",
  "retryable": true,
  "attempts": 3,
  "operation_name": "watcher_ignore_purge",
  "commit_outcome_unknown": false
}
```

## Verification
Run a unit-level import or CST/read command to confirm `DatabaseErrorInfo`, `TransientDatabaseError`, and `database_error_details` exist.

## Observation entry
Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
