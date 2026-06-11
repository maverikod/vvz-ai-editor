# Step 11: core/db_driver/ — delete legacy driver package

## Target
`code_analysis/core/db_driver/` — entire directory (7 files, 1490 lines)

## Why this exists and why it must go

`db_driver/` is the **first-generation driver layer**, created before `database_driver_pkg/`
existed. It predates the full RPC architecture and was the original way `CodeDatabase`
talked to SQLite. Over time `database_driver_pkg/` was built as a proper RPC server
stack, but `db_driver/` was never cleaned up because `CodeDatabase` still depended on it.

### Files in the package

| File | Lines | Role |
|------|-------|------|
| `__init__.py` | 131 | `create_driver()` factory + `_DRIVERS` registry |
| `base.py` | 127 | `BaseDatabaseDriver` — **different interface** from `database_driver_pkg/drivers/base.py` |
| `sqlite.py` | 468 | `SQLiteDriver` — SQL-level driver (execute→void, fetchone, fetchall) |
| `sqlite_proxy.py` | 388 | `SQLiteDriverProxy` — early IPC-based proxy (predates RPCServer) |
| `sqlite_proxy_execute.py` | 211 | Execute/poll logic for the proxy |
| `sqlite_proxy_socket.py` | 106 | Socket communication for the proxy |
| `sqlite_proxy_worker.py` | 59 | Worker process entry point for the proxy |

### Why it is dead code after steps 01–10

The **only production consumer** of `db_driver/` is `CodeDatabase`, via:
```python
# code_analysis/core/database/base.py line 16
from ..db_driver import create_driver
```
`create_driver()` is called in `CodeDatabase.__init__` only.

After steps 01–10 eliminate all direct `CodeDatabase` usage from production code,
`CodeDatabase` itself becomes internal-only (driver layer + test fixtures). Once
`CodeDatabase.__init__` is no longer reachable from production paths, `db_driver/`
has zero live callers.

Other consumers found (non-production):
- `scripts/test_db_architecture.py` — script, not production
- `db_driver/__init__.py` itself imports `db_driver/base.py`, `db_driver/sqlite.py`, `db_driver/sqlite_proxy.py` — internal

### Interface incompatibility confirmed

`db_driver.BaseDatabaseDriver` and `database_driver_pkg.drivers.base.BaseDatabaseDriver`
are **unrelated classes** — no shared base, different method signatures:

| Method | `db_driver` | `database_driver_pkg` |
|--------|------------|----------------------|
| `execute()` | `(sql, params) → None` | `(sql, params, tid) → Dict` |
| `fetchone()` | `(sql, params) → Optional[Dict]` | not in interface |
| `fetchall()` | `(sql, params) → List[Dict]` | not in interface |
| `insert()` | not in interface | `(table, data) → DbIdentity` |
| `select()` | not in interface | `(table, where, ...) → List` |

`CodeDatabase` bridges them via `_invoke_driver_execute` which catches `TypeError`
to handle the extra `transaction_id` argument — a classic compatibility shim.

`CodeDatabase` bridges them via `_invoke_driver_execute` which catches `TypeError`
to handle the extra `transaction_id` argument — a classic compatibility shim.

---

## ⚠️ CRITICAL: CodeDatabase.__init__ must be rewritten before deleting db_driver/

**Problem:** `core/database/base.py:16` imports `from ..db_driver import create_driver`.
`CodeDatabase.__init__` at line 137 calls `self.driver = create_driver(driver_type, driver_cfg)`.
Deleting `db_driver/` while this import and call remain causes `NameError` at runtime.

**The two `create_driver` factories are NOT drop-in replacements:**

| Aspect | `db_driver.create_driver` (legacy) | `database_driver_pkg.driver_factory.create_driver` (new) |
|--------|-----------------------------------|--------------------------------------------------------|
| Supported types | `sqlite`, `sqlite_proxy` | `sqlite`, `postgres` |
| `sqlite_proxy` support | ✅ yes | ❌ NO |
| `postgres` support | ❌ NO | ✅ yes |
| Returned driver interface | `_execute→void`, `_fetchone`, `_fetchall` | `execute→Dict`, `insert`, `select` |
| `BaseDatabaseDriver` class | `db_driver/base.py` (legacy) | `database_driver_pkg/drivers/base.py` (unrelated) |

