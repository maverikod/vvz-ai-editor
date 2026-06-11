# Atomic step 01: `LogicalWriteProgramV1` types module

## Executor role

`coder_auto`

## Execution directive

Create a new module that defines the **exact** `TypedDict` shapes for the composite logical-write RPC payload (`LogicalWriteProgramV1`) and the SQL row type alias used by the tactical task, so that `DatabaseClient` and RPC handlers share one canonical type definition without circular imports.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file (full path from repo root):** `code_analysis/core/database/logical_write_program.py`
- **action:** `create`

## Dependency contract

- **Depends on:** none (first step).
- **Blocks:** step 02 (handlers import these types or duplicate field names exactly — prefer import).

## Required context

- Tactical task **Data structures** table: `LogicalWriteProgramV1`, `SqlParamPair`, `batches` semantics.
- Project rule: module docstring must include Author and email as in other `code_analysis` modules.

## Read first

- `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md` (Class/function inventory, Data structures)
- `code_analysis/core/database_client/client_operations.py` (style for typing imports)

## Expected file change

- New file `logical_write_program.py` containing only type aliases and TypedDict definitions (no I/O, no RPC).

## Forbidden alternatives

- Do **not** place `LogicalWriteProgramV1` only inside `client_operations.py` if the tactical inventory lists a shared type; this step creates the shared module first.
- Do **not** use `typing.Any` for `SqlParamPair` tuple elements; use `Any` only where the tactical table uses `Any` for parameter payloads, and import `Any` from `typing`.
- Do **not** add runtime validation functions in this file (validation is step 02 / client step).

## Atomic operations

1. Add the new file with the module docstring specified below.
2. Define `SqlParamPair` as `Tuple[str, Sequence[Any]]` (import `Sequence`, `Tuple`, `Any` from `typing`).
3. Define `LogicalWriteProgramV1` as a `TypedDict` with **`total=False`** and keys:
   - `batches: list[list[SqlParamPair]]` — **required at runtime** for every mutating call; step 02 validates presence.
   - `defer_constraints: bool` — optional; when absent, treat as `False`.
4. Add module-level constant `DEFAULT_DEFER_CONSTRAINTS: bool = False`.
5. Export names for use by `client_operations` and `rpc_handlers_schema` in later steps.

**Exact TypedDict:**

```python
class LogicalWriteProgramV1(TypedDict, total=False):
    batches: list[list[SqlParamPair]]
    defer_constraints: bool
```

## Expected deliverables

- New module file on disk at the target path.
- `mypy`-friendly definitions (no invalid forward refs).

## Mandatory validation

From repo root with venv active:

```bash
black code_analysis/core/database/logical_write_program.py
flake8 code_analysis/core/database/logical_write_program.py
mypy code_analysis/core/database/logical_write_program.py
```

Expected:

- black: `reformatted` or `already well formatted`
- flake8: exit code 0, no output
- mypy: `Success: no issues found`

**Completion:** all tests in the repository must still pass (`pytest -q`); this step adds no tests.

## Decision rules

- Use only `TypedDict` + `total=False` as shown; no `typing_extensions`.

## Blackstops

- Stop and escalate if `TypedDict` + `total=False` is rejected by project linters; report the exact flake8/mypy rule.

## Handoff package

- File created; list of exported symbols: `SqlParamPair`, `LogicalWriteProgramV1`, `DEFAULT_DEFER_CONSTRAINTS`.

---

## LLAMA-readiness appendix

### File header (exact module docstring)

```text
"""
Logical write program types for composite SQLite RPC transactions.

Defines TypedDict payloads for execute_logical_write_operation (one RPC, full transaction).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

### Imports (complete list)

```text
from __future__ import annotations

from typing import Any, Sequence, Tuple, TypedDict
```

Include module constant `DEFAULT_DEFER_CONSTRAINTS: bool = False` after imports.

### Class/function skeleton

- No functions or classes; only type aliases and `TypedDict` + constant `DEFAULT_DEFER_CONSTRAINTS: bool`

### Method logic

- N/A

### Error handling

- N/A

### Return values

- N/A

### Edge cases

- N/A

### Constants and literals

- `DEFAULT_DEFER_CONSTRAINTS = False`

### Forbidden patterns

- No `print()`
- No I/O
- No new dependencies beyond stdlib / existing project patterns

### Test expectations

- None for this step.
