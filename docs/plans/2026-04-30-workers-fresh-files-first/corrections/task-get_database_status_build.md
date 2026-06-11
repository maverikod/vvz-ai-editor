# Task: `get_database_status_build.py` — observability breaks abstraction

**Finding:** F-05 from AUDIT_SUMMARY_2.md
**File:** `code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py`
**Severity:** Medium (architectural violation)
**Phase:** 1
**Lines:** ~191-219 (`_postgres_pool_observability_fields`)

---

## Context

`get_database_status` is an MCP command. It builds its response via
`build_database_status_result(db, db_path, driver_type=...)`. The `db` argument is a
`DatabaseClient` — the universal facade.

Commands should not know about specific driver internals. `DatabaseClient` is the abstraction
boundary — commands work with it and nothing below.

## Problem

`_postgres_pool_observability_fields()` reaches through 3 layers to get pool metrics:

```python
def _postgres_pool_observability_fields(db: Any, driver_type: str) -> Dict[str, Any]:
    if driver_type != "postgres":
        return {}
    rpc = getattr(db, "rpc_client", None)           # layer 1: DatabaseClient → rpc_client
    handlers = getattr(rpc, "handlers", None)        # layer 2: InProcessRpcClient → handlers
    driver = getattr(handlers, "driver", None)       # layer 3: RPCHandlers → driver
    if not isinstance(driver, PostgreSQLDriver):     # imports specific driver class!
        return {}
    pool_st = driver.pool_status()
    ...
```

This violates the paradigm: a command knows about `PostgreSQLDriver`, `RPCHandlers`,
`InProcessRpcClient` internals. If any internal structure changes, this command breaks.

Plan step 6 acknowledges this: "Альтернатива: тонкий публичный метод на `DatabaseClient`
/ отдельный RPC — выбрать по минимальности диффа".

## Task

Add a thin public method to `DatabaseClient` that returns pool status without exposing internals:

**Step 1:** Add method to `DatabaseClient` (in `client.py` or a mixin):
```python
def get_pool_status(self) -> Dict[str, Any]:
    """Pool metrics for observability; empty dict if driver has no pool."""
    rpc = self.rpc_client
    handlers = getattr(rpc, "handlers", None)
    driver = getattr(handlers, "driver", None)
    pool_status_fn = getattr(driver, "pool_status", None)
    if callable(pool_status_fn):
        return pool_status_fn()
    return {}
```

**Step 2:** Simplify `_postgres_pool_observability_fields` to use it:
```python
def _postgres_pool_observability_fields(db: Any, driver_type: str) -> Dict[str, Any]:
    if driver_type != "postgres":
        return {}
    pool_st = db.get_pool_status()
    if not pool_st.get("enabled"):
        return {}
    # ... same field extraction as now ...
```

**Step 3:** Remove `from ... import PostgreSQLDriver` from this file.

## What NOT to do

- Do NOT expose `db._driver` as a public attribute
- Do NOT add driver-specific logic to `DatabaseClient` beyond the thin `get_pool_status`
- Do NOT change the output field names (`pg_write_pool_in_use`, etc.) — they are API

## Acceptance criteria

- [ ] `get_database_status_build.py` does NOT import `PostgreSQLDriver`
- [ ] Pool status obtained via `DatabaseClient.get_pool_status()` or similar thin method
- [ ] Output fields unchanged (backward compatible)
- [ ] Works correctly for both PostgreSQL (returns metrics) and SQLite (returns empty dict)
- [ ] File size ideally reduced (currently 434 lines — over 400 limit)
