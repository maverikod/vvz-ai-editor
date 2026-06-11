# G-000 Green Closure — Legacy Sidecar Layout Cutover (Final Integration Gate)

## Purpose

Close G-000 (SidecarLayoutMigration / C-023) to GREEN after G-001..G-006 are GREEN: complete any remaining code cutover gaps, purge all legacy on-disk tree artifacts (`.cst/*.tree`, `.trees/*.tree`, `*.tree_sidecar`), align scripts, and run the **full** project pytest suite as the overall plan integration gate.

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- HRS: `docs/plans/marked_tree_unification/source_spec.md` (Block 11 — `{k001}`–`{k004}`)
- MRS: `docs/plans/marked_tree_unification/spec.yaml` (C-023 SidecarLayoutMigration, C-003 TreeFile, C-006 ChecksumSyncPolicy)
- Global step: `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/README.yaml`
- Plan tactical steps: T-001, T-002, T-003 under same G-000 directory
- Parallel waves: `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/parallel-waves.yaml`

## Scope

**Included (hard cutover — no compatibility shim):**

1. **T-001 (path-resolution)** — `tree_sidecar.py` uses `sibling_tree_path` only; legacy `.cst/` resolver and entire pending mechanism deleted.
2. **T-002 (write-path)** — `core/tree_temp/sidecar_paths.py` deleted; `tree_temp_write_commit.py`, `tree_temp_open_support.py` use `sibling_tree_path`.
3. **T-003 (read-path-and-consumers)** — `tree_representation.py` dispatcher/readers sibling-only; all listed consumers on sibling path; tests/scripts aligned.
4. **Remaining code gap A-007** — Remove dead `write_sidecar_atomic` stub in `recreate_tree_from_content` python_cst branch (`code_analysis/core/tree_lifecycle/checksum.py` L154–155 per researcher audit 2026-05-31).
5. **Disk hygiene `{k003}`** — Delete all legacy artifact files under repo (`code_analysis/`, `tests/`, `scripts/`); **exclude** `test_data/` from automated bulk delete (server-guarded projects may retain artifacts until separately managed).
6. **Script alignment** — Fix or retire `scripts/_delete_models_sidecar.py` (hard-coded `.cst/models.tree` path).
7. **Optional docstring sweep (non-blocking for functional GREEN)** — Update stale `.cst/` / `.trees/` / `.tree_sidecar` mentions in: `tree_stable_data.py`, `sidecar_payload.py`, `file_tree_sync.py`, `persist_tree_sidecar_after_edit` docstring in `tree_sidecar.py`, `checksum.py` L207 comment.
8. **Full integration gate** — `pytest -q` per `pytest.ini` on entire `tests/` tree; triage every failure per rules below.

**Excluded:**

- Creating `sibling_tree_path` (G-002 owns it)
- Three-section TreeFile parse/write semantics (G-002 TreeBuilder / NodeIdMap)
- HRS/MRS/spec.yaml edits — escalate to global orchestrator
- `test_data/` code changes — `tester_ca` only via MCP; not in this closure batch unless server failure blocks tests
- Fixes inside G-001..G-006 feature internals unrelated to legacy path layout

## Boundaries

- Do NOT modify `source_spec.md` or `spec.yaml`
- Do NOT add backward-compatibility shims for `.cst/`, `.trees/`, or `.tree_sidecar`
- Do NOT mask unrelated test failures as GREEN
- Do NOT touch `test_data/` with direct file tools

## Dependencies

- G-001, G-002, G-003, G-004, G-005, G-006 — all GREEN (prerequisite)

## Parallelization note

**Wave 1 (parallel, max 3):**
- Track A: A-007 checksum fix (`coder_auto`)
- Track B: Legacy artifact purge + script fix (`coder_auto` — separate file set from A)
- Track C: Docstring sweep (`coder_auto` — lowest priority; may skip if time-constrained)

**Wave 2 (serial after Wave 1):**
- Full suite gate (`tester_auto`): `pytest -q` from repo root with `.venv` active

**Wave 3 (on cutover-related failures only):**
- Targeted fixes (`coder_auto`) → re-run full suite (`tester_auto`)

## Expected outcome

| Criterion | Verification |
|-----------|--------------|
| Legacy resolvers removed | Grep: no `sidecar_path_for_py`, `resolve_trees_sidecar_path`, `promote_pending_sidecar_to_final`, `_ADJACENT_SIDECAR_SUFFIX` in `code_analysis/` |
| Pending mechanism removed | Grep: no `pending_sidecar_path_for_py`, `resolve_sidecar_write_path`, `_cleanup_empty_pending_dir` |
| All formats sibling path | `sidecar_path_for` → `sibling_tree_path` only |
| A-007 closed | No `write_sidecar_atomic` in `checksum.py` python_cst recreate branch |
| Zero legacy artifacts | `find code_analysis tests scripts -path '*/test_data/*' -prune -o -path '*/.cst/*.tree' -print \| wc -l` → **0**; same for `.trees/*.tree` and `*.tree_sidecar` |
| Full test suite | `pytest -q` — **all tests pass** (report passed/failed/skipped/xfail counts) |

## Correction items (from researcher_code audit 2026-05-31)

### P0 — Code (blocking)