Consequence: `CodeDatabase` mixins (`_execute`, `_fetchall`, `_commit`) are built on the legacy
interface. Simply swapping the factory call crashes `CodeDatabase` internals.

**Required action before deleting db_driver/: choose one approach.**

### Approach A — Rewrite `CodeDatabase.__init__` (recommended for PostgreSQL support)

Replace `from ..db_driver import create_driver` with the new factory.
Rewrite `_invoke_driver_execute`, `_execute`, `_fetchone`, `_fetchall`, `_commit` methods
to call `self.driver.execute(sql, params)` and extract results from the returned dict.
This makes `CodeDatabase` work with both `SQLiteDriver` and `PostgreSQLDriver`.
Scope: medium effort. Tests continue to use `CodeDatabase(driver_config)` — no test migration.

### Approach B — Delete CodeDatabase entirely

If tests are migrated to use `DatabaseClient` directly (or raw driver fixtures),
`CodeDatabase` can be deleted in full. This eliminates the mixin layer entirely.
Scope: large effort (≈30 test fixtures need migration). Architecturally cleaner.

**Executor MUST stop and consult user before starting step 11.**
**Do NOT attempt to delete db_driver/ without completing whichever approach is chosen.**

---

## Depends on: steps 01–10 all complete + full reindex test passing

## Pre-deletion checklist

Before deleting, verify:
1. `grep -r 'db_driver' code_analysis/ --include='*.py' | grep -v 'database_driver_pkg' | grep -v 'test_'`
   → must return only `core/database/base.py` (CodeDatabase) and `core/db_driver/` itself
2. `grep -r 'from.*db_driver' code_analysis/ --include='*.py'`
   → same: only `database/base.py` and internal `db_driver/` files
3. Full reindex test: `update_indexes(project_id=...)` → `functions > 0`, `cst_node_id != ""`
4. `comprehensive_analysis` — no new errors after steps 01–10
5. `pytest tests/ -x` — all tests pass

## What to delete

Use `delete_files_by_mask` to soft-delete the entire directory:

```
delete_files_by_mask(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    path_mask="code_analysis/core/db_driver/**",
    reason="Legacy first-generation driver stack. Sole consumer CodeDatabase eliminated in steps 01-10."
)
```
Then rewrite `CodeDatabase` to eliminate the `db_driver` dependency
(per Approach A or B chosen above). At minimum:

**Approach A minimum changes to `database/base.py`:**
1. Replace `from ..db_driver import create_driver` with:
   ```python
   from ..database_driver_pkg.driver_factory import create_driver as _new_create_driver
   ```
2. Rewrite `CodeDatabase.__init__` to call `_new_create_driver(driver_type, driver_cfg)`.
3. Update `_invoke_driver_execute`, `_execute`, `_fetchone`, `_fetchall`, `_commit`
   to use the new driver interface (`execute()→Dict`, extract `result.get('data', [])`). 
4. Re-run `type_check_code` on `database/base.py` — must pass cleanly.

**Note on `sqlite_proxy`:** The new factory does NOT support `sqlite_proxy`.
If any caller still passes `driver_type='sqlite_proxy'`, it will raise `DriverNotFoundError`.
After steps 01–10, `CodeDatabase` is only instantiated by tests (which use `sqlite`).
Verify no live `sqlite_proxy` usage via `grep` before proceeding.
from ..db_driver import create_driver
```

## What NOT to delete

- `core/database_driver_pkg/` — current driver stack, keep
- `scripts/test_db_architecture.py` — update it to use `database_driver_pkg` or delete separately

## Validation

1. `type_check_code(file_path="code_analysis/core/database/base.py")` — must pass without `db_driver` import
2. `lint_code` on all changed files
3. Server restart + full reindex test
4. `pytest tests/ -x`

## Risk: MEDIUM (elevated from original LOW)

The directory deletion itself is low risk once `db_driver/` has no live callers.
The elevated risk comes from the required `CodeDatabase.__init__` rewrite:
- Approach A: medium rewrite of internal mixin adapter methods.
- Approach B: large-scale test fixture migration.
Incorrect rewrite of `CodeDatabase` internals will break all tests that instantiate it.
Always run `pytest tests/ -x` after the rewrite, before deleting `db_driver/`.