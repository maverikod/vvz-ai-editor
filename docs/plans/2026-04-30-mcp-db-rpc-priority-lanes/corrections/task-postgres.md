# Task: postgres.py — audit and fix

**File:** `code_analysis/core/database_driver_pkg/drivers/postgres.py`
**Lines:** 516 (EXCEEDS 400 limit — plan for split)
**Plan steps:** 2 (pool integration), 2a (lock removal), 5 (transactions), 6 (observability)

---

## Issues found

### 1. File exceeds 400-line limit (VIOLATION)

At 516 lines the file violates the project's 400-line rule (`docs/PROJECT_RULES.md`).
The class `PostgreSQLDriver` alone is 416 lines (101–516).

**Fix:** Extract retry logic (`_run_once_with_reconnect_on_lost`, `_run_self_managed_with_retry`,
`_rollback_self_managed_before_retry`, `_sleep_before_retry`) into a separate module
`postgres_retry.py` or a mixin. This removes ~65 lines.
Alternatively, extract CRUD proxy methods (`insert`, `update`, `delete`, `select`,
`create_table`, `drop_table`, `get_table_info`, `sync_schema`) — they are thin
wrappers around `_operations` / `_schema_manager`.

### 2. _reconnect_main destroys and rebuilds pool — no partial recovery

`_reconnect_main()` (lines 209–228) calls `self._pool.close_all()` and creates a
brand new `PostgreSQLConnectionPool`. This means:
- All 5 connections are torn down even if only the main `self.conn` was lost.
- Any threads currently waiting on pool acquire will get `DriverConnectionError`
  ("pool is closed") after `close_all()` calls `notify_all()`.

**Plan reference:** step 2: "Учесть _reconnect_main: при потере основного conn логика
пула и операций должна оставаться согласованной".

**Concern:** This is not strictly wrong (it's the safe path), but the plan explicitly
asks to consider this. Document the choice in a comment or ADR note.

### 3. _rollback_self_managed_before_retry skips pool rollback

Method `_rollback_self_managed_before_retry` (lines 285–295) does:
```python
if self._pool is not None:
    return   # <-- skips rollback entirely when pool exists
```
The comment says "pool rolls back leased conn" — this relies on `acquire()` context
manager's `except BaseException` branch doing `conn.rollback()`. This is correct
behavior, but the method name is misleading. When pool exists, it's a no-op.

**Fix:** Rename to `_rollback_main_before_retry` or add a clear docstring explaining
that pool-managed retries handle rollback in the context manager, not here.

### 4. self.conn still used alongside pool — role unclear

After pool introduction, `self.conn` is still created in `connect()` and used in
`_operations`, `_schema_manager`, `commit()`, `rollback()`.
The pool has its own 5 connections. So `self.conn` is the 6th connection.

**Concern:** The plan says "ровно 5 соединений" (exactly 5). With `self.conn`
there are actually 6 connections total. This may be intentional (main conn for
schema sync, transactions via `_transaction_manager`, while pool handles self-managed
execute/execute_batch), but it's not documented.

**Fix:** Add a comment block in `connect()` documenting the connection topology:
"Main conn: schema ops, commit/rollback for local transactions.
Pool (5 conn): self-managed execute/execute_batch via acquire().
Transaction manager: creates additional connections per begin_transaction()."

### 5. QA injection methods add noise to production class

`qa_set_db_retry_injections` and `_qa_maybe_inject_transient` (lines 117–137)
are test-only. Consider extracting to a QA mixin if file size is being reduced.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. `pytest tests/test_postgres_connection_pool.py tests/test_postgres_execute_lane.py -v`
3. Verify file is ≤400 lines after extraction
4. `comprehensive_analysis` on file and new extracted module
