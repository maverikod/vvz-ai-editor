# Refactoring Plan: Eliminate Direct CodeDatabase Usage in Production Code

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Problem Statement

The project architecture mandates a layered access pattern:

```
Command → DatabaseClient (RPC) → DatabaseDriver → СУБД
```

However, multiple production files bypass this architecture by creating or using
`CodeDatabase` directly ("Path 2"), skipping the RPC layer. This causes:

- `INSERT OR REPLACE` statements not adapted for PostgreSQL → `duplicate key` errors
- `functions: 0` on reindexing — files fail before entities are written
- `cst_node_id: ""` — entities not recorded
- Lock contention when multiple connections touch the DB
- **Legacy `db_driver/` does NOT support PostgreSQL at all** — `CodeDatabase` via legacy
  factory only works with `sqlite` and `sqlite_proxy`; any `postgres` driver_type raises
  `ValueError("Unknown database driver: postgres")`. This is the primary technical
  `ValueError("Unknown database driver: postgres")`. This is the primary technical
  motivation for the entire plan, beyond just architectural cleanliness.

## Goal

Eliminate **all** direct `CodeDatabase` usage from production code. Every DB operation
must go through `DatabaseClient` (RPC path). `CodeDatabase` remains only as:

- Internal implementation behind the driver layer
- Test fixture setup (tests are out of scope)

## Scope

**In scope:** Production code under `code_analysis/` (not `tests/`, not `scripts/`).

**Out of scope:** Test fixtures using `CodeDatabase` for test DB setup —
these are acceptable because tests use SQLite in-memory and don’t hit PostgreSQL.

---

## Important: Line Numbers In Step Files

> **Warning:** Line numbers in the per-step files were verified against specific commits.
> Before applying any `cst_modify_tree` or `cst_get_node_by_range` command, **always**
> re-verify node IDs via `cst_load_file` + `cst_find_node`. Use node_id, not line number
> as the primary key for all CST operations. node_id values in step files are the ones
> verified at time of writing — reload the tree and confirm before applying.

## Important: Two SQLiteDriver Classes

The codebase has **two** classes named `SQLiteDriver`:
- `code_analysis.core.database_driver_pkg.drivers.sqlite.SQLiteDriver` — the **RPC process driver** (use this in all steps)
- `code_analysis.core.db_driver.sqlite.SQLiteDriver` — the legacy factory driver used by `CodeDatabase` internally

Always import from `database_driver_pkg.drivers.sqlite`, not from `db_driver.sqlite`.

---

## Files to Refactor

### 1. `core/database_driver_pkg/rpc_handlers_index_file.py`

**Location:** lines 102-112 (try-block with CodeDatabase.from_existing_driver)
**Current behavior:**
```python
from code_analysis.core.database import CodeDatabase
db = CodeDatabase.from_existing_driver(self.driver)
update_result = db.update_file_data(file_path, project_id, Path(root_path))
```
**Problem:** Creates `CodeDatabase` wrapper around existing driver, then calls
`update_file_data` which is a mixin method on CodeDatabase.

**Fix:** Call `update_file_data_via_driver(self.driver, ...)` (created in step 09).

**Complexity:** HIGH — depends on step 09.

**Callers:** `handle_index_file` RPC handler (invoked by file_watcher after file changes).

---

### 2. `core/database/files/update.py`

**Location:** line 27 — `update_file_data(self, ...)` (401 lines)
**Current behavior:** CodeDatabase mixin that calls `analyze_file(database=self, ...)`.

**Note:** `analyze_file()` in `update_indexes_analyzer.py` accepts `database: Any` but
requires `DatabaseClient` instance internally (uses `add_file`, `save_ast_tree`, etc.).

**Fix:** Create `update_file_data_via_driver` in new `update_standalone.py` that wraps
driver in `InProcessRpcClient → DatabaseClient` and calls `analyze_file(database=client)`.
Do NOT rewrite `update.py` itself — keep CodeDatabase mixin for backward compat.

**Complexity:** HIGH — but addressed via standalone wrapper in step 09, not rewrite.

---

### 3. `core/database/files/update_vectorize.py`

**Location:** line 16 — `vectorize_file_immediately(self, ...)` (306 lines)
**Current behavior:** CodeDatabase mixin that chunks and vectorizes a file.

**Fix:** Create `update_and_vectorize_via_driver` in `update_standalone.py` (step 10).

**Complexity:** MEDIUM — depends on step 09 + requires reading chunking SQL.

---

### 4. `core/indexing_worker_pkg/vectorize_after_index.py`

**Location:** lines 87-98 — `_create_database()`
**Current behavior:**
```python
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
driver = SQLiteDriver()
driver.connect({"path": str(db_path.resolve())})
return CodeDatabase.from_existing_driver(driver)
```
**Problem:** Creates CodeDatabase directly, bypasses RPC, only works with SQLite.

**Fix:** Use `InProcessRpcClient(RPCHandlers(driver)) → DatabaseClient(rpc_client=ipc)`.

**Complexity:** MEDIUM — step 06 addresses `_create_database`/`_close_driver`;
`_vectorize_file_immediately` wrapper blocked until step 10.

---

### 5. `core/faiss_manager.py`

**Location:** line 26 `from .database import CodeDatabase`, line 24 `from typing import Union`
**Current behavior:** Type hints use `Union[CodeDatabase, DatabaseClient]`.

**Fix:** Remove both imports; change signatures to `database: DatabaseClient`.
**Union in this file** is ONLY used for `Union[CodeDatabase, DatabaseClient]` — no other usages.

**Complexity:** LOW.

---

### 6. `core/faiss_manager_rebuild.py`

