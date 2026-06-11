# Task: batch_processor.py (vectorization) — audit and fix

**File:** `code_analysis/core/vectorization_worker_pkg/batch_processor.py`
**Lines:** 635 (EXCEEDS 400 limit — SEVERELY)
**Plan steps:** 4 (tag vectorization_worker)

---

## Issues found

### 1. File severely exceeds 400-line limit (CRITICAL VIOLATION)

At 635 lines this is 59% over the 400-line limit. Two large functions:
- `process_chunks_missing_embedding_params`: 211 lines (173–383)
- `process_embedding_ready_chunks`: 250 lines (386–635)

**Fix:** Split file using `split_file_to_package` MCP command or manual extraction:
- `batch_processor_reembed.py` — `process_chunks_missing_embedding_params` + helpers
  (`_apply_chunker_results_to_db`, `_get_chunking_blocks_logger`, `_log_blocks_sent_to_chunker`,
  `_token_count_heuristic`)
- `batch_processor_vectorize.py` — `process_embedding_ready_chunks`
- `batch_processor.py` — re-export from submodules for backward compatibility

### 2. Magic number `priority=1` — scattered across file

Lines 229, 302, 309, 350, 367, 370, 432, 585 — all use literal `priority=1`.

**Fix:** Import or define `_VECTORIZATION_WORKER_DB_RPC_PRIORITY` constant.
Replace all occurrences.

### 3. f-string logging (PERFORMANCE)

Multiple logger calls use f-strings instead of %-formatting:
- Line 416: `f"[TIMING] Getting non-vectorized chunks..."`
- Line 435: `f"[TIMING] Retrieved {len(chunks)} chunks..."`
- Line 487+: Many more in `process_embedding_ready_chunks`

f-string logging eagerly evaluates the format string even when the log level
is disabled. With `logger.debug()` this wastes CPU.

**Fix:** Replace f-string logger calls with %-formatting:
```python
# Before
logger.info(f"[TIMING] Retrieved {len(chunks)} chunks in {step_duration:.3f}s")
# After
logger.info("[TIMING] Retrieved %d chunks in %.3fs", len(chunks), step_duration)
```

### 4. No error handling for FAISS save failure (line 608)

```python
except Exception as e:
    logger.error(f"Error saving FAISS index: {e}")
```
After this error, the function returns `batch_processed` as if writes succeeded,
but vector_id UPDATEs in the DB are already committed (line 585).
This creates inconsistency: DB has vector_ids pointing to a FAISS index that
was not saved.

**Fix:** Either:
1. Document this as known behavior (FAISS rebuild will fix on next cycle), or
2. Roll back DB updates on FAISS save failure (complex, requires keeping track of
   which vector_ids were assigned).

Option 1 is acceptable given that `rebuild_from_database` runs every cycle.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. Verify each resulting file is ≤400 lines
3. `comprehensive_analysis` on all resulting files
