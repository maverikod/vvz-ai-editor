# Audit #2: Plan execution — mcp-db-rpc-priority-lanes

**Date:** 2026-05-01 (second pass)
**Plan:** `docs/plans/2026-04-30-mcp-db-rpc-priority-lanes/README.md`
**Previous audit:** `AUDIT_SUMMARY_1.md` (some findings corrected in code since)

---

## Architecture (verified)

- **PostgreSQL** — multi-threaded in-process: `InProcessRpcClient` → `process_rpc_request` → `PostgreSQLDriver` (connection pool 3W+2R). No subprocess, no queue. Multiple threads hit the pool concurrently.
- **SQLite** — single-threaded SQL execution in a **separate subprocess**: `RPCClient` → Unix socket → `RPCServer` (subprocess) → `RequestQueue` → single consumer thread → `SQLiteDriver`. The queue in subprocess **emulates** multi-threaded behavior for callers. Only one thread executes SQL.
- **Universal layer** (`DatabaseClient`, `client_operations`, `rpc_dispatch`) — pass-through only. Commands know nothing about pool/queue internals. All concurrency/scheduling logic lives in specific drivers.
- **No cross-contamination found**: PostgreSQL path has no queue/subprocess logic, SQLite path has no pool logic. The separation is clean.

---

## Phase 1 step completion

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| 1 | `priority` in `RPCRequest` | ✅ DONE | Field, to_dict/from_dict, tests |
| 2 | Pool 3W+2R | ✅ DONE | `postgres_connection_pool.py`, `max_wait_seconds=30`, snapshot() |
| 2a | Narrow InProcessRpcClient lock | ✅ DONE | Lock only for `_closed` check |
| 3 | Tag indexing_worker | ✅ DONE | Uses `BACKGROUND_WORKER_DB_RPC_PRIORITY` |
| 4 | Tag vectorization_worker | ✅ DONE | All files use shared constant (corrects Audit #1) |
| 5 | Transaction consistency | ✅ DONE | Explicit tid → dedicated conn, not pool |
| 6 | Observability | ✅ DONE | Exports in_use, idle, waiters for both lanes (corrects Audit #1) |
| 7 | Tests | ⚠️ PARTIAL | Unit tests exist. Missing: integration MCP+workers under PG load |

---

## Paradigm compliance ✅

No violations. Pool in driver, no queues in universal layer, SQLite subprocess untouched.

---

## Findings

### F-01 — `RPCRequest.priority` is dead code (BOTH paths)

The field is set by workers via `BACKGROUND_WORKER_DB_RPC_PRIORITY` and serialized to wire JSON.
But **no consumer reads it**:
- **PostgreSQL**: `rpc_dispatch.py` ignores `request.priority`. Pool does not use it for scheduling.
- **SQLite subprocess**: `rpc_server.py._priority_for_request()` classifies by `method`/`table_name` only. Does NOT read `request.priority`.

The field is cosmetic in both paths. Low risk but misleading to maintainers.

→ `task-rpc_protocol.md`, `task-rpc_dispatch.md`

### F-02 — `_reconnect_main` destroys pool under active threads

When main `self.conn` is lost, `_reconnect_main()` calls `pool.close_all()`, setting `_closed=True`.
Threads mid-`acquire()` get `DriverConnectionError`. Threads holding a leased connection from the OLD pool
may attempt to use an already-closed psycopg connection. No graceful drain.

→ `task-postgres.md`

### F-03 — No pool connection health check / stale connection detection

Pool connections are created at `connect()` time and never validated after. If a pool connection
goes stale (PG `idle_in_transaction_session_timeout`, network partition), next `acquire()` hands
out a dead connection. `_run_once_with_reconnect_on_lost` only handles the main `self.conn` path —
pool connections bubble up as raw exceptions from `run_execute` / `run_execute_batch`.

→ `task-postgres_connection_pool.md`

### F-04 — `autocommit=False` on read-pool connections

All 5 pool connections have `autocommit=False`. Read-only SELECTs on the read pool open an implicit
transaction. The `acquire()` context manager only does `rollback()` on exception — on normal exit,
the implicit transaction stays open until next use, holding PG resources (MVCC snapshot, locks).

→ `task-postgres_connection_pool.md`

### F-05 — Observability breaks abstraction: command reaches into driver internals

`get_database_status_build._postgres_pool_observability_fields()` does:
```python
rpc = getattr(db, "rpc_client", None)
handlers = getattr(rpc, "handlers", None)
driver = getattr(handlers, "driver", None)
if isinstance(driver, PostgreSQLDriver): ...
```
This is a command reaching through 3 layers of abstraction into the specific driver.
Plan step 6 notes this as a known compromise but recommends "thin public method on DatabaseClient".
Not yet done — commands should not know about driver internals.

→ `task-get_database_status_build.md`

### F-06 — `rpc_server._priority_for_request` ignores `RPCRequest.priority` from wire

SQLite subprocess has its own priority classification (`_priority_for_request`) based on
`method == "select"` and `table_name == "projects"`. It does NOT read the `priority` field
that workers send. Workers tagging requests (steps 3-4) has zero effect in SQLite mode.

Plan says Phase 2 step S-1 should address this — not a Phase 1 bug, but confirms the field is dead in all paths.

→ `task-rpc_server.md`

### F-07 — File size violations

| File | Lines | Over 400 |
|------|-------|----------|
| `batch_processor.py` | 640 | 60% |
| `processing.py` (indexing) | 623 | 56% |
| `postgres.py` | 539 | 35% |
| `rpc_client.py` | 514 | 29% |
| `rpc_server.py` | 489 | 22% |
| `client_operations.py` | 480 | 20% |
| `get_database_status_build.py` | 434 | 9% |
| `processing_cycle_projects.py` | 429 | 7% |
| `processing_cycle.py` | 402 | <1% |

→ Not tasked individually; separate tech-debt initiative.

### F-08 — Missing integration test (step 7)

No test simulates concurrent MCP commands + worker DB traffic under PostgreSQL.
Unit tests cover pool mechanics but not the end-to-end scenario that was the original problem
(MCP commands timing out while workers hold DB connections).

→ `task-integration_test.md`

---

## Corrections to Audit #1

| Audit #1 finding | Actual status |
|------------------|---------------|
| "vectorization uses magic priority=1" | ❌ Wrong — all files import `BACKGROUND_WORKER_DB_RPC_PRIORITY` |
| "observability missing idle/waiters" | ❌ Wrong — `_postgres_pool_observability_fields` exports all 6 fields |
| "pool has no acquire timeout" | ❌ Wrong — `max_wait_seconds=30` with deadline in `acquire()` |

---

## Task files (this directory)

| Task file | Target code file | Finding |
|-----------|------------------|---------|
| `task-rpc_protocol.md` | `protocol/rpc_protocol.py` | F-01 |
| `task-rpc_dispatch.md` | `database_driver_pkg/rpc_dispatch.py` | F-01 |
| `task-postgres.md` | `drivers/postgres.py` | F-02 |
| `task-postgres_connection_pool.md` | `drivers/postgres_connection_pool.py` | F-03, F-04 |
| `task-get_database_status_build.md` | `worker_status_mcp_commands/get_database_status_build.py` | F-05 |
| `task-rpc_server.md` | `database_driver_pkg/rpc_server.py` | F-06 (Phase 2) |
| `task-postgres_execute_lane.md` | `drivers/postgres_execute_lane.py` | No issues |
| `task-in_process_rpc_client.md` | `database_client/in_process_rpc_client.py` | No issues |
| `task-integration_test.md` | `tests/` | F-08 |
