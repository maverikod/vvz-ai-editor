# Task: postgres_connection_pool.py — audit and fix

**File:** `code_analysis/core/database_driver_pkg/drivers/postgres_connection_pool.py`
**Lines:** 141 (within limit)
**Plan steps:** 2 (pool), 6 (observability), 7 (tests)

---

## Issues found

### 1. No timeout on acquire() — potential deadlock (CRITICAL)

Method `acquire()` calls `self._cond.wait()` with no timeout.
If all 3 write connections are held indefinitely (e.g. long-running index_file),
a new write request will block forever with no way to detect starvation.

**Plan reference:** "Ожидание при полном пуле: блокировка на получении conn — внутри драйвера"; "Starvation / fairness — при необходимости max wait в драйвере".

**Fix:** Add a configurable `max_wait_seconds` parameter (e.g. 30s default) to `__init__`.
In `acquire()`, replace:
```python
self._cond.wait()
```
with:
```python
self._cond.wait(timeout=self._max_wait_seconds)
```
After wait returns, re-check slot availability; if still all busy — raise
`DriverOperationError("Pool acquire timeout: all {lane} connections busy for {max_wait_seconds}s")`.

### 2. No waiter count in snapshot() — observability gap

The `snapshot()` method reports `in_use` and `idle` per lane but does not report
how many threads are currently waiting to acquire a connection.

**Plan reference:** step 6: "при необходимости — длина очереди ожидания conn в драйвере".

**Fix:** Add `self._write_waiters: int = 0` and `self._read_waiters: int = 0` counters,
increment before `self._cond.wait()`, decrement after (in `finally`). Include in `snapshot()`:
```python
"write": { ..., "waiters": self._write_waiters },
"read": { ..., "waiters": self._read_waiters },
```

### 3. Connection health check missing (LOW PRIORITY)

Pool creates connections in `__init__` and never validates they are alive before lending.
If a connection drops (network flap, PG restart), `acquire()` hands out a dead connection.
`PostgreSQLDriver._reconnect_main` rebuilds entire pool on main conn loss, but
individual pool connections have no liveness check.

**Fix (optional):** Add `conn.execute('SELECT 1')` inside acquire() context before yielding.
On failure — close conn, open new one, re-initialize slot. Document risk if not implementing.

### 4. No logging inside acquire() — debugging blind spot

When all slots are busy and a thread blocks, there is zero log output.
For diagnosing production hangs this is critical.

**Fix:** Add:
- `logger.debug("Pool acquire(%s) waiting — all %d slots busy", lane, pool_size)` before wait
- `logger.debug("Pool acquire(%s) got slot %d in %.3fs", lane, idx, elapsed)` after acquiring

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. `pytest tests/test_postgres_connection_pool.py -v`
3. Add test: `test_acquire_timeout_raises` — hold all write slots, verify 4th caller gets timeout error
4. Add test: `test_snapshot_reports_waiters` — verify snapshot shows waiter count > 0 while blocked
5. `comprehensive_analysis` on file
