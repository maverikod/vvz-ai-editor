# Atomic step 03: `handle_execute_logical_write_operation` on `RPCHandlers`

## Executor role

`coder_auto`

## Execution directive

Implement `handle_execute_logical_write_operation(self, params: dict[str, Any]) -> SuccessResult | ErrorResult` on `_RPCHandlersSchemaMixin` in `rpc_handlers_schema.py`, delegating to `self.driver.begin_transaction()`, then **for each** inner batch calling `self.driver.execute_batch(batch_ops, transaction_id)`, then `self.driver.commit_transaction(transaction_id)`. On any exception after `begin_transaction`, call `self.driver.rollback_transaction(transaction_id)` before returning `ErrorResult`. Optionally honor `defer_constraints` via `PRAGMA defer_foreign_keys=ON` immediately after begin.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database_driver_pkg/rpc_handlers_schema.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** steps 01–02 (`parse_logical_write_batches_param` in `rpc_handlers_base.py`).
- **Blocks:** step 04.

## Read first

- `code_analysis/core/database_driver_pkg/rpc_handlers_schema.py` (full file)
- `code_analysis/core/database_driver_pkg/rpc_handlers_base.py` (`parse_logical_write_batches_param`, `handle_execute_batch`)
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py` (`begin_transaction`, `execute_batch`, `commit_transaction`, `rollback_transaction`, `execute`)

## Expected file change

- Add **one** method `handle_execute_logical_write_operation` to `_RPCHandlersSchemaMixin`.
- Add imports: `parse_logical_write_batches_param` from `.rpc_handlers_base`.

## Forbidden alternatives

- Do **not** spawn threads or bypass the driver.
- Do **not** call `rpc_client` from the handler (server-side only).

## Method signature (exact)

```python
def handle_execute_logical_write_operation(
    self, params: Dict[str, Any]
) -> SuccessResult | ErrorResult:
```

## Algorithm

1. Call `parse_logical_write_batches_param(params)`. If first tuple element is `ErrorResult`, return it.
2. Let `batches` be the parsed list (guaranteed non-empty list of non-empty lists by parser).
3. `transaction_id: str = self.driver.begin_transaction()` inside `try` block.
4. If `params.get("defer_constraints") is True` (truthy), call `self.driver.execute("PRAGMA defer_foreign_keys=ON", None, transaction_id)` — if this raises or returns an error shape not expected, treat as failure → rollback branch.
5. Initialize `batch_results: list[dict[str, Any]] = []`.
6. For each `batch_ops` in `batches` in order:
   - `results = self.driver.execute_batch(batch_ops, transaction_id)` (same contract as existing `handle_execute_batch` inner call).
   - Append `{"results": results}` to `batch_results`.
7. `self.driver.commit_transaction(transaction_id)`.
8. Return `SuccessResult(data={"batch_results": batch_results, "transaction_id": transaction_id})`.

## Rollback / error handling

- Wrap steps 3–7 in `try` / `except Exception as e`:
  - If `transaction_id` is assigned, call `self.driver.rollback_transaction(transaction_id)` in `try` / `except Exception` (swallow rollback errors but log).
  - Return `ErrorResult(error_code=ErrorCode.DATABASE_ERROR, description=str(e))` (same pattern as `handle_execute_batch`).
- Do **not** raise uncaught exceptions from the handler method.

## Logging

- One `logger.info` line at start: `method=execute_logical_write_operation n_batches=%s` with `len(batches)`.
- One `logger.info` after begin: include shortened `transaction_id` prefix like other handlers (`[CHAIN]` prefix optional but preferred for consistency with `handle_begin_transaction`).

## Return value specification

- Success payload keys:
  - `transaction_id`: `str` — value returned by `begin_transaction` (for diagnostics only).
  - `batch_results`: `list[dict[str, Any]]` where each element is exactly `{"results": <list from driver.execute_batch>}`.

## Edge cases

- Single batch with one SQL statement: valid; `batch_results` length 1.
- `defer_constraints` absent or false: skip PRAGMA.

## Mandatory validation

```bash
black code_analysis/core/database_driver_pkg/rpc_handlers_schema.py
flake8 code_analysis/core/database_driver_pkg/rpc_handlers_schema.py
mypy code_analysis/core/database_driver_pkg/rpc_handlers_schema.py
pytest tests/test_rpc_handlers.py tests/test_driver_rpc_server.py -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If `SQLiteDriver.execute` for PRAGMA fails in tests, set `defer_constraints` handling to **no-op** with comment **only if** step 06 proves sync never sets it to true — **do not** guess; run PRAGMA as specified and fix driver/tests.

## Handoff package

- Handler method name **exact string:** `handle_execute_logical_write_operation` (must match `rpc_server` registration string in step 04).

---

## LLAMA-readiness appendix

### Imports to add (in addition to existing file imports)

```text
from .rpc_handlers_base import parse_logical_write_batches_param
```

### Constants

- None.

### Forbidden patterns

- Bare `except:`
