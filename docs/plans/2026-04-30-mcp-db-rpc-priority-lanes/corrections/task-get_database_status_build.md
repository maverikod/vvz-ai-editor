# Task: get_database_status_build.py — audit and fix

**File:** `code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py`
**Lines:** 426 (EXCEEDS 400 limit)
**Plan steps:** 6 (observability)

---

## Issues found

### 1. File exceeds 400-line limit (VIOLATION)

At 426 lines, marginally over the limit.

**Fix:** Extract `_postgres_pool_observability_fields()` (lines 192–211) and
related helper `build_status_ops()` (lines 44–185) into a separate module,
e.g. `get_database_status_ops.py`. This removes ~170 lines from the main file.

### 2. Pool observability is implemented correctly ✅

`_postgres_pool_observability_fields()` (lines 192–211):
- Navigates `db.rpc_client.handlers.driver` chain correctly
- Checks `isinstance(driver, PostgreSQLDriver)` before calling `pool_status()`
- Exports `pg_write_pool_in_use` and `pg_read_pool_in_use` fields

This matches plan step 6 requirements. However, fields `pg_write_pool_idle` and
`pg_read_pool_idle` are NOT exported — only `in_use` is.

**Fix (minor):** Add idle counts and waiter counts (once pool implements them):
```python
if "idle" in w:
    out["pg_write_pool_idle"] = w["idle"]
if "waiters" in w:
    out["pg_write_pool_waiters"] = w["waiters"]
```

### 3. STATUS_OPS is hardcoded to "sqlite_proxy" (line 189)

```python
STATUS_OPS: List[tuple] = build_status_ops("sqlite_proxy")
```
This module-level constant is built for SQLite dialect only. When used by
Postgres in-process, `build_database_status_result()` receives `driver_type`
and calls `build_status_ops()` again (check this). If it doesn't, the wrong
SQL dialect will be used for status queries.

**Fix:** Verify that `build_database_status_result()` calls `build_status_ops(driver_type)`
dynamically and does not rely on the module-level `STATUS_OPS` constant for Postgres.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. Verify file is ≤400 lines after extraction
3. `comprehensive_analysis` on file
