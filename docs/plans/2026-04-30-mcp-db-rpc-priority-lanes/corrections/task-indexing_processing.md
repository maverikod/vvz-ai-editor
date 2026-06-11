# Task: processing.py (indexing_worker) — audit and fix

**File:** `code_analysis/core/indexing_worker_pkg/processing.py`
**Lines:** 622 (EXCEEDS 400 limit — SEVERELY)
**Plan steps:** 3 (tag indexing_worker)

---

## Issues found

### 1. File severely exceeds 400-line limit (CRITICAL VIOLATION)

At 622 lines, this is 56% over the 400-line limit. The single function
`process_cycle` is 561 lines (62–622) with deeply nested try/except/for blocks.

**Fix:** Extract into separate functions:
- `_ensure_database_connection(...)` — lines ~113–160 (DB connect/reconnect logic)
- `_run_indexing_cycle(...)` — lines ~180–540 (one cycle: discover projects, batch files, index)
- `_process_project_batch(...)` — lines ~280–500 (per-project file loop)
- `_finalize_cycle_stats(...)` — lines ~520–570 (update stats, end cycle)

Each function should be ≤100 lines. The outer `while not self._stop_event.is_set()`
loop stays in `process_cycle` but delegates to extracted functions.

### 2. Priority tagging is DONE correctly ✅

`_INDEXING_WORKER_DB_RPC_PRIORITY = 1` is defined (line 43) and used consistently
in all `database.execute()`, `database.execute_batch()`, `database.index_file()`,
`try_acquire_project_activity()`, `heartbeat_project_activity()`, and
`release_project_activity()` calls.

No missing priority tags found. Mark step 3 as DONE.

### 3. SELECT 1 health check without priority (line 120)

```python
database.execute("SELECT 1", None)
```
This connectivity check does not pass `priority`. It runs at default priority=0,
which is correct — it's a diagnostic probe, not background work. No fix needed,
but document the intentional choice.

### 4. julianday('now') in SQL — not portable to PostgreSQL

Multiple SQL statements use `julianday('now')` (lines 188, 219, 536, etc.).
This is SQLite-only syntax. For PostgreSQL, `EXTRACT(EPOCH FROM NOW())` or
the project's `sql_julian_timestamp_now_expr()` should be used.

**Check:** `sql_julian_timestamp_now_expr(database)` IS used on line 466 for
error insertion. But the stats queries on lines 188, 219, etc. use literal
`julianday('now')`. If indexing_worker runs against PostgreSQL, these will fail.

**Fix:** Replace all raw `julianday('now')` with `sql_julian_timestamp_now_expr(database)`
or the project's portable equivalent for timestamp operations.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. Verify each resulting file is ≤400 lines
3. `comprehensive_analysis` on all resulting files
4. Test with `pytest tests/ -k indexing` if indexing-related tests exist
