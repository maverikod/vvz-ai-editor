# Step 07: rpc_handlers_file_trash.py — replace _get_code_db() with self.driver calls

## Target file
`code_analysis/core/database_driver_pkg/rpc_handlers_file_trash.py` (170 lines)

## Architecture check
`_RPCHandlersFileTrashMixin` is part of `RPCHandlers` — the UNIVERSAL DRIVER layer.
It runs INSIDE the driver process. `self.driver` is the SPECIFIC DRIVER (SQLiteDriver/PostgreSQL).

**Current (WRONG) path:**
RPCHandlers → `_get_code_db()` → `CodeDatabase.from_existing_driver(self.driver)` → CodeDatabase mixin methods

**Correct path:**
RPCHandlers → `self.driver.execute()` directly (no CodeDatabase wrapper)

**CANNOT use DatabaseClient here** — it is a network client. Using it inside
the driver process would create a recursive RPC call.

**IMPORTANT NOTE on trash logic complexity:**
The CodeDatabase trash methods (`mark_file_deleted`, `unmark_file_deleted`, `hard_delete_file`)
are NOT pure SQL operations. They also perform **filesystem operations** (move/delete physical files).
They live in `code_analysis/core/database/files/trash.py`:
- `mark_file_deleted` (line 17, ~220 lines): moves file to trash dir, updates DB record
- `unmark_file_deleted` (line 236, ~130 lines): moves file back from trash, clears deleted flag
- `get_deleted_files` (line 366, ~28 lines): pure SELECT
- `hard_delete_file` (line 394, ~44 lines): deletes physical file + clears all DB data

This means: extracting SQL alone is NOT sufficient — filesystem logic must also be moved.
Read `code_analysis/core/database/files/trash.py` in full before implementing any handler.

## STOP — architectural decision required before implementation

Two approaches, choose one:

**Approach A (full refactor, recommended):**
Extract the filesystem+SQL logic from trash.py into standalone functions that accept
`BaseDatabaseDriver` instead of `self` (CodeDatabase). Then call those from the handlers.
Files to create: `code_analysis/core/database/files/trash_standalone.py`
Scope: large (200+ lines), but architecturally clean.

**Approach B (acceptable exception):**
Keep `_get_code_db()` as a documented architectural exception with a comment:
```python
def _get_code_db(self):
    """ARCHITECTURAL NOTE: uses CodeDatabase.from_existing_driver to reuse
    the driver connection. Does NOT open a new connection or call sync_schema.
    Trash operations include filesystem moves which are not part of the RPC
    driver interface. This is an accepted exception until trash logic is
    extracted to a driver-level module."""
    from code_analysis.core.database import CodeDatabase
    return CodeDatabase.from_existing_driver(self.driver)
```

Approach B is safe: `from_existing_driver` reuses the existing driver connection
without calling `sync_schema()` or opening a second connection.

**Consult user before implementing either approach.**

## If Approach A is chosen — prerequisites

Before writing any handler code:
1. Read `code_analysis/core/database/files/trash.py` lines 1-438 in full
2. Map every `self._execute()`, `self._fetchone()`, `self._fetchall()`, `self._commit()` call
   to `self.driver.execute()` equivalent
3. Identify all `self.get_project()`, `self.get_file_by_path()`, `self.clear_file_data()` calls
   and map them to direct SQL via `self.driver.execute()`
4. Create `trash_standalone.py` with functions accepting `BaseDatabaseDriver`
5. Only then rewrite the 4 handlers

## If Approach A is chosen — implementation guide

**Never guess SQL — always read source before writing.**

```
tree_id = cst_load_file(file_path="code_analysis/core/database_driver_pkg/rpc_handlers_file_trash.py")
```

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Lines | node_id |
|---------|-------|---------|
| `_get_code_db` FunctionDef | **30-34** | `0659a7a4-bbd3-4bc2-80b3-dc1f623c44fb` |
| `handle_mark_file_deleted` FunctionDef | **36-70** | `4312d641-46e3-4615-9847-93ecdab6cc4b` |
| `handle_unmark_file_deleted` FunctionDef | **72-106** | `87d7b8f3-170d-46e1-a3e7-759ebc6716ed` |
| `handle_hard_delete_file` FunctionDef | **108-142** | `31572cdb-fc90-42e3-b3c4-64cb04f232f4` |
| `handle_get_deleted_files` FunctionDef | **144-170** | `3b7620e5-ebe4-49b0-a1dd-e22a4f952a77` |

**Note:** After removing `_get_code_db()`, there are no other usages of
`from code_analysis.core.database import CodeDatabase` in this file.
The local import inside the method body is removed together with the method.
No separate import-cleanup step is needed.

## Validation sequence
1. `lint_code(file_path="code_analysis/core/database_driver_pkg/rpc_handlers_file_trash.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. Test trash operations end-to-end:
   - `delete_file` MCP command
   - `list_deleted_files` MCP command
   - `restore_deleted_files` MCP command

## Risk: MEDIUM (Approach A) / LOW (Approach B)
Approach A: 200+ lines to move, filesystem logic must be preserved exactly.
Approach B: no code change, only documentation added to `_get_code_db`.
