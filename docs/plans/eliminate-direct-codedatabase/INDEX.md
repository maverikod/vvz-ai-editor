# Eliminate Direct CodeDatabase — Step Index (v4, with parallelization map)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

**Parallelization, execution rules, and validation gates:**
see [PARALLELIZATION.md](PARALLELIZATION.md)


## Architecture (canonical)

```
Команда/Воркер
    ↓ (socket / in-process)
DatabaseClient          ←── UNIVERSAL DRIVER (client side)
    ↓ (RPC over socket)
RPCServer
    ↓
RPCHandlers(self.driver) ←─ UNIVERSAL DRIVER (server side, handler layer)
    ↓
BaseDatabaseDriver       ←─ SPECIFIC DRIVER (interface)
    ↓
SQLiteDriver / PostgreSQLDriver  ←─ SPECIFIC DRIVER (implementation)
```

**Rules derived from this schema:**
- Workers and commands → use only `DatabaseClient`
- `RPCHandlers` (inside driver process) → use only `self.driver.execute()`
- `RPCHandlers` CANNOT use `DatabaseClient` (recursive RPC)
- `RPCHandlers` CANNOT use `CodeDatabase` (bypasses RPC SQL adaptation)
- CLI/admin tools without running driver → use driver directly (acceptable exception)

**In-process shortcut (for indexing worker context):**
```
Indexing worker → SQLiteDriver() → RPCHandlers(driver) → InProcessRpcClient → DatabaseClient
```
This avoids network RPC while still going through the handler layer.
`InProcessRpcClient(handlers: RPCHandlers)` exists at `database_client/in_process_rpc_client.py:38`.
`DatabaseClient(rpc_client=ipc)` keyword-only param exists at `database_client/client.py:56`.

---

## db_driver/ — legacy artifact, will be deleted after this plan

The codebase has **two separate driver stacks**:

| Package | Interface style | Used by | Status |
|---------|----------------|---------|--------|
| `core/db_driver/` | SQL-level: `execute()` → void, `fetchone()`, `fetchall()`, `commit()` | `CodeDatabase` only, via `create_driver()` | **Legacy. Delete after CodeDatabase is gone.** |
| `core/database_driver_pkg/drivers/` | Table+SQL hybrid: `insert()`, `select()`, `execute()` → `Dict`, `execute_batch()` | RPC server, RPCHandlers, all new code | **Current. Use this.** |

**Why `db_driver/` is a костыль:**
- `db_driver/sqlite.py` guards itself with `os.getenv("CODE_ANALYSIS_DB_WORKER")` — classic sign of an awkward bypass layer
- `db_driver/sqlite_proxy*.py` is an early first-generation RPC implementation, predating `database_driver_pkg`
- `CodeDatabase.from_existing_driver()` already imports `RpcSQLiteDriver` from `database_driver_pkg` for isinstance-checks — the two stacks are already leaking into each other
- `BaseDatabaseDriver` in `db_driver/base.py` and in `database_driver_pkg/drivers/base.py` are **unrelated classes** with different interfaces

**Consequence of this plan:** once all `CodeDatabase` usages are eliminated (steps 01–10),
`db_driver/` has **zero production consumers** and can be deleted entirely.
This should be done as **step 11** after the full reindex test passes.

**Always import from `database_driver_pkg.drivers.sqlite`**, NOT from `db_driver.sqlite`.

---

## Execution order

