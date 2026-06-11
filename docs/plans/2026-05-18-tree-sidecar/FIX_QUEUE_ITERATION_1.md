# SUPERSEDED — Fix queue — iteration 1 (post gate)

This iteration assumed `PLAN_LAYER_STATUS.yaml` was absent and predates tactical remediation + `PLAN_FULL_GREEN.md`. Do not execute as current work; see `PLAN_FULL_GREEN.md`.

**Gate date:** 2026-05-18  
**Sources:** `TACTICAL_VERIFICATION_REPORT.md`, `AS_VERIFICATION_REPORT.md`; **`PLAN_LAYER_STATUS.yaml` absent on disk** (add under §0).

**Gate result:** Not full green — **`PLAN_FULL_GREEN.md` not produced.**

---

## 0. Missing status artifact (blocking for YAML gate)

| Path | Action | Owner |
|------|--------|--------|
| `docs/plans/2026-05-18-tree-sidecar/PLAN_LAYER_STATUS.yaml` | Create with explicit `tactical_overall_green`, atomic / GS rollup fields aligned to standards | **planner_auto** (schema + values); **doc_writer** may populate descriptions if split |

---

## 1. Tactical layer (`tactical_step_creation_standard` / t11)

Per `TACTICAL_VERIFICATION_REPORT.md` — normalize **`atomic_steps`** to **`A-001`** … only; fix **`concepts`** on G-004 T-004.

| Path | Issue | Owner |
|------|-------|--------|
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-001-sha-sync-policy-resolver/README.yaml` | Path-valued `atomic_steps` → **`A-NNN`** only | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-002-edit-session-open/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-003-edit-session-edit/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-004-edit-session-write/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-005-edit-session-close/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/README.yaml` | Slug-augmented `atomic_steps` (**t11**) | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-001-tree-node-model-unit-tests/README.yaml` | `A-NNN-slug` composites → **`A-NNN`** only | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-002-source-parser-json/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-003-source-parser-yaml/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-004-source-serializer-round-trip/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-005-sha-sync-policy/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-006-edit-session-lifecycle/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-007-universal-file-integration-json/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-005-tests/T-008-universal-file-integration-yaml/README.yaml` | Same | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-004-universal-file-close/README.yaml` | Add **`C-001`**, **`C-002`** to **`concepts`** (**t5**) | **doc_writer** |

(Optional polish per tactical report:) `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-005-universal-file-preview-drill-down-stable-id/README.yaml` — **doc_writer**.

---

## 2. Atomic layer — contract / structure (**planner_auto**)

Per `AS_VERIFICATION_REPORT.md` §§2–4, 8–9, 11–13 — session API single shape; merge edit pipelines; TS/file ownership or sequencing so **`a8`** holds.

| Path / scope | Issue | Owner |
|--------------|-------|--------|
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/parallel_waves.yaml` | Escalations (G-003 vs G-004 edit) — reconcile before AS green | **planner_auto** |
| `docs/plans/2026-05-18-tree-sidecar/spec.yaml` (if MRS/session fields change) | Single **`EditSession`** field set vs fork | **planner_auto** (only if tactical/MRS amendment required) |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-002-edit-session-open/A-001-edit-session-fields/README.yaml` | **`session.py`** — align with single contract vs G-004 | **planner_auto** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-001-universal-file-open-tree-temp-sidecar/A-001-editsession-tree-temp-sidecar-fields/README.yaml` | **`session.py`** — merge with G-003; **`tree_temp_roots` vs `tree_roots`**, SHA/dirty | **planner_auto** |
| G-003 **`tree_temp_node_editing`** vs G-004 **`tree_temp_edit_batch`** AS targets | One module + entrypoint + session field naming | **planner_auto** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/` | **`edit_command.py`** chain — **a3** ≤400 LOC or TS split | **planner_auto** |

---

## 3. Atomic layer — prompts / embedding (**doc_writer**, after §2 frozen)

| Path | Issue | Owner |
|------|-------|--------|
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-002-edit-session-open/A-003-wire-open-command/README.yaml` | **`a8`**: later cross-G steps need true post-state | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-001-universal-file-open-tree-temp-sidecar/A-003-open-command-tree-temp-wire/README.yaml` | **`a8`** embed full cumulative **`open_command.py`** | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-004-edit-session-write/A-001-write-source-and-sidecar/README.yaml` | Baseline for **`write_command.py`** chain | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-003-universal-file-write/A-002-write-command-preview-commit-mode/README.yaml` | **`a8`** literal full file after G-003 | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-005-edit-session-close/A-001-close-discard-without-disk-sidecar/README.yaml` | Baseline for **`close_command.py`** | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-004-universal-file-close/A-001-close-tree-temp-session/README.yaml` | **`a8`** full **`close_command.py`** body | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/T-003-edit-session-edit/A-002-tree-node-edit-engine/README.yaml` | **`edit_command.py`** ordering vs G-004 | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/A-000-slim-edit-command/README.yaml` | **`a5`**, canonical **`step_id`** | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/A-002-edit-command-delegate-tree-temp/README.yaml` | **`a5`** strip sibling step refs from **`prompt`** | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/A-000-tree-temp-legacy-apply/README.yaml` | **`a5`** | **doc_writer** |
| `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/T-002-universal-file-edit/A-000-sidecar-cst-apply/README.yaml` | **`a5`** | **doc_writer** |
| Remaining **`G-004-universal-file-integration/T-002-universal-file-edit/A-*.*/README.yaml`** | **`a5`**, **`A-NNN`** **`step_id`** normalization | **doc_writer** |

---

## 4. Re-run order for orchestrator

1. **planner_auto:** §0 + §2 (contracts / waves / optional **`spec.yaml`**).  
2. **doc_writer:** §1 + §3 (and §0 prose if applicable).  
3. Regenerate or update **`PLAN_LAYER_STATUS.yaml`** when tactical atomic_steps fixes land.  
4. **`researcher_doc`**: rerun tactical outer loop + AS verification → gate again.

---

## Report consistency (no contradiction)

- **Tactical:** `overall_green` **no** (G-003–G-005 failures).  
- **Atomic:** formal precondition **FAIL**, GS **FAIL** for G-003–G-005, no evidenced tactical **`overall_green`**.  
Both reports agree the plan is **not** green at tactical + atomic gates.