**Location:** lines 14/10 — CodeDatabase import + Union in typing.
**Current behavior:** `database: Union[CodeDatabase, DatabaseClient]` dual-path.
**Note (behaviour fix):** When `database` is `DatabaseClient`, the embedding save code
`if isinstance(database, CodeDatabase): database._execute(...)` is skipped, so
embeddings are silently NOT saved. Step 02 fixes this bug.

**Complexity:** LOW.

---

### 7. `core/faiss_manager_sync.py`

**Location:** lines 10/8 — CodeDatabase import + Union in typing.
**Current behavior:** `database: Union[CodeDatabase, DatabaseClient]` dual-path.

**Complexity:** LOW.

---

### 8. `core/database_driver_pkg/rpc_handlers_file_trash.py`

**Location:** lines 30-34 — `_get_code_db()` method.
**Current behavior:**
```python
def _get_code_db(self):
    from code_analysis.core.database import CodeDatabase
    return CodeDatabase.from_existing_driver(self.driver)
```
**Important:** Trash methods (`mark_file_deleted`, `unmark_file_deleted`, `hard_delete_file`)
are NOT pure SQL — they also perform **filesystem operations** (move/delete physical files).
See `core/database/files/trash.py:17` (438 lines).

**Complexity:** MEDIUM-HIGH — architecture decision required (see step 07).

---

### 9. `main_workers.py`

**Location:** lines 289-331 — `if not db_path_obj.exists():` block
**Current behavior:**
```python
from code_analysis.core.database import CodeDatabase
init_database = CodeDatabase(driver_config=driver_config)
init_database.close()
```
**Fix:** Use `SQLiteDriver`/`PostgreSQLDriver` + `get_schema_definition()` + `driver.sync_schema()`.
Branch on `driver_config["type"]` for SQLite vs PostgreSQL.

**Complexity:** LOW.

---

### 10. `cli/config_cli_commands.py`

**Location:** lines 55-64 inside `cmd_schema`
**Current behavior:** `CodeDatabase(driver_config)` to apply schema.
**Fix:** Use `SQLiteDriver` + `get_schema_definition()` + `driver.sync_schema()`.
`backup_dir` computed from `db_path`.

**Complexity:** LOW.

---

## Execution Order (recommended by INDEX.md)

| Step | Plan file | Target | Risk |
|------|-----------|--------|------|
| 01 | step-01 | `faiss_manager_sync.py` | LOW |
| 02 | step-02 | `faiss_manager_rebuild.py` | LOW |
| 03 | step-03 | `faiss_manager.py` | LOW |
| 04 | step-04 | `cli/config_cli_commands.py` | LOW |
| 05 | step-05 | `main_workers.py` | LOW |
| 06 | step-06 | `indexing_worker_pkg/vectorize_after_index.py` | MEDIUM |
| 07 | step-07 | `rpc_handlers_file_trash.py` | MEDIUM |
| 09 | step-09 | NEW `database/files/update_standalone.py` | HIGH |
| 08 | step-08 | `rpc_handlers_index_file.py` | HIGH |
| 10 | step-10 | extend `update_standalone.py` | MEDIUM |

**Note:** Steps 08 and 09 are ordered 09 → 08 (create standalone first, then apply to handler).

## Validation After Each Phase

1. `comprehensive_analysis` — no new errors
2. `lint_code` + `type_check_code` — clean
3. Run relevant tests: `pytest tests/ -k <relevant_test_pattern>`
4. Verify reindexing works: `update_indexes` on test project
5. Check `functions` count > 0 and `cst_node_id` populated

## Related Patches (from previous session, verified)

- `postgres_run.py` — `_FILES_INSERT_OR_REPLACE_NORM` + `ON CONFLICT` branch — **APPLIED ✅**
- `crud.py` (`add_file`) — uses UPDATE/INSERT (not INSERT OR REPLACE) — **correct for Path 1**

## Risk Assessment

- **Steps 01-05:** Low risk — type signatures and isolated utilities
- **Steps 06-07:** Medium risk — vectorization and trash still must work
- **Steps 09, 08, 10:** High risk — core indexing pipeline, needs thorough testing

## Dependencies (verified)

- `DatabaseClient` already supports all core client operations (`add_file`, `save_ast_tree`, etc.)
- `InProcessRpcClient(handlers: RPCHandlers)` exists — `database_client/in_process_rpc_client.py:38`
- `RPCHandlers(driver: BaseDatabaseDriver)` exists — `database_driver_pkg/rpc_handlers.py:42`
- `DatabaseClient(rpc_client=...)` exists — `database_client/client.py:56` (keyword-only param)
- `analyze_file()` in `update_indexes_analyzer.py:34` accepts `DatabaseClient` (not CodeDatabase); **it is sync (def, not async)**
- `sync_schema(schema_definition, backup_dir)` exists on `SQLiteDriver:476` and `PostgreSQLDriver:532`
  (`backup_dir` is Optional with default None; always pass it explicitly for backup behavior)
- `get_schema_definition()` is a free function in `core/database/schema_definition.py:30`
- Trash methods include filesystem operations — cannot be simplified to SQL-only replacement
- `core/database/__init__.py:12` re-exports `CodeDatabase` — kept intentionally for tests

## Post-refactoring validation (cleanup pass)

After step 10 completes and full reindex passes, run this verification:

```bash
# Must return ZERO production files (only tests/ and scripts/ allowed)
grep -r 'CodeDatabase' code_analysis/ --include='*.py' \
  | grep -v 'tests/' | grep -v 'scripts/' | grep -v 'database/' | grep -v 'core/db_driver/'
```

Expected result: 0 matches (all production `CodeDatabase` usage eliminated).
If any match appears — stop and investigate before proceeding to step 11.