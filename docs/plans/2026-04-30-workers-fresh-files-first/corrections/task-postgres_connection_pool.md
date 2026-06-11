# Task: `postgres_connection_pool.py` — stale connections and autocommit

**Findings:** F-03, F-04 from AUDIT_SUMMARY_2.md
**File:** `code_analysis/core/database_driver_pkg/drivers/postgres_connection_pool.py`
**Severity:** Medium (F-03: stale conn), Low (F-04: implicit txn on reads)
**Phase:** 1

---

## Context

The pool holds exactly 5 psycopg connections (3 write, 2 read). Connections are created at
`__init__` time and reused indefinitely. The pool is thread-safe with `threading.Lock` +
`Condition`. `acquire()` is a context manager that yields a connection and releases on exit.

Current pool size: 186 lines — well under 400 limit.

---

## F-03: No pool connection health check

**Problem:** Pool connections are created once in `__init__` and never validated.
If a connection goes stale (causes: PG `idle_in_transaction_session_timeout`, PG restart,
network partition, TCP keepalive timeout), `acquire()` hands out a dead connection.
The caller gets a raw psycopg error (e.g. `OperationalError: server closed the connection`)
instead of a clean retry.

**Current code** (`acquire`, lines ~108-170):
```python
@contextmanager
def acquire(self, *, write: bool) -> Iterator[Any]:
    # ... find first free slot ...
    yield conn          # ← conn may be stale, no validation
```

**Fix options (pick one):**

**Option A — ping before yield (simple, slight overhead):**
```python
# After finding free slot, before yield:
try:
    conn.execute("SELECT 1")
except Exception:
    # Connection stale — replace it
    try:
        conn.close()
    except Exception:
        pass
    conn = psycopg.connect(**self._connect_kwargs)
    conn.autocommit = False  # or True, see F-04
    conns[idx] = conn
```
Overhead: ~0.1ms per acquire on a healthy connection. Acceptable for a pool of 5.

**Option B — catch-and-replace on failure (no overhead, more complex):**
Let the caller hit the error. In the `except` block of `acquire()` context manager,
detect connection-lost errors and replace the stale connection in the pool before
re-raising. This avoids the ping overhead but makes error handling more complex.

**Recommendation:** Option A for simplicity. The pool is small (5 connections);
a `SELECT 1` ping per acquire is negligible.

---

## F-04: `autocommit=False` on read-pool connections

**Problem:** All pool connections (including 2 read-pool) have `autocommit=False`.
A read-only SELECT on the read pool opens an implicit PG transaction. The `acquire()`
context manager only calls `rollback()` on exception. On success, the implicit
transaction stays open until the connection is next acquired, holding:
- MVCC snapshot (preventing vacuum of old row versions)
- Lightweight locks (if any)

**Current code** (`__init__`, lines ~60-68):
```python
for _ in range(self.WRITE_POOL_SIZE):
    c = psycopg.connect(**connect_kwargs)
    c.autocommit = False                    # write pool — correct
    self._write_conns.append(c)
for _ in range(self.READ_POOL_SIZE):
    c = psycopg.connect(**connect_kwargs)
    c.autocommit = False                    # read pool — should be True?
    self._read_conns.append(c)
```

**Fix options:**

**Option A (recommended):** Set `autocommit=True` on **read-pool** connections only.
Read-only SELECTs don't need transactions. This avoids holding MVCC snapshots
between acquires. Write-pool stays `autocommit=False` (needs explicit commit).

**Option B:** Keep `autocommit=False` but add explicit `conn.commit()` or
`conn.rollback()` after every successful read in the `acquire()` finally block.
This closes the implicit transaction but adds overhead.

**Option C:** Keep as-is and document the trade-off. If MCP reads are fast and
the pool is small, the held snapshots are short-lived and may be acceptable.

**Recommendation:** Option A. Read pool should not hold implicit transactions.

---

## What NOT to do

- Do NOT change pool topology (3W+2R)
- Do NOT add priority/scheduling logic to the pool — that's not its job
- Do NOT move pool to universal layer

## Acceptance criteria

- [ ] Pool connections are validated before use (F-03) — ping or catch-and-replace
- [ ] Read-pool connections use `autocommit=True` or explicit commit after use (F-04)
- [ ] `snapshot()` still works correctly after changes
- [ ] Unit tests updated for new behavior
- [ ] File stays under 400 lines
