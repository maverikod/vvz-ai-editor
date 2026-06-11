# Task: `rpc_server.py` — `_priority_for_request` ignores `RPCRequest.priority`

**Finding:** F-06 from AUDIT_SUMMARY_2.md
**File:** `code_analysis/core/database_driver_pkg/rpc_server.py`
**Severity:** Low (Phase 2 scope — not a Phase 1 bug)
**Phase:** 2 (S-1)
**Lines:** ~198-209 (`_priority_for_request`)

---

## Context

`RPCServer` is the **SQLite subprocess** path. It runs in a separate process, receives
requests via Unix socket, enqueues them in `RequestQueue`, and processes them with a
single consumer thread (single SQL executor — SQLite limitation).

The queue has priority support (`RequestPriority.HIGH` / `NORMAL`).

Workers tag requests with `priority=1` via `BACKGROUND_WORKER_DB_RPC_PRIORITY`. This value
is serialized into wire JSON and deserialized by `RPCRequest.from_dict()` on the server side.

## Problem

`_priority_for_request()` (lines ~198-209) does its own classification:

```python
def _priority_for_request(self, rpc_request: RPCRequest) -> RequestPriority:
    if rpc_request.method != "select":
        return RequestPriority.NORMAL
    params = rpc_request.params or {}
    if params.get("table_name") != "projects":
        return RequestPriority.NORMAL
    where = params.get("where")
    if not isinstance(where, dict) or len(where) != 1 or "id" not in where:
        return RequestPriority.NORMAL
    return RequestPriority.HIGH
```

It checks `method` and `table_name` — never reads `rpc_request.priority`.
Workers setting `priority=1` has zero effect in SQLite mode.

## Task (Phase 2 — S-1)

When Phase 2 begins, update `_priority_for_request` to also consider `rpc_request.priority`:

**Option A (simple merge):**
```python
def _priority_for_request(self, rpc_request: RPCRequest) -> RequestPriority:
    # Worker-tagged background traffic → NORMAL (lower priority)
    if rpc_request.priority > 0:
        return RequestPriority.NORMAL
    # Fast MCP lookups → HIGH
    if rpc_request.method == "select":
        params = rpc_request.params or {}
        if params.get("table_name") == "projects":
            # ... existing logic ...
            return RequestPriority.HIGH
    return RequestPriority.NORMAL
```

**Option B (invert — worker traffic explicitly deprioritized):**
Use `rpc_request.priority` to lower background traffic while keeping existing heuristic
for HIGH priority lookups.

## What NOT to do (Phase 1)

- Do NOT change this file in Phase 1 — plan explicitly gates SQLite changes to Phase 2
- Do NOT modify `RequestQueue` priority levels in Phase 1
- Do NOT mix this with PostgreSQL pool changes

## Acceptance criteria (Phase 2)

- [ ] `_priority_for_request` reads `rpc_request.priority` from wire
- [ ] Worker-tagged requests get lower priority in the queue
- [ ] Existing HIGH priority for `select projects by id` preserved
- [ ] No regression in SQLite subprocess tests
