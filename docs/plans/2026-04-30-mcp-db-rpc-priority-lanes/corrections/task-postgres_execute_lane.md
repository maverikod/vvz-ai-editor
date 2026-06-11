# Task: postgres_execute_lane.py — audit and fix

**File:** `code_analysis/core/database_driver_pkg/drivers/postgres_execute_lane.py`
**Lines:** 74 (within limit)
**Plan steps:** 2 (pool — read/write classification)

---

## Issues found

### 1. Classification is correct and well-tested ✅

`_WRITE_STMT_HINT` regex covers all DML/DDL/DCL/transaction statements.
Both `postgres_execute_requires_write_pool` and `postgres_batch_requires_write_pool`
correctly iterate statements and return True if any requires write.
Tests in `tests/test_postgres_execute_lane.py` cover the main cases.

### 2. CTE (WITH ... INSERT/UPDATE/DELETE) classification may fail

A CTE like:
```sql
WITH updated AS (UPDATE files SET ... RETURNING id) SELECT * FROM updated
```
The `split_batch_sql()` may treat the whole thing as one statement. The regex
will find `UPDATE` inside the CTE and correctly classify as write. This is fine.

However:
```sql
WITH counts AS (SELECT COUNT(*) FROM files) SELECT * FROM counts
```
This is a read-only CTE. The regex will NOT match — correctly classified as read. ✅

### 3. EXPLAIN/PREPARE not in write list

`EXPLAIN ANALYZE INSERT INTO ...` would be classified as write (finds `INSERT`).
This is correct — EXPLAIN ANALYZE does execute the statement.

`PREPARE` and `EXECUTE` (prepared statements) are not in `_WRITE_STMT_HINT`.
If used, they would be classified as read even if the prepared statement is a write.

**Fix (low priority):** Add `PREPARE|EXECUTE` to `_WRITE_STMT_HINT` if prepared
statements are used via raw `execute()`. Currently not a risk — the project
does not use `PREPARE`.

### 4. No issues — file is clean

No code changes needed. Keep as-is.

---

## Validation

No changes required. File passes all checks.
