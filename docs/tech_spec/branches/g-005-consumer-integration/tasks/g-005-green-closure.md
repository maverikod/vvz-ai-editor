# G-005 Green Closure — Corrective Tactical Task

## Purpose

Close G-005 (Consumer Integration) to GREEN: fix T-001 and T-002 deviations found in verification (2026-05-31), confirm T-003 remains GREEN, and re-run G-005 pytest scope until all tests pass. Tests currently pass but code audit found plan incoherence on live production paths.

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- HRS: `docs/plans/marked_tree_unification/source_spec.md` (Block 7 — labels `{g001}` grep, `{g002}` watcher + tree_checksum, `{g003}` indexer skip guard, `{g004}` Finding without mtime)
- MRS: `docs/plans/marked_tree_unification/spec.yaml` (C-020 GrepConsumer, C-021 Watcher, C-022 Indexer, C-026 SearchSessionFinding; grep/watcher route through C-010 TreeLifecycle; indexer uses C-006 ChecksumSyncPolicy)
- Global step: `docs/plans/marked_tree_unification/G-005-consumer-integration/README.yaml`
- Tactical steps: T-001, T-002, T-003 under `docs/plans/marked_tree_unification/G-005-consumer-integration/`

## Scope

**Included:**
- T-001 P0: Route live grep enrichment path through TreeLifecycle (replace mtime gate in `stable_tree.py`)
- T-002 P0: Batch watcher INSERT/UPDATE path must call TreeLifecycle and persist `tree_checksum`
- Re-run G-005 pytest scope (64 tests, 13 files per tester_auto report)
- Confirm T-003 indexer guard unchanged and still GREEN

**Excluded:**
- HRS/MRS/spec.yaml edits — escalate to global orchestrator
- `test_data/` — server-guarded; not touched
- G-002 TreeLifecycle contract changes — escalate if wrapper incoherent (audit: wrapper OK)
- Full-suite 21 failures outside G-005 scope (edit session / universal preview)
- Optional legacy cleanup of unused `grep_block_resolver._build_index` — P2, not blocking

## Boundaries

- Do NOT modify `source_spec.md` or `spec.yaml`
- Do NOT touch `test_data/`
- Do NOT redefine `validate_or_recreate_tree_file` (G-002 owns TreeLifecycle)
- Minimal diffs only — no queue refactor beyond TreeLifecycle + checksum seam

## Dependencies

- G-002 TreeLifecycle path wrapper must exist (verified IMPLEMENTED in `code_analysis/core/tree_lifecycle/checksum.py`)
- T-002 schema column + version bump already IMPLEMENTED (do not revert)

## Parallelization note

Two independent coder tracks may run in parallel:
1. T-001 fix: `stable_tree.py` TreeLifecycle routing
2. T-002 fix: `processor_queue.py` batch path TreeLifecycle + tree_checksum

T-003 requires no code change; re-verify after T-002 fix populates checksums on batch path.

## Expected outcome

- T-001 GREEN: all grep tree-validity checks route through `validate_or_recreate_tree_file`; no ad-hoc py/sidecar mtime gate on live enrichment path
- T-002 GREEN: every file-row insert/update (batch and fallback) calls TreeLifecycle before DB write; `tree_checksum` persisted
- T-003 GREEN: checksum skip guard unchanged; becomes effective in production once watcher populates checksum
- G-005 pytest scope: 64 passed, 0 failed (same command set as verification)
- Finding contract (no mtime, result_id tie-break) remains GREEN — no regression

## Correction items (from researcher_code audit 2026-05-31)

### P0 — T-001 GrepConsumer live path

**File:** `code_analysis/core/structure_extraction/stable_tree.py`

**Problem:** `_load_current_sidecar_metadata` uses py_mtime vs sidecar_mtime gate (L50–63 area). `resolve_python_metadata_stable` rebuilds via `load_file_to_tree`, not `validate_or_recreate_tree_file`. This is the path used by `extract_structure` → `enrich_matches_for_file` → `fs_grep_command._phase2_enrich_blocks` and `GrepBlockResolver.resolve`. Violates HRS `{g001}` / C-020 Action 1.

**Required fix:**
1. Replace mtime sidecar validity gate with TreeLifecycle path wrapper `validate_or_recreate_tree_file` from `code_analysis.core.tree_lifecycle.checksum`.
2. On checksum mismatch: wrapper rebuilds tree before metadata bind (Action 2).
3. On wrapper failure (FileNotFoundError, ValueError, OSError, NotImplementedError): degrade — return None / empty metadata so match becomes ineligible lower-relevance result, not structural error (Action 3).
4. Remove py_mtime/sidecar_mtime comparison from sidecar load path.
5. Derive `project_root` and project-relative `file_path` from `abs_path` consistently with `grep_block_resolver._load_python_sidecar_index` pattern.