| Step | Plan file | Target code file | Risk | Depends on | Correct strategy |
|------|-----------|-----------------|------|------------|------------------|
| 01 | [step-01](step-01-faiss-manager-sync.md) | `core/faiss_manager_sync.py` | LOW | — | Remove CodeDatabase branch, keep DatabaseClient |
| 02 | [step-02](step-02-faiss-manager-rebuild.md) | `core/faiss_manager_rebuild.py` | LOW | — | Remove CodeDatabase branches, keep DatabaseClient. **Bug fix: embed save** |
| 03 | [step-03](step-03-faiss-manager.md) | `core/faiss_manager.py` | LOW | 01, 02 | Remove CodeDatabase from type signatures, delete Union import |
| 04 | [step-04](step-04-config-cli-commands.md) | `cli/config_cli_commands.py` | LOW | — | CLI: SQLiteDriver + get_schema_definition() + driver.sync_schema(schema, backup_dir) |
| 05 | [step-05](step-05-main-workers.md) | `main_workers.py` | LOW | — | Init: SQLiteDriver/PostgreSQLDriver + get_schema_definition() + driver.sync_schema(). Branch on driver type |
| 06 | [step-06](step-06-vectorize-after-index.md) | `core/indexing_worker_pkg/vectorize_after_index.py` | MEDIUM | 10 | InProcessRpcClient(RPCHandlers(driver)) → DatabaseClient. `_vectorize` blocked until step 10 |
| 07 | [step-07](step-07-rpc-handlers-file-trash.md) | `core/database_driver_pkg/rpc_handlers_file_trash.py` | MEDIUM | — | STOP: choose Approach A (trash_standalone.py) or B (document exception). Trash has filesystem ops |
| 09 | [step-09](step-09-update.md) | NEW `core/database/files/update_standalone.py` | HIGH | — | Create standalone wrapper: InProcessRpcClient → DatabaseClient → analyze_file() |
| 08 | [step-08](step-08-rpc-handlers-index-file.md) | `core/database_driver_pkg/rpc_handlers_index_file.py` | HIGH | 09 | Handler: call update_file_data_via_driver(self.driver) |
| 10 | [step-10](step-10-update-vectorize.md) | extend `update_standalone.py` | MEDIUM | 09 | Add update_and_vectorize_via_driver + _vectorize_via_client |
| **11** | [step-11](step-11-delete-db-driver.md) | **`core/db_driver/` (entire package)** | LOW | 01–10 | **Delete legacy driver stack after full reindex test passes** |

**Note:** Steps 08 and 09 are swapped in execution — do 09 before 08.

---

| **11** | [step-11](step-11-delete-db-driver.md) | **`core/db_driver/` (entire package)** | **MEDIUM** | 01–10 + CodeDatabase rewrite | **STOP: choose Approach A or B for CodeDatabase.__init__ rewrite before deleting** |

| File | Layer | Correct DB access |
|------|-------|------------------|
| Vectorization worker | Команда/Воркер | DatabaseClient |
| Indexing worker | Команда/Воркер | DatabaseClient |
| `faiss_manager*.py` | Команда/Воркер | DatabaseClient |
| `main_workers.py` | Init (no driver yet) | SQLiteDriver/PostgreSQLDriver direct + get_schema_definition() |
| `cli/config_cli_commands.py` | Admin CLI (no driver) | SQLiteDriver direct + get_schema_definition() |
| `vectorize_after_index.py` | Команда/Воркер | InProcessRpcClient → DatabaseClient |
| `rpc_handlers_index_file.py` | Универсальный драйвер | update_file_data_via_driver(self.driver) |
| `rpc_handlers_file_trash.py` | Универсальный драйвер | Approach A: trash_standalone / Approach B: documented exception |
| `update_standalone.py` (new) | Универсальный драйвер | InProcessRpcClient → DatabaseClient → analyze_file() |
| `core/db_driver/` | **LEGACY** | Delete in step 11 |

---

## Rules for executor (Haiku model)

1. Execute steps in order: 01 → 02 → 03 → 04 → 05 → 07 → 09 → 08 → 10 → 06 → 11
2. Step 06: implement after step 10 (depends on `_vectorize_via_client` from step 10)
3. Step 07: **STOP, ask user to choose Approach A or B before implementing**
4. Step 11: delete `core/db_driver/` only after full reindex test passes (step 10 validation complete)
5. One step = one file change (step 11 exception: entire package deletion)
6. After each step: `lint_code` → `format_code` → `type_check_code`
7. After Phase 1 (steps 01–05) complete: `comprehensive_analysis` on all 5 changed files
8. After Phase 2 (step 07) complete: test trash operations
9. After Phase 3 (steps 09, 08, 10) complete: full reindex test
10. If any step fails: **STOP**, report error, wait for user decision
11. Use CST tools for all Python edits: `cst_load_file` → `cst_modify_tree` → `cst_save_tree`
12. **Before every `cst_modify_tree`: re-verify node_id via `cst_load_file` + `cst_find_node`.** Node IDs in step files were verified at time of writing but may change. Always use node_id as key, not line number.
13. Read source files before writing ANY SQL — never guess SQL
14. Use `universal_file_save` for markdown plan files
15. Use `create_text_file` for new markdown files
17. For `sync_schema()`: always pass both `schema_definition` and `backup_dir`. `backup_dir` is technically optional (default None) but must always be provided explicitly so backups are created. Use `get_schema_definition()` from `core/database/schema_definition.py`.
18. Always import `SQLiteDriver` from `database_driver_pkg.drivers.sqlite`, NOT from `db_driver.sqlite`.
19. **Step 11 only:** before deleting `db_driver/`, STOP and consult user to choose Approach A (rewrite CodeDatabase.__init__) or Approach B (delete CodeDatabase). Do NOT skip this step — see step-11-delete-db-driver.md for full details.