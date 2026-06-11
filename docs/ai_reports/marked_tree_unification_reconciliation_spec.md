<!-- Author: Vasiliy Zdanovskiy, email: vasilyvz@gmail.com -->

# Marked Tree Unification — Plan Reconciliation Spec

**Date:** 2026-05-30  
**Scope:** Mechanical edits to close list-vs-files and naming anomalies surfaced by `marked_tree_unification_parallelization_wave_map.md`.  
**Source of truth rule:** Per Development Plan Standard, the `atomic_steps` field in each tactical README must enumerate exactly the A-NNN steps that belong to that tactical step. When on-disk atomic step YAML files are well-formed and coherent, the README is stale → **ADD** ids. When files are orphans/duplicates/malformed, **REMOVE** files.

**Investigation snapshot:** Plan tree read in full under `docs/plans/marked_tree_unification/`. Global steps on disk: G-000, G-001, G-002, G-003, G-004, G-005, G-006-node-id-map. **G-007 absent.** **G-006-universal-node-id absent.**

---

## Summary verdicts

| # | Anomaly | Verdict |
|---|---------|---------|
| 1 | G-000/T-003 README vs A-011–A-020 files | **ADD** A-011, A-012, A-013, A-014, A-015, A-016, A-017, A-018, A-019, A-020 to README; **UPDATE** `parallel-waves.yaml` (discovered stale) |
| 2 | G-005/T-001 README vs A-008 file | **ADD** A-008 to README |
| 3 | G-007 absent / dangling refs | **NO EDIT NEEDED** |
| 4 | G-006 folder naming | **NO EDIT NEEDED** |

**Files to edit:** 3  
**Files to delete:** 0

---

## Anomaly 1 — G-000/T-003 README vs atomic files (A-011–A-020)

### Evidence

**Tactical README path:**  
`docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/README.yaml`

**Listed in README (`atomic_steps`):** A-001, A-002, A-003, A-004, A-005, A-006, A-007, A-008, A-009, A-010 (10 ids)

**On disk but not listed:** A-011 through A-020 (10 files)

### Per-file legitimacy assessment

| step_id | file | parent | target_file | priority | depends_on | verdict |
|---------|------|--------|-------------|----------|------------|---------|
| A-011 | `A-011-tree-builder-index-module.yaml` | T-003 ✓ | `code_analysis/core/cst_tree/tree_builder_index.py` | 10 | A-009 | **LEGITIMATE — ADD** |
| A-012 | `A-012-tree-builder-slim-after-index-extract.yaml` | T-003 ✓ | `code_analysis/core/cst_tree/tree_builder.py` | 11 | A-011 | **LEGITIMATE — ADD** |
| A-013 | `A-013-test-cst-stable-ids-sibling.yaml` | T-003 ✓ | `tests/test_cst_stable_ids.py` | 12 | [] | **LEGITIMATE — ADD** |
| A-014 | `A-014-test-tree-temp-lifecycle-sibling.yaml` | T-003 ✓ | `tests/test_tree_temp_edit_session_lifecycle.py` | 13 | [] | **LEGITIMATE — ADD** |
| A-015 | `A-015-open-command-transitive-sibling-sidecar.yaml` | T-003 ✓ | `code_analysis/commands/universal_file_edit/open_command.py` | 14 | [] | **LEGITIMATE — ADD** |
| A-016 | `A-016-invalid-write-support-transitive-sibling-sidecar.yaml` | T-003 ✓ | `code_analysis/commands/universal_file_edit/invalid_write_support.py` | 15 | [] | **LEGITIMATE — ADD** |
| A-017 | `A-017-sidecar-cst-apply-transitive-sibling-sidecar.yaml` | T-003 ✓ | `code_analysis/commands/universal_file_edit/sidecar_cst_apply.py` | 16 | [] | **LEGITIMATE — ADD** |
| A-018 | `A-018-test-cst-tree-saver-sibling.yaml` | T-003 ✓ | `tests/test_cst_tree_saver.py` | 17 | [] | **LEGITIMATE — ADD** |
| A-019 | `A-019-test-tree-modifier-sidecar-sibling.yaml` | T-003 ✓ | `tests/test_tree_modifier.py` | 18 | [] | **LEGITIMATE — ADD** |
| A-020 | `A-020-check-restore-script-sibling.yaml` | T-003 ✓ | `scripts/check_restore.py` | 19 | [] | **LEGITIMATE — ADD** |

**Justification:** All ten files have `parent_tactical_step: T-003`, `status: ready_for_review`, complete `prompt` and `verification` blocks, concepts C-023/C-003 aligned with parent TS, and scope matching T-003 description (remaining consumer cutover, test/script alignment, tree_builder module split per file-size constraint). Created during `tree_builder_split` convergence pass (see `marked_tree_unification_dovodka_audit.yaml` → `convergence_pass.tree_builder_split`). None are duplicate step_ids, parent mismatches, or empty stubs.