1. **`code_analysis/core/tree_lifecycle/checksum.py` — A-007**: In `recreate_tree_from_content`, python_cst branch: remove local import of `write_sidecar_atomic` and delete:
   ```python
   if not sidecar_path.is_file():
       write_sidecar_atomic(source_abs, {"source_sha256": content_checksum})
   ```
   Atomic step: `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-007-checksum-drop-dead-fallback.yaml`

### P0 — Disk (blocking for `{k003}`)

2. **Legacy artifact purge**: Delete **1,146** existing `**/.cst/*.tree` files under `code_analysis/` (mostly `database_driver_pkg/**/.cst/`). Count must be **0** after purge. Do not delete sibling `*.tree` files at source-adjacent paths.

### P1 — Scripts

3. **`scripts/_delete_models_sidecar.py`**: Update to use `sibling_tree_path` for models sidecar target, or retire script if obsolete.

### P2 — Docstrings (hygiene)

4. Stale layout references in comments/docstrings (listed in Scope §7).

### Already IMPLEMENTED (verify only, no re-edit unless regression)

- T-001 A-001: `tree_sidecar.py` sibling cutover
- T-002 A-001..A-004: `sidecar_paths.py` deleted, tree-temp callers redirected
- T-003 A-001..A-006, A-008..A-020 except A-007

## Test plan (tester_auto)

**Primary gate (mandatory):**
```bash
cd /home/vasilyvz/projects/tools/code_analysis
source .venv/bin/activate
pytest -q
```

**Legacy artifact scan (mandatory after purge):**
```bash
find code_analysis tests scripts -path '*/test_data/*' -prune -o -path '*/.cst/*.tree' -print | wc -l
find code_analysis tests scripts -path '*/test_data/*' -prune -o -path '*/.trees/*.tree' -print | wc -l
find code_analysis tests scripts -path '*/test_data/*' -prune -o -name '*.tree_sidecar' -print | wc -l
```
All three counts must be **0**.

**Triage rules:**
- Failure references `.cst/`, `.trees/`, `.tree_sidecar`, removed symbols, or legacy path assertions → **cutover-owned** → `coder_auto` fix → re-run full suite.
- Failure in tree/sidecar/preview/edit-session/grep/watcher/indexer/node-id-map area but not legacy paths → likely **G-001..G-006 regression** → report test id + branch owner; do not fix other branch internals here.
- Failure clearly unrelated (not touching listed domains) → **pre-existing** → report test id + error verbatim; do NOT claim GREEN.

## Questions/escalation rule

Escalate to global orchestrator if:
- Purging `.cst/*.tree` under `code_analysis/database_driver_pkg/` breaks runtime assumptions not covered by sibling cutover
- Full-suite failure requires HRS/MRS change
- `test_data/` server-guarded verification needed for layout change impact

## Subordinate verification checkpoint

After `coder_auto` completes P0/P1:
1. `researcher_code` — re-audit G-000 criteria 1–6 (quick confirm)
2. `tester_auto` — full `pytest -q` + artifact scan counts
3. Report pass/fail counts and list any pre-existing or cross-branch failures explicitly

## Residual failure triage (global orchestrator routing — 2026-05-31)

### FAILURE 1 — `test_removed_commands_absent_from_server`

**Classification:** **Pre-existing / out-of-plan** — command-surface cleanup gap (May 2026 client API sync), **not** marked_tree_unification G-000..G-006 deliverable.

**Root cause:** `client/code_analysis_client/server_api.py` `LEGACY_REMOVED_COMMANDS` includes `create_text_file` (added e4a77c7d 2026-05-23); server still registers via `code_analysis/hooks_register_part2.py` → `reg.register(CreateTextFileMCPCommand, "custom")`. Partial deregistration in `registration.py` (2e000154) removed other legacy commands but not this hooks_part2 registration.

**Plan linkage:** G-003 `{d002}` / C-012 functionally supersede create via `universal_file_open(create=True, initial_content=...)` — but **no plan artifact requires unregistering** `create_text_file`. HRS for marked_tree does not mention it; obsolete-command policy is in `docs/plans/2026-05-20-universal-to-ai-editor/HRS.md` and `docs/AI_TOOL_USAGE_RULES.md`.

**Owning area for routing:** Command-surface / client-API sync (not G-003 green-closure, not G-000). Conflicting test: `tests/test_create_text_file_command.py` still asserts command registered.

**G-000 action taken:** None (not cutover-owned).

### FAILURE 2 — `test_performance_project_id_validation_1000_files`

**Classification:** **Pre-existing / out-of-plan — environment/load-sensitive flake** (not reproducible in isolation; not marked_tree regression).

**Full-suite failure:** `assert 7.554693698883057 < 5.0` (during concurrent full `pytest -q`).

**Isolated re-runs (3/3 PASS, idle machine):**
```bash
pytest tests/test_performance.py::TestPerformanceProjectIdValidation::test_performance_project_id_validation_1000_files -v --tb=short
```
| Run | Result | DB insert elapsed |
|-----|--------|-------------------|
| 1 | PASS | ~3.12s session (elapsed not printed) |
| 2 | PASS | **2.79s** |
| 3 | PASS | **2.87s** |

Threshold: `tests/test_performance.py:240` — `assert elapsed < 5.0`. Uses isolated SQLite via `tmp_path` fixture, not production DB.

**Plan-impact check:** Skipped — flake classification; no researcher_code regression trace requested.

**G-000 action taken:** None.