**Forbidden:** Do not add Finding mtime fields. Do not modify block_assembler ranking.

### P0 — T-002 Watcher batch path

**File:** `code_analysis/core/file_watcher_pkg/processor_queue.py`

**Problem:** `_queue_file_for_processing` fallback path correctly calls TreeLifecycle and passes `tree_checksum` (L708–729 area). Primary batch path `_queue_project_delta` writes via direct SQL (`insert_new_sql`, `update_changed_sql`) without TreeLifecycle and without `tree_checksum` column. Violates HRS `{g002}`.

**Required fix:**
1. Before batch INSERT for `new_rows` and batch UPDATE for `changed_rows`, call `validate_or_recreate_tree_file(project_root=..., file_path=rel_path)` per file.
2. Persist `tree_ref.content_checksum` as `tree_checksum` on each file row — either extend batch SQL to include `tree_checksum` column or route through `ensure_file_row_for_disk_path(..., tree_checksum=...)` if batch refactor is too large.
3. On TreeLifecycle failure for a file: log error and skip that file (do not write row without valid tree), consistent with fallback path returning False.
4. Do NOT recompute checksum — reuse `tree_ref.content_checksum`.
5. Keep queue/normalization/scheduling unchanged outside this seam.

**Already IMPLEMENTED (do not break):**
- Schema: `tree_checksum` column in `schema_definition_tables_core.py`, version `1.9.0`
- `ensure_file_row_for_disk_path` accepts and persists `tree_checksum` via `_persist_tree_checksum`

### P1 — Test gaps (non-blocking for code GREEN if audit passes post-fix)

- Dedicated unit tests for `update_checksum_guard.py` (T-003)
- Integration test: batch watcher persists `tree_checksum`
- Integration test: stable_tree routes through TreeLifecycle on mismatch

Route to planner_auto → coder_auto if global orchestrator requests test hardening before freeze.

## Questions/escalation rule

Escalate to global orchestrator if:
- `validate_or_recreate_tree_file` cannot serve stable_tree or batch watcher without G-002 contract change
- Batch path fix requires architectural queue rewrite beyond minimal seam
- HRS `{g002}` intended to exclude batch path (would require global step cascade, not local fix)

## Verification commands

```bash
source .venv/bin/activate
# G-005 scope (13 files, 64 tests)
pytest tests/unit/test_search_paginated_ggrep.py tests/unit/test_search_paginated_tree_query.py \
  tests/unit/test_search_paginated_cross.py tests/unit/test_existing_behavior_inventory.py \
  tests/test_update_file_data_atomic.py tests/test_search_inline_timeout.py \
  tests/commands/test_grep_block_resolver.py tests/unit/test_search_paginated_semantic.py \
  tests/test_processor_queue_logical_write.py tests/test_sqlite_files_unique_project_path_index.py \
  tests/unit/test_block_assembler.py tests/test_watcher_indexer_project_coordination.py \
  tests/unit/test_search_paginated_fulltext.py -q
```

Post-fix: researcher_code re-audit T-001 criteria 4 and T-002 criteria 1 & 4.

## Closure status (2026-05-31)

| Task | Pre-fix | Post-fix | Evidence |
|------|---------|----------|----------|
| T-001 GrepConsumer + Finding | RED | **GREEN** | researcher_code re-audit: stable_tree routes live fs_grep path through TreeLifecycle; no mtime gate |
| T-002 Watcher + checksum persist | RED | **GREEN** | researcher_code re-audit: batch INSERT/UPDATE includes TreeLifecycle + tree_checksum |
| T-003 Indexer checksum guard | GREEN | **GREEN** | unchanged; update_checksum_guard + update.py delegation |
| G-005 pytest scope | GREEN | **GREEN** | tester_auto: 64 passed, 0 failed, 1 skipped (official 13-file command) |

**Fixes applied (coder_auto):**
- `code_analysis/core/structure_extraction/stable_tree.py` — TreeLifecycle routing for live grep enrichment
- `code_analysis/core/file_watcher_pkg/processor_queue.py` — batch path TreeLifecycle + tree_checksum on INSERT/UPDATE
- `tests/test_watcher_indexer_project_coordination.py` — fixture `# a`/`# b` → `a = 1`/`b = 1` for tree buildability

**P2 follow-ons (non-blocking):** GrepBlockResolver.resolve uses `ensure_persisted_tree=False`; dedicated unit tests for update_checksum_guard.py.