**Direction:** README is stale → ADD all ten ids. No file deletions.

### Priority uniqueness check (post-reconciliation)

Within T-003, grouped by `target_file`:

| target_file | step_ids | priorities | collision? |
|-------------|----------|------------|------------|
| `tree_builder.py` | A-010, A-012 | 10, 11 | **No** |
| `tree_builder_index.py` | A-011 | 10 | **No** |
| All other files | one AS each | unique per file | **No** |

Note: A-010 and A-011 both use priority 10 but on **different** files — allowed per plan standard (priority namespace is per target_file within a TS).

### Mechanical edit instruction — README

**File:** `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/README.yaml`

**Field:** `atomic_steps:` (lines 65–75)

**BEFORE:**
```yaml
atomic_steps:
- A-001
- A-002
- A-003
- A-004
- A-005
- A-006
- A-007
- A-008
- A-009
- A-010
```

**AFTER:**
```yaml
atomic_steps:
- A-001
- A-002
- A-003
- A-004
- A-005
- A-006
- A-007
- A-008
- A-009
- A-010
- A-011
- A-012
- A-013
- A-014
- A-015
- A-016
- A-017
- A-018
- A-019
- A-020
```

**Deletions:** none

---

### Discovered sub-anomaly — stale `parallel-waves.yaml`

**File:** `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/parallel-waves.yaml`

Currently lists waves 1–4 covering A-001 through A-009 only. A-011–A-020 are absent despite being canonical on disk and referenced in the macro-wave map critical path (A-009 → A-011 → A-012).

### Mechanical edit instruction — parallel-waves

**File:** `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/parallel-waves.yaml`

**Field:** append after existing `wave: 4` block (after line 46 `      - A-009`)

**BEFORE (tail of file):**
```yaml
  - wave: 4
    after:
      - A-001
      - A-002
      - A-003
      - A-004
      - A-005
      - A-006
      - A-007
      - A-008
    steps:
      - A-009
```

**AFTER (replace tail from `wave: 4` through EOF):**
```yaml
  - wave: 4
    after:
      - A-001
      - A-002
      - A-003
      - A-004
      - A-005
      - A-006
      - A-007
      - A-008
    steps:
      - A-009
  - wave: 5
    after:
      - A-009
    steps:
      - A-011
  - wave: 6
    after:
      - A-011
    steps:
      - A-012
  - wave: 7
    parallel:
      - A-013
      - A-014
      - A-015
      - A-016
  - wave: 8
    parallel:
      - A-017
      - A-018
  - wave: 9
    parallel:
      - A-019
      - A-020
```

**Deletions:** none

---

## Anomaly 2 — G-005/T-001 README vs A-008 file

### Evidence

**Tactical README path:**  
`docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/README.yaml`

**Listed in README:** A-001, A-002, A-003, A-004, A-005, A-006, A-007 (7 ids)

**On disk but not listed:** `A-008-cross-drop-mtime-producer.yaml`

### Legitimacy assessment — A-008

| field | value | check |
|-------|-------|-------|
| step_id | A-008 | ✓ |
| parent_tactical_step | T-001 | ✓ |
| name | Drop mtime from normalize_cross_finding and delete _source_mtime machinery | ✓ |
| target_file | `code_analysis/commands/search_paginated_cross.py` | ✓ production code |
| operation | modify_file | ✓ |
| priority | 1 | ✓ unique on this file |
| depends_on | A-002 | ✓ resolves within TS |
| concepts | C-026 | ✓ matches TS SearchSessionFinding scope |
| verification | pytest → `tests/unit/test_search_paginated_cross.py` | ✓ complete |
| status | ready_for_review | ✓ |

**Justification:** Well-formed production-code AS implementing C-026 no-mtime contract on the cross-search adapter. Already listed in sibling file `atomic_steps/parallel-waves.yaml` wave 2 (`A-003`, `A-004`, `A-005`, `A-008`). README omission is the only inconsistency.

**Direction:** README is stale → ADD A-008. No file deletion.

**Note on A-006/A-007:** Both are listed in README and on disk. They target plan artifacts (`spec.yaml`, `source_spec.md`) as verify-first cascade alignment steps — legitimate per current TS scope (re-added after convergence pass plan-doc purge per audit trail). Not part of this anomaly.

### Priority uniqueness check (post-reconciliation)

All eight steps use priority 1 on **distinct** target_files — **no collisions**.

### Mechanical edit instruction

**File:** `docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/README.yaml`

**Field:** `atomic_steps:` (lines 46–53)

**BEFORE:**
```yaml
atomic_steps:
- A-001
- A-002
- A-003
- A-004
- A-005
- A-006
- A-007
```

