# Atomic step 06: `file_data_batch` — batch builder + single-RPC `update_file_data_atomic_batch`

## Executor role

`coder_auto`

## Execution directive

Refactor `code_analysis/core/database_client/file_data_batch.py` so that:

1. **`build_file_data_atomic_batches`** (new public function) performs all AST parsing and row construction currently inside `update_file_data_atomic_batch`, but returns **`list[list[tuple[str, tuple[Any, ...] | None]]]`** (each inner list is one **batch** for `execute_logical_write_operation`), plus a **metadata** dict with keys needed to build the return value of `update_file_data_atomic_batch` **without** any database reads between batches.
2. **Eliminate** the **SELECT** batch that ran `SELECT id FROM classes WHERE file_id = ? ORDER BY id` by replacing method `INSERT`s with SQL that binds `class_id` via a correlated subquery: for the method associated with `class_rows` index `class_idx` (0-based), use  
   `(SELECT id FROM classes WHERE file_id = ? ORDER BY id ASC LIMIT 1 OFFSET ?)`  
   with parameters `(file_id, class_idx)` in the `VALUES` clause for the `class_id` column.
3. **`update_file_data_atomic_batch`** calls **`database.execute_logical_write_operation`** exactly once with `{"batches": batches}` (and `defer_constraints` omitted), using batches from `build_file_data_atomic_batches`. Preserve the **public** function signature and return dict shape for existing callers (`compose_cst_writer`, `replace_file_lines_command`, tests).

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database_client/file_data_batch.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** step 05 (`DatabaseClient.execute_logical_write_operation` exists).
- **Blocks:** step 07.

## Read first

- Full current `file_data_batch.py`
- `code_analysis/core/database_client/objects/` (`Class`, `Method`, `Function`, `Import`) — unchanged usage

## Forbidden alternatives

- Do **not** call `begin_transaction`, `commit_transaction`, `rollback_transaction`, or per-batch `execute_batch` on `database` in `update_file_data_atomic_batch`.
- Do **not** leave the old SELECT-based class id resolution in the batch list.

## New function signature (exact)

```python
def build_file_data_atomic_batches(
    file_id: int,
    project_id: str,
    source_code: str,
    file_path: str,
    file_mtime: float,
) -> tuple[list[list[tuple[str, tuple[Any, ...] | None]], dict[str, Any]]:
```

### `build_file_data_atomic_batches` return tuple

- **First element:** `batches` — ordered list of batches:
  - **Batch 0:** `ops1` (same statements as current lines ~80–98 in pre-refactor file: deletes + ast + cst inserts), as list of `(sql, params)` tuples.
  - **Batch 1:** `ops2` — `INSERT INTO classes` for each class row (same as current `ops2` from `_row_to_insert_sql("classes", r)`).
  - **Batch 2:** `ops3` — methods, functions, imports inserts **without** any preceding SELECT. Methods use the **subquery** form for `class_id` as specified below.
- **Second element:** `meta: dict[str, Any]` with at least:
  - `"success": True` if parsing succeeded (if syntax error, do not return batches — see error path).
  - `"file_path": str`, `"file_id": int`
  - `"ast_updated": True`, `"cst_updated": True` on success path
  - `"entities_updated": int`, `"classes": int`, `"functions": int`, `"methods": int`, `"imports": int` — same counting logic as current return dict (lines ~279–293).

### Syntax error path

- If `ast.parse` fails with `SyntaxError`, return `([], {"success": False, "error": f"Syntax error: {e}", "file_path": file_path, "file_id": file_id})` — **empty batches list**; caller must not call `execute_logical_write_operation` with empty batches.

### Method INSERT construction (prescriptive)

For each `(class_idx, row)` in `method_specs` (same iteration order as current code):

1. Build `row_dict = dict(row)` and **delete** key `class_id` from the dict used for column listing (subquery supplies `class_id`).
2. Columns list = keys of `row_dict` **plus** `class_id` inserted in the **same column order** as a literal column list for `INSERT INTO methods (...)`.
3. SQL pattern:  
   `INSERT INTO methods (class_id, <other cols...>) VALUES ((SELECT id FROM classes WHERE file_id = ? ORDER BY id ASC LIMIT 1 OFFSET ?), <placeholders for other cols>)`
4. Params tuple: `(file_id, class_idx, ...values for row_dict in same order as placeholders excluding class_id from values dict)`.

If this ordering is error-prone, **alternative fixed rule:** build SQL using explicit column order from `row_dict` keys sorted **alphabetically** except `class_id` first — **pick one approach in implementation** and document in module comment **only if** needed; prefer **matching** `_row_to_insert_sql` column order by reusing `_row_to_insert_sql` for non-class_id columns and prepending the subquery for `class_id` **only** for `methods` table — **mandatory minimal approach:** implement **dedicated** `_method_row_to_insert_sql_with_class_subquery(row_dict, file_id, class_idx) -> tuple[str, tuple]` that returns one INSERT statement and params.

Add **private** helper with signature:

```python
def _method_insert_sql_with_class_id_subquery(
    row: Dict[str, Any],
    file_id: int,
    class_idx: int,
) -> tuple[str, tuple[Any, ...]]:
    ...
```

## `update_file_data_atomic_batch` algorithm after refactor

1. Call `build_file_data_atomic_batches(...)`.
2. If `meta["success"] is False`, return `meta` only (same as today for syntax errors).
3. If `batches` is empty and success True, raise `RuntimeError` (invariant violation).
4. `database.execute_logical_write_operation({"batches": batches})`.
5. Merge RPC result success into return dict: preserve `meta` counts and flags; set `"success": True` if RPC indicates success (use same `_extract` pattern as other client code — **reuse** `batch_result` from response if needed for diagnostics only).
6. On RPC failure, return `{"success": False, "error": str(e), "file_path": ..., "file_id": ...}` matching prior behavior style.

## Logging

- Keep existing module `logger` usage; add at most one `INFO` line when entering `update_file_data_atomic_batch` with `file_id` and batch count.

## Mandatory validation

```bash
black code_analysis/core/database_client/file_data_batch.py
flake8 code_analysis/core/database_client/file_data_batch.py
mypy code_analysis/core/database_client/file_data_batch.py
pytest tests/test_file_data_batch_integration.py -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If SQLite rejects subquery in `VALUES` for any method row, capture exact error and escalate — **do not** revert to multi-RPC SELECT without orchestrator approval.

## Handoff package

- Export `build_file_data_atomic_batches` for step 07.

---

## LLAMA-readiness appendix

### Imports to add

- `Any` from `typing` if not present
- No new imports if `execute_logical_write_operation` is only used on `database` passed in (typed as `Any` today)

### Forbidden patterns

- Do **not** use `Any` as the **only** type for `database`; keep parameter type as `Any` to match existing file.

### Edge cases

- No classes: `ops2` empty — **omit** batch 1 or use empty list? **Fixed:** if `class_rows` empty, **omit** empty inner batches from the `batches` list entirely (parser requires non-empty inner batches — **so** do not emit batch 1 if empty). Same for `ops3` if empty — omit final batch.
- **Re-read step 02:** each batch must be **non-empty**. Therefore skip empty `ops2` / `ops3` batches when building `batches` list.

### Constants

- SQL fragment: `"SELECT id FROM classes WHERE file_id = ? ORDER BY id ASC LIMIT 1 OFFSET ?"`
