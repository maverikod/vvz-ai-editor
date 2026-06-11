# Task: `postgres.py` — `_reconnect_main` destroys pool under active threads

**Finding:** F-02 from AUDIT_SUMMARY_2.md
**File:** `code_analysis/core/database_driver_pkg/drivers/postgres.py`
**Severity:** Medium (data loss risk under reconnection)
**Phase:** 1
**Lines:** ~225-250 (`_reconnect_main`)

---

## Context

PostgreSQL driver has a multi-threaded architecture:
- **Main connection** (`self.conn`): used by schema manager, operations, `commit`/`rollback`
- **Pool** (3W+2R via `PostgreSQLConnectionPool`): used by `execute`/`execute_batch` self-managed path
- Multiple threads call `execute`/`execute_batch` concurrently through the pool

When main `self.conn` is lost (network error, PG restart), `_reconnect_main()` is called
from `_run_once_with_reconnect_on_lost`.

## Problem

Current `_reconnect_main` (lines ~225-250):
```python
def _reconnect_main(self) -> None:
    if self._pool:
        self._pool.close_all()    # ← kills ALL 5 pool connections immediately
        self._pool = None
    if self.conn:
        self.conn.close()
    self.conn = psycopg.connect(**self._connect_kwargs)
    # ... rebuild managers ...
    self._pool = PostgreSQLConnectionPool(
        self._connect_kwargs, max_wait_seconds=self._pool_max_wait_seconds
    )
```

**Issues:**
1. `pool.close_all()` sets `_closed=True` and wakes all waiters with `DriverConnectionError`.
   Threads currently waiting in `acquire()` get an exception.
2. Threads that already hold a leased connection from the OLD pool may still be executing SQL.
   Their connection object was closed by `close_all()` — the next cursor operation will fail
   with a psycopg error, not a clean `DriverConnectionError`.
3. The new pool is created with fresh connections, but old threads still reference the old
   (now destroyed) pool's connection objects.
4. `_run_once_with_reconnect_on_lost` catches connection-lost errors on `self.conn` path,
   but pool connections that die simultaneously are not handled — they raise raw psycopg errors.

## Task

Improve `_reconnect_main` to handle concurrent pool users gracefully:

1. **Mark old pool as draining** instead of immediately closing all connections.
   Option: set a flag that prevents new `acquire()` calls but lets active leases finish.
   After a brief drain timeout (e.g. 2-5s), force-close remaining connections.

2. **Alternative (simpler):** Accept the current behavior (immediate close) but document it
   explicitly. Add a log warning when pool is destroyed while connections are busy:
   ```python
   snap = self._pool.snapshot()
   busy = snap["write"]["in_use"] + snap["read"]["in_use"]
   if busy > 0:
       logger.warning("_reconnect_main: closing pool with %d active connections", busy)
   ```

3. **Ensure retry path covers pool connections:** When a pool connection gets a connection-lost
   error, the `acquire()` context manager does `conn.rollback()` which will also fail, then
   raises `DriverOperationError`. The caller (`_run_self_managed_with_retry`) should recognize
   this as a retryable error and trigger `_reconnect_main` if not already in progress.

## What NOT to do

- Do NOT add queue/scheduling logic to this file
- Do NOT move pool management to the universal layer
- Do NOT change the 3W+2R topology
- Keep changes within `_reconnect_main` and `_run_once_with_reconnect_on_lost`

## Acceptance criteria

- [ ] `_reconnect_main` logs when destroying pool with active connections
- [ ] Decision documented: immediate close (with justification) or drain timeout
- [ ] `_run_self_managed_with_retry` correctly handles pool-connection-lost errors
- [ ] File stays under 400 lines (currently 539 — already over; do not increase)
