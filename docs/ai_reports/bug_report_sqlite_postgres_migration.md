# Bug Report: Incomplete SQLite → PostgreSQL Migration

**Date:** 2026-04-29  
**Found by:** Claude (code_analysis session)  
**Severity:** CRITICAL — blocks `cst_save_tree`, `cst_apply_buffer`, all CST write operations  
**Status:** Open  

---

## Summary

During the migration from SQLite to PostgreSQL, several critical compatibility issues were left unresolved. These cause systematic failures in the DB sync layer after every CST file save, blocking all code editing through MCP. Additionally, `view_worker_logs` blocks the async event loop on large log files, causing server crashes.

---

## Bug 1 — CRITICAL: `cst_save_tree` always fails on DB sync

**Error:**
```
Failed to sync file to DB: execute_batch failed:
  invalid input syntax for type integer: "8a16d627-f423-4f1b-910c-c621e3d90885"
  CONTEXT: unnamed portal parameter $1 = '...'
```

**Trigger:** Any call to `cst_save_tree` or `cst_apply_buffer` with `apply=true`.

**Root cause:** During the SQLite→Postgres migration, `file_id` (formerly INTEGER autoincrement PK) may now be a UUID in Postgres. However, the DB sync path `tree_saver.py` → `execute_batch` still passes a UUID string where a SQL column typed as `INTEGER` is expected.

**Evidence:**
- `unnamed portal parameter $1` — psycopg3 value type mismatch.
- `build_file_data_atomic_batches(file_id: int, ...)` — typed as `int`, receives UUID string at runtime.
- `get_entity_dependencies` returns same error — confirms systemic problem.
- 45 call sites of `execute_batch` identified across codebase.

**Key files:**
- `core/cst_tree/tree_saver.py` — `sync_file_to_db_atomic`
- `core/database_client/file_data_batch.py` — `build_file_data_atomic_batches(file_id: int, ...)`
- `commands/compose_cst_db.py` — `backup_file_data(file_id: int)`
- `core/database_driver_pkg/rpc_handlers_schema.py:317` — `handle_execute_logical_write_operation`

**Fix direction:**
1. Audit `tree_saver.py` — where `file_id` is fetched; returns UUID string in Postgres mode, but typed as `int` everywhere downstream.
2. Either update `file_id: int` → `str | int` with SQL cast, OR confirm `files` table still uses integer PK.
3. Run `test_driver_sqlite_batch.py` suite against Postgres driver.

---

## Bug 2 — CRITICAL: `INSERT OR REPLACE` SQLite syntax in Postgres restore path

**Location:** `commands/compose_cst_db.py` — `_restore_entities()`, `_restore_metadata()`, `_restore_trees()`

**Code (confirmed from AST):**
```python
database.execute(
    'INSERT OR REPLACE INTO classes (id, file_id, ...) VALUES (?, ?, ...)', ...
)
```

**Root cause:** `INSERT OR REPLACE` is SQLite-only. PostgreSQL requires `INSERT INTO ... ON CONFLICT (id) DO UPDATE SET ...`.

**Impact:** When `cst_save_tree` fails and tries to rollback by restoring from backup, the restore also fails on Postgres → data deleted + restore failed = **data loss**.

**Fix direction:** Replace all `INSERT OR REPLACE` with `ON CONFLICT` syntax, or route through existing `core/sql_portable.py`.

---

## Bug 3 — CRITICAL: `syntax error at or near "OR"` on `watch_dirs` init

**Error (from logs, 2026-04-23T15:04:50):**
```
Failed to initialize watch_dirs: Failed to execute SQL: syntax error at or near "OR"
```

**Trigger:** Server startup — `file_watcher` worker initialization.

**Root cause:** `INSERT OR IGNORE` in `watch_dirs` init query — SQLite-only syntax, fails on Postgres.

**Impact:** `file_watcher` fails to initialize `watch_dirs` on every server start → `errors: 1256` per scan cycle (confirmed: `[CYCLE #2] errors: 1256` in current session).

**Fix direction:** Search `INSERT OR IGNORE` in `file_watcher_pkg/` → replace with `INSERT INTO ... ON CONFLICT DO NOTHING`.

---

## Bug 4 — HIGH: `column "cnt" does not exist` in vectorization worker

**Error (recurring every ~38 seconds since 2026-04-23):**
```
Error processing project c86dded6 (vast_srv):
  Failed to execute SQL: column "cnt" does not exist
  File: batch_processor.py:216, in process_chunks_missing_embedding_params
```

**Root cause:** SQL query uses alias `cnt` and references it in outer WHERE/HAVING. SQLite allows alias forward-references; PostgreSQL does not.

```sql
-- SQLite: works
SELECT count(*) AS cnt FROM chunks WHERE ... HAVING cnt > 0
-- Postgres: fails — cnt not visible at same SELECT level
-- Fix: wrap in subquery
SELECT * FROM (SELECT count(*) AS cnt ...) sub WHERE sub.cnt > 0
```

