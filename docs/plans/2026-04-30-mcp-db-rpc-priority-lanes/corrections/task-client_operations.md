# Task: client_operations.py — audit and fix

**File:** `code_analysis/core/database_client/client_operations.py`
**Lines:** 480 (EXCEEDS 400 limit)
**Plan steps:** general (code quality)

---

## Issues found

### 1. File exceeds 400-line limit (VIOLATION)

At 480 lines, 20% over limit. The `_ClientOperationsMixin` class is 440 lines.

**Fix:** Extract chunk-related methods into a separate mixin:
- `add_code_chunk` (lines 340–420, 81 lines)
- `upsert_code_chunk` (lines 422–463, 42 lines)
- `upsert_code_chunks_batch` (lines 465–480, 16 lines)

Move to `client_chunks.py` → `_ClientChunksMixin`. This removes ~140 lines.

### 2. execute() and execute_batch() correctly accept priority ✅

Both methods have `*, priority: int = 0` parameter and pass it through to
`self.rpc_client.call(..., priority=priority)`. This is correct per plan step 1.

### 3. add_code_chunk does not pass priority

`add_code_chunk()` (line 340) calls `self.execute(...)` without `priority` kwarg.
When called from vectorization_worker's batch processing, the worker passes
`priority=1` to `execute_batch` but this method uses the default `priority=0`.

**Fix (low priority):** Add `*, priority: int = 0` parameter to `add_code_chunk()`
and forward to `self.execute()`. Or accept default=0 since `add_code_chunk` is
rarely called directly (batch path uses `upsert_code_chunks_batch`).

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. Verify file is ≤400 lines after extraction
3. `comprehensive_analysis` on file and new mixin file
