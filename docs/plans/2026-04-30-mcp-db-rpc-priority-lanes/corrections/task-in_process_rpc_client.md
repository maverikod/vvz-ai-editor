# Task: in_process_rpc_client.py — audit and fix

**File:** `code_analysis/core/database_client/in_process_rpc_client.py`
**Lines:** 128 (within limit)
**Plan steps:** 2a (remove global serialization)

---

## Issues found

### 1. Step 2a is DONE — lock correctly narrowed ✅

The lock now only covers `self._closed` check (lines 95–97):
```python
with self._call_lock:
    if self._closed:
        raise ConnectionError(...)
```
`process_rpc_request` runs **outside** the lock (line 99). This matches the plan:
"lock не должен оборачивать весь process_rpc_request; минимальный вариант:
под lock только проверка _closed".

Comment at lines 92–95 documents the design choice clearly.

**No code change needed.** Mark step 2a as DONE in plan status.

### 2. Minor: disconnect() has no lock — race window

`disconnect()` (lines 52–59) sets `self._closed = True` and `self._connected = False`
without holding `self._call_lock`. A concurrent `call()` could read `self._closed`
as False inside the lock, then `disconnect()` closes the driver before
`process_rpc_request` starts.

**Risk:** Low — the driver's own pool handles concurrent close gracefully.
**Fix (optional):** Wrap `self._closed = True` in `with self._call_lock:` for correctness.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. `comprehensive_analysis` on file