**Impact:** Vectorization for `vast_srv` (c86dded6) permanently fails every cycle. Project stuck at 76.21% vectorized and never progresses.

**Fix direction:** Open `batch_processor.py` ~line 216, wrap query using `cnt` alias in outer subquery.

---

## Bug 5 — HIGH: `view_worker_logs` blocks async event loop on large log files

**Root cause (confirmed from AST analysis):**
```python
# log_viewer_utils.py
def read_log_lines(path: Path) -> List[str]:
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()   # synchronous, entire file into RAM

# log_viewer_command.py
async def execute(self):
    lines: List[str] = []
    for p in files_to_read:
        lines.extend(read_log_lines(p))  # blocking I/O in async context
    for line in lines:   # iterates 35M lines in event loop without yield
        ...
```

**Impact:** `mcp_server.log` is 35M+ lines. `view_worker_logs` with `log_id=mcp_server` blocks event loop 30–120 seconds:
- Server stops responding to heartbeat → proxy unregisters (`SERVER_NOT_FOUND`)
- Crash triggered **3 times in current session**

**Fix direction (agreed with user — chunked reading + pagination):**
1. Add to `core/constants.py`: `DEFAULT_LOG_VIEW_CHUNK_SIZE = 262144`, `DEFAULT_LOG_VIEW_WINDOW_BYTES = 2097152`, `DEFAULT_LOG_VIEW_LIMIT = 1000`, `DEFAULT_LOG_VIEW_MAX_LIMIT = 5000`
2. Add optional `log_view` section to `ServerConfig` in `config_server.py`
3. Replace `read_log_lines` with `iter_log_chunks(path, offset, window_bytes, chunk_size)` using `asyncio.to_thread`
4. Add `offset` / `window` / `next_offset` / `has_more` to command schema and metadata

**Note:** Implementation blocked by Bug 1 — `cst_save_tree` fails on DB sync, so constants cannot be saved to the project.

---

## Bug 6 — MEDIUM: `get_entity_dependencies` passes UUID as integer

**Error:**
```
Failed to execute SQL: invalid input syntax for type integer: "c83ef244-..."
```

**Impact:** Command always fails with UUID entity_id — the only format returned by `cst_find_node` / `list_cst_blocks`. Effectively broken post-migration.

**Fix direction:** Same root as Bug 1 — audit entity_id type handling across the migration.

---

## Common Root Cause

Bugs 1–4 and 6 share the same root: **SQLite → PostgreSQL migration was done partially**. The DB driver was switched (`database_driver: postgres` in config), but:

1. **SQL dialect not updated:** `INSERT OR REPLACE` / `INSERT OR IGNORE` not converted to `ON CONFLICT`
2. **Type annotations not updated:** `file_id: int` throughout, but Postgres may now return UUID strings from `files.id`
3. **SQL alias scoping not fixed:** subquery aliases not wrapped in outer SELECT per SQL standard
4. **No integration tests against Postgres:** only `test_driver_sqlite_batch.py` exists

**Recommended fix order:**

| Priority | Bug | Impact |
|----------|-----|--------|
| 1 | Bug 3 — watch_dirs OR syntax | Stops 1256 errors/cycle, unblocks file_watcher |
| 2 | Bug 4 — `cnt` alias | Unblocks vast_srv vectorization |
| 3 | Bug 1 + 2 — file_id type + INSERT OR REPLACE | Unblocks all CST write operations |
| 4 | Bug 6 — entity_id type | Unblocks get_entity_dependencies |
| 5 | Bug 5 — async log reading | Independent, implement after CST writes work |

---

## Files Requiring Changes

| File | Bug | Change |
|------|-----|--------|
| `core/cst_tree/tree_saver.py` | 1 | Audit `file_id` type: int vs UUID |
| `core/database_client/file_data_batch.py` | 1 | `file_id: int` → `str | int` |
| `commands/compose_cst_db.py` | 1, 2 | `file_id` annotation; `INSERT OR REPLACE` → ON CONFLICT |
| `core/database_driver_pkg/rpc_handlers_schema.py` | 1 | Trace UUID→int mismatch |
| `core/vectorization_worker_pkg/batch_processor.py` | 4 | Fix `cnt` alias ~line 216 |
| `core/file_watcher_pkg/` (watch_dirs init) | 3 | `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING` |
| `commands/log_viewer_utils.py` | 5 | `read_log_lines` → chunked async generator |
| `commands/log_viewer_command.py` | 5 | Async chunked read + offset pagination |
| `commands/log_viewer_mcp_commands/view_worker_logs.py` | 5 | Add offset/window params to schema |
| `commands/log_viewer_mcp_commands/view_worker_logs_metadata.py` | 5 | Update metadata |
| `core/constants.py` | 5 | Add `DEFAULT_LOG_VIEW_*` constants |
| `core/config_server.py` | 5 | Add `log_view` section to `ServerConfig` |
| `commands/ast/entity_dependencies.py` | 6 | Fix entity_id type |