**AFTER:**
```yaml
atomic_steps:
- A-001
- A-002
- A-003
- A-004
- A-005
- A-006
- A-007
- A-008
```

**Deletions:** none

**parallel-waves.yaml:** already includes A-008 in wave 2 — **no edit needed**.

---

## Anomaly 3 — G-007 absent / dangling references

### Evidence

| check | result |
|-------|--------|
| `G-007-identity-remap-integration/` on disk | **Absent** |
| `git ls-files docs/plans/marked_tree_unification/G-007*` | **Empty** (not tracked) |
| HRS `source_spec.md` line 25 | `"There is no G-007 step"` — explicit retirement |
| `G-006-node-id-map/README.yaml` lines 12–14 | States identity-remap integration step retired; absorbed into G-001–G-006 |
| `concept_gs_matrix.yaml` | Lists G-000–G-006 only; no G-007 |
| All `G-*/README.yaml` under plan | **Zero** `G-007` references in `depends_on`, `tactical_steps`, or descriptions |
| Atomic step prompts mentioning G-007 | G-004/T-001 A-002, A-005, A-006, A-007 and G-006/T-001 A-001 — **negative constraints** ("NO G-007", "Do NOT reference G-007"); not execution dependencies |

### Verdict

**NO EDIT NEEDED.** G-007 retirement is consistent across HRS, MRS coverage matrix, G-006 README, and disk layout. Remaining G-007 strings are intentional guardrails in atomic prompts, not dangling references to an active global step.

### Mechanical edit instruction

**no references found requiring edit in plan tree — no edit needed**

---

## Anomaly 4 — G-006 folder naming (`G-006-node-id-map` vs `G-006-universal-node-id`)

### Evidence

| check | result |
|-------|--------|
| Directories on disk | **`G-006-node-id-map/` only** |
| `G-006-universal-node-id/` on disk | **Absent** |
| `git ls-files .../G-006-universal-node-id*` | **Empty** |
| Path refs to `G-006-universal-node-id` in plan tree | **Zero** (grep across `docs/plans/marked_tree_unification/`) |
| Path refs to `universal-node-id-functions` | **Zero** |
| Canonical slug in active AS | `G-006-node-id-map/T-001-node-id-map-module/` (A-001 prompt lines 15–16) |
| `concept_gs_matrix.yaml` | G-006 → C-024, C-025 |
| Audit record F-002 | Rename `G-006-universal-node-id` → `G-006-node-id-map` marked **resolved** |

Prose mentions of "former universal-node-id block" in `source_spec.md`, `spec.yaml`, and `G-006-node-id-map/README.yaml` are historical context, not path references to a non-existent directory.

### Verdict

**NO EDIT NEEDED.** Canonical folder is `G-006-node-id-map/`. Stale duplicate tree already removed; no dangling path references remain.

### Mechanical edit instruction

**no references found, no edit needed**

---

## New anomalies discovered (beyond the original four)

### N-001 — G-000/T-003 `parallel-waves.yaml` stale (covered above)

Included in Anomaly 1 edit checklist as a required companion edit.

### N-002 — No priority collisions after reconciliation

Cross-checked all 20 T-003 AS and all 8 T-001 AS post-ADD — **no duplicate (target_file, priority) pairs**.

### N-003 — Logical sequencing note (informational, not a blocking edit)

`tree_builder.py` receives A-010 (docstring cleanup, p=10) before A-012 (slim after extract, p=11). A-011 (extract to `tree_builder_index.py`, p=10, depends_on A-009) runs in parallel with A-010 (different files). This matches the convergence-pass split design and the wave-map critical path A-009 → A-011 → A-012. **No mechanical edit required** — priorities are valid; coordinators should respect `depends_on` A-011 → A-012 chain.

---

## Edit checklist

| # | Operation | File path |
|---|-----------|-----------|
| 1 | **MODIFY** — extend `atomic_steps` list A-001..A-010 → A-001..A-020 | `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/README.yaml` |
| 2 | **MODIFY** — append waves 5–9 for A-011..A-020 | `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/parallel-waves.yaml` |
| 3 | **MODIFY** — extend `atomic_steps` list A-001..A-007 → A-001..A-008 | `docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/README.yaml` |

**Total files to edit:** 3  
**Total files to delete:** 0

---

## Post-edit verification (coder)

1. For each modified README: `atomic_steps` list length equals count of `A-*.yaml` files in sibling `atomic_steps/` directory (excluding `parallel-waves.yaml`).
2. G-000/T-003: 20 AS files ↔ 20 ids in README.
3. G-005/T-001: 8 AS files ↔ 8 ids in README.
4. Re-run priority-uniqueness per `(tactical_step, target_file)` — expect zero collisions.
5. Confirm G-007 directory still absent and no new G-007 path references introduced.
6. Confirm only `G-006-node-id-map/` exists under plan root for step_id G-006.
