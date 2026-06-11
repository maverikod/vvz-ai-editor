# Task: processing_cycle.py (vectorization) — audit and fix

**File:** `code_analysis/core/vectorization_worker_pkg/processing_cycle.py`
**Lines:** 399 (within limit, borderline)
**Plan steps:** 4 (tag vectorization_worker)

---

## Issues found

### 1. Magic number `priority=1` instead of named constant (CODE QUALITY)

All `database.execute()` calls use literal `priority=1` (lines 179, 187, 197,
211, 233, 252, 284, 388). In contrast, `indexing_worker_pkg/processing.py`
defines `_INDEXING_WORKER_DB_RPC_PRIORITY = 1` and uses it consistently.

**Plan reference:** step 4: "priority=1 на соответствующие execute / execute_batch".
The plan says to tag vectorization worker with priority — this is done, but using
a magic number diverges from the indexing_worker pattern.

**Fix:** Add at module top:
```python
# Background vectorization DB traffic: non-zero RPC request priority for pool routing / metrics.
_VECTORIZATION_WORKER_DB_RPC_PRIORITY = 1
```
Replace all `priority=1` with `priority=_VECTORIZATION_WORKER_DB_RPC_PRIORITY`.

### 2. list_projects() call without priority (line 333)

`database.list_projects()` (line 333) does not pass `priority`. This is a
high-level API call that ultimately calls `execute()` without priority.
During FAISS rebuild, this SELECT competes with worker traffic at default priority=0.

**Fix:** This is a method on `DatabaseClient` mixin, not `execute()` directly.
Either add `priority` parameter to `list_projects()` method, or accept that
this single read-only call at priority=0 is correct (MCP-like behavior).
Document the decision.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. `comprehensive_analysis` on file
