# Atomic step 02: Parse and validate `execute_logical_write_operation` params (RPC handlers base)

## Executor role

`coder_auto`

## Execution directive

Add a **module-level** helper function in `rpc_handlers_base.py` that converts raw RPC `params` (`dict[str, Any]`) into a validated **list of batches** (each batch a list of `(sql, params)` tuples compatible with `SQLiteDriver.execute_batch`), or returns a structured validation `ErrorResult` with `ErrorCode.VALIDATION_ERROR`. This helper is called by `handle_execute_logical_write_operation` in step 03.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database_driver_pkg/rpc_handlers_base.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** step 01 (`LogicalWriteProgramV1` field names and `SqlParamPair` semantics).
- **Blocks:** step 03.

## Required context

- `handle_execute_batch` in the same file: validation style for `operations` list and each `{sql, params}` item (reuse the same rules for per-row SQL inside each batch).
- Tactical **Algorithm (handler)** expects `batches` as ordered list of batches; each batch is one `driver.execute_batch` call.

## Read first

- `code_analysis/core/database_driver_pkg/rpc_handlers_base.py` (`handle_execute_batch` full method)
- `code_analysis/core/database/logical_write_program.py` (from step 01)

## Expected file change

- Add **one** module-level function; do **not** change behavior of existing handler methods except if imports require reordering (minimize diff).

## Forbidden alternatives

- Do **not** perform `begin_transaction` / `execute_batch` / `commit` in this step — parsing only.
- Do **not** add a new mixin class; use a single module-level function as specified below.
- Do **not** change `handle_execute_batch` behavior.

## Atomic operations

### Function to implement (exact signature)

```python
def parse_logical_write_batches_param(
    params: Dict[str, Any],
) -> tuple[Optional[ErrorResult], Optional[list[list[tuple[str, Optional[tuple[Any, ...]]]]]]]:
    ...
```

### Algorithm `parse_logical_write_batches_param`

1. If `params` is not a `dict`, return `(ErrorResult(VALIDATION_ERROR, "params must be a dict"), None)`.
2. If `params.get("batches")` is missing or not a `list`, return `(ErrorResult(VALIDATION_ERROR, description="batches (non-empty list) is required"), None)`.
3. If `batches` is an **empty** list, return `(ErrorResult(VALIDATION_ERROR, description="batches must be non-empty"), None)`.
4. Iterate each **outer** element `batch` with index `i`:
   - If `batch` is not a `list`, return `(ErrorResult(..., f"batches[{i}] must be a list"), None)`.
   - If `batch` is **empty**, return `(ErrorResult(..., f"batches[{i}] must be non-empty"), None)`.
5. For each `batch`, build `operations: list[tuple[str, Optional[tuple[Any, ...]]]]` by iterating items with index `j`:
   - If item is not a `dict`, error `"batches[{i}][{j}] must be {sql, params}"`.
   - Read `sql = item.get("sql")` — if missing or empty string, validation error.
   - Read `p = item.get("params")` — if `p is None`, bind `None`; elif `isinstance(p, (list, tuple))`, bind `tuple(p)`; else validation error (same wording as `handle_execute_batch`).
6. Append each `(sql, bind)` to the inner list. Result type matches step 4 outer structure: `list[list[tuple[str, Optional[tuple[Any, ...]]]]]`.
7. `defer_constraints` is **not** parsed here (handler uses raw `params.get("defer_constraints")` in step 03).

### Imports to add

- `Optional`, `Any`, `Dict` from `typing` if not already present
- `ErrorResult`, `ErrorCode` from `code_analysis.core.database_client.protocol` (already imported in file — reuse)

### Error handling

- Only return `ErrorResult` for validation failures; never raise for invalid input.

### Edge cases

- `batches` containing one batch with one operation: valid.
- Extra keys in `params` ignored except `batches` (and `defer_constraints` ignored here).

## Expected deliverables

- `parse_logical_write_batches_param` implemented and used in step 03.

## Mandatory validation

```bash
black code_analysis/core/database_driver_pkg/rpc_handlers_base.py
flake8 code_analysis/core/database_driver_pkg/rpc_handlers_base.py
mypy code_analysis/core/database_driver_pkg/rpc_handlers_base.py
pytest tests/test_rpc_handlers.py -q
```

Expected: flake8 silent; mypy success; pytest passes.

**Completion:** full `pytest -q` must pass.

## Decision rules

- Validation messages must be stable strings (tests may assert substrings in step 09).

## Blackstops

- Stop if `ErrorResult` constructor signature differs — read `protocol` module for exact fields.

## Handoff package

- Function name and contract documented for step 03.

---

## LLAMA-readiness appendix

### Target file header

- Do **not** change existing module docstring except appending nothing (keep file header as-is).

### Complete import list (file after edit)

- Start from existing imports in `rpc_handlers_base.py` and add only what is missing for `Optional`, `Any` in the new signature (file already has `Dict`).

### Constants

- None new.

### Forbidden patterns

- No `print()`
- No bare `except:`

### Test expectations

- Covered indirectly in step 09; step 02 has no new dedicated test requirement beyond suite pass.
