# Task: processing_cycle_projects.py (vectorization) — audit and fix

**File:** `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`
**Lines:** 428 (EXCEEDS 400 limit)
**Plan steps:** 4 (tag vectorization_worker)

---

## Issues found

### 1. File exceeds 400-line limit (VIOLATION)

At 428 lines the file violates the 400-line rule.

**Fix:** Extract per-project step processing into separate functions or a submodule.
Candidates for extraction:
- Step 0 (re-embed, lines ~96–162) → `_run_project_step0_reembed()`
- Step 1 (chunking query, lines ~163–310) → `_run_project_step1_chunking()`
- Step 2 (embedding/vectorization, lines ~311–415) → `_run_project_step2_vectorize()`

Each step is self-contained with its own try/finally for faiss_manager restore.

### 2. Magic number `priority=1` (same as processing_cycle.py)

Lines 247, 407 use literal `priority=1`.

**Fix:** Import `_VECTORIZATION_WORKER_DB_RPC_PRIORITY` from `processing_cycle.py`
(or define in a shared constants module for the package, e.g.
`vectorization_worker_pkg/constants.py`).

### 3. No priority on process_embedding_ready_chunks / process_chunks_missing_embedding_params

These functions in `batch_processor.py` receive `database` but do not receive
a `priority` parameter — they use hardcoded `priority=1` internally.
If the constant value ever changes, these would be out of sync.

**Fix:** Either centralize the constant (see #2) or pass `rpc_priority` through.

---

## Validation after fix

1. `format_code` → `lint_code` → `type_check_code`
2. Verify file is ≤400 lines after extraction
3. `comprehensive_analysis` on file and any new extracted module
