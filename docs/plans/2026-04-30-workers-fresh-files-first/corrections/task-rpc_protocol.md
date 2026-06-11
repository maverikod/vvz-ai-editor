# Task: `rpc_protocol.py` — `RPCRequest.priority` dead code

**Finding:** F-01 from AUDIT_SUMMARY_2.md
**File:** `code_analysis/core/database_client/protocol/rpc_protocol.py`
**Severity:** Low (cosmetic, misleading)
**Phase:** 1

---

## Context

`RPCRequest` dataclass has field `priority: int = 0` (line ~66). Workers set it to
`BACKGROUND_WORKER_DB_RPC_PRIORITY = 1`. The field is serialized via `to_dict()` (only
when non-zero) and deserialized via `from_dict()`.

**Problem:** No consumer reads this field in either runtime path:
- PostgreSQL in-process: `rpc_dispatch.process_rpc_request()` receives `RPCRequest` but
  never accesses `request.priority`. The connection pool does not use it for scheduling.
- SQLite subprocess: `rpc_server._priority_for_request()` classifies priority by
  `method`/`table_name` — it ignores `request.priority` entirely.

The field exists, is set, is serialized, but has zero effect.

## Current code (lines ~60-94)

```python
@dataclass
class RPCRequest:
    method: str
    params: Dict[str, Any]
    priority: int = 0          # ← set by workers, never consumed
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self.method,
            "params": self.params,
        }
        if self.priority != 0:
            result["priority"] = self.priority   # ← serialized but never read
        if self.request_id is not None:
            result["id"] = self.request_id
        return result
```

## Task

**Option A (recommended):** Keep the field. Add a docstring line to `priority` explaining
it is reserved for future use (Phase 2 / observability metrics) and currently not consumed
by any dispatcher or pool. This prevents future developers from assuming it works.

**Option B:** If the project owner decides priority should influence behavior in PostgreSQL
path, the consumer must be added in `rpc_dispatch.py` or in the pool acquire logic. But
this is a design decision, not a code fix.

## What NOT to do

- Do NOT remove the field — it was added deliberately (plan step 1) and may be needed for Phase 2.
- Do NOT add priority-based scheduling to `rpc_dispatch.py` — that violates the paradigm
  (specific logic belongs in specific drivers, not universal layer).

## Acceptance criteria

- [ ] `RPCRequest.priority` docstring clearly states the field is not yet consumed
- [ ] No functional code changes needed
