# Phase 3 Atomic Layer — STEP 0 Zero-Trust Inventory

**Plan:** `docs/plans/marked_tree_unification/`  
**Date:** 2026-05-30  
**Scope:** Read-only inventory of all `A-*.yaml` on disk (excluding `docs/_archive/`).  
**Governance:** `atomic_step_creation_standard.yaml` (a1–a10), locked decisions A1/A2/C1, FINAL-1/FINAL-2.

---

## 1. AS count per global step (before changes)

| GS | TS count | AS on disk | Breakdown by TS |
|----|----------|------------|-----------------|
| **G-000** sidecar-layout-migration | 3 | **15** | T-001: 1; T-002: 4; T-003: 10 |
| **G-001** marker-contract-and-format-handlers | 3 | **11** | T-001: 2; T-002: 7; T-003: 2 |
| **G-002** tree-storage-and-lifecycle | 4 | **4** | T-001: 1; T-002: 1; T-003: 2; **T-004: 0** |
| **G-003** edit-session-and-git-api | 3 | **12** | T-001: 3; T-002: 4; T-003: 5 |
| **G-004** edit-operations-preview-and-tree-query | 3 | **11** | T-001: 7; T-002: 2; T-003: 2 |
| **G-005** consumer-integration | 3 | **12** | T-001: 7; T-002: 4; T-003: 1 |
| **G-006** universal-node-id | 1 | **1** | T-001: 1 |
| **G-007** identity-remap-integration | 1 | **7** | T-001: 7 |
| **TOTAL** | **21 TS** | **73 AS** | |

**TS↔disk drift (README `atomic_steps` vs files):**

| TS | Listed in README | On disk | Drift |
|----|------------------|---------|-------|
| G-001/T-002 | A-001…A-008 | A-001…A-007 | **A-008 missing** (python-cst-deferral-tracker) |
| G-002/T-003 | A-001, A-002, A-003 | A-001, A-002 | **A-003 missing** (parallel-waves wave 2 package init) |
| G-002/T-004 | A-001, A-002 | *(none)* | **Entire AS set missing**; `atomic_steps/` dir absent |
| G-000/T-* | Matches disk | 15 | OK (TS READMEs list steps) |

---

## 2. Full stale AS list (scope-aware)

Only flags where the AS domain should encode Phase 1/2/2b locked wording.

### G-000 (legacy cutover — expected stale vs A1; not Phase 3 rewrite target)

| step_id | File | Stale reason |
|---------|------|--------------|
| A-007 | `G-000/.../A-007-checksum-drop-dead-fallback.yaml` | Uses `TreeFormatKind` / `recreate_tree_from_content(kind=…)`; no parity-oracle / new-alongside-old text (acceptable for G-000 scope but pre-A1) |

### G-002 (unified pipeline — **high priority**)

| step_id | File | Stale reason |
|---------|------|--------------|
| A-001 | `G-002/T-002/.../A-001-checksum-sync-policy-class.yaml` | Embeds legacy `recreate_tree_from_content` / `TreeFormatKind` context without A1 HandlerRegistry path or parity-oracle note |
| A-001 | `G-002/T-003/.../A-001-tree-lifecycle-and-builder-classes.yaml` | **Old {c005} kind-dispatch** in prompt (`dispatch by format kind`, HRS `{c005}` verbatim); **missing A1** (`HandlerRegistry.default_registry().resolve`); verification imports `TreeFormatKind`; no parity strategy; **superseded** by intended `builder.py` AS (not on disk) |
| A-002 | `G-002/T-003/.../A-002-tree-lifecycle-package-init.yaml` | Re-exports legacy checksum symbols; no new-alongside-old / A1 encoding |

### G-003 (edit session — **high priority**)

| step_id | File | Stale reason |
|---------|------|--------------|
| A-001 | `G-003/T-001/.../A-001-edit-session-entity.yaml` | **Old {d002}** — no FINAL-2 (content only when non-existent/broken); **old {d003}** — no hide/unhide, no unmark-export per mutation, no DEGRADED invalid path; **missing {h008}** tree-validity state field; **missing {h009}** re-validation via `TreeBuilder.build` |
| A-003 | `G-003/T-001/.../A-003-active-session-registry.yaml` | Same {d002}/{d003}/{h008} gaps (embeds stale open/edit flow from A-001) |
| A-001 | `G-003/T-002/.../A-001-session-repo-module.yaml` | **Old {d003}** — tree-only commits; **missing DEGRADED** dual commit shape (source-only when invalid per {h008}/{d003}) |
| A-003 | `G-003/T-002/.../A-003-edit-session-wire-session-repo.yaml` | Same {d002}/{d003} gaps in embedded `EditSession` |
| A-004 | `G-003/T-002/.../A-004-declare-dulwich-dependency.yaml` | References open protocol without FINAL-2 |

**Not stale (current):** `G-003/T-003/A-005-session-git-diff-command.yaml` — includes **source mode** vs tree mode ({e003} satisfied).

### G-004 (edit gate + preview FINAL-1)

| step_id | File | Stale reason |
|---------|------|--------------|
| A-001 | `G-004/T-002/.../A-001-preview-selector.yaml` | **Missing FINAL-1 {i005}-{i008}**: no `full_text_max_lines`, drilldown-only (zero), max_chars envelope rule |
| A-002 | `G-004/T-002/.../A-002-preview-navigation.yaml` | **Missing FINAL-1**: no `[node_id]` line-prefix rendering, IndentedBlock transparency, JSON pretty-print before line count, legacy Python comment strip, per-format thresholds |
| A-005 | `G-004/T-001/.../A-005-yaml-handler-edit-operations.yaml` | **Missing {h008}/{h009}** at handler/delegation boundary (TS requires tree-validity edit gate) |
| A-006 | `G-004/T-001/.../A-006-json-handler-edit-operations.yaml` | Same edit-gate gap |
| A-007 | `G-004/T-001/.../A-007-python-handler-edit-operations.yaml` | Same edit-gate gap |

**Not stale for edit gate:** `A-002-edit-operations-dispatch.yaml` — prompt includes tree-validity edit gate and `tree_is_valid` parameter.

### G-001 (locked A2/C1)

| step_id | File | Stale reason |
|---------|------|--------------|
| *(none on disk)* | TS lists **A-008** deferral tracker | Listed but absent; if deferral is resolved-in-plan, TS should drop A-008 or AS should record `resolved_in_plan` |

**Not stale:** `G-001/T-002/A-007-python-handler.yaml` — encodes **A2/C1** (cst_tree wrapper, {b005}, forbids NotImplementedError).

### Universal marker {b000}

No AS prompt cites HRS `{b000}`. **G-006/T-001/A-001** covers C-024 `universal_node_id.py` separately; **G-007** wires remap. Gap is plan-level: marker-contract AS do not cross-reference `{b000}` / all-nodes universal marker (may be intentional deferral to G-006/G-007).

---

## 3. a10 coverage gaps per TS

### G-002/T-004 — Unified pipeline integration (**critical**)

**TS excerpt (outputs):**
> Canonical TreeLifecycle routing wired to unified build … Parity verification suite comparing unified-pipeline tree output against the legacy parity oracle …

**Gap:** **Zero AS files on disk.** TS README lists A-001, A-002; `parallel-waves.yaml` defines waves but `atomic_steps/` directory does not exist. Entire TS uncovered at atomic layer.

**Missing from AS set:** wire `validate_or_recreate_from_content` → `TreeBuilder.build`; parity test module; A1 + new-alongside-old encoding.

---

### G-002/T-003 — TreeLifecycle and TreeBuilder

**TS excerpt:**
> TreeBuilder.build resolves HandlerRegistry … T-003 defines skeletons only; wiring is T-004 …

**Gap:**
- Only **A-001-tree-lifecycle-and-builder-classes.yaml** (lifecycle.py wrappers, **stale {c005}**) and **A-002 package init** exist.
- TS lists **A-003** (wave 2 init per `parallel-waves.yaml`) — **missing**.
- Intended **A-001-tree-builder-class.yaml** (`builder.py`, A1-compliant) referenced in archive/assignment docs — **not on disk**.
- **Duplicate step_id A-001** conflict: one stale lifecycle.py AS vs missing builder.py AS.

---

### G-001/T-002 — Format handlers

**TS lists A-008** (python-cst-deferral-tracker); **file absent**. Either author A-008 as `resolved_in_plan` doc-only step or remove from TS `atomic_steps`.

---

### G-003/T-001 — EditSession lifecycle

**TS excerpt (outputs):**
> FINAL-2 content-supply on open; tree-validity-state tracking {h008}; dual-mode edit (valid — hide/restore + full {d003}; invalid — plain-text + DEGRADED {d003}/{h008}); re-validation {h009}; atomic copy-out; blind close.

**Gap:** AS A-001..A-003 implement **pre-Phase-2b** four-phase skeleton:
- No `content` parameter / FINAL-2 guards on `open()`
- No `is_invalid` / tree-validity state
- No hide/unhide / unmark-export / checksum recording per mutation
- No DEGRADED plain-text edit path
- No re-validation hook

---

### G-003/T-002 — SessionRepo

**TS excerpt:**
> When valid each commit captures both tree + unmark-exported source; when invalid (DEGRADED) each commit captures source-only.

**Gap:** A-001 SessionRepo prompt describes **tree-only** one-commit-per-mutation; no dual commit shape by validity state.

---

### G-003/T-003 — SessionGitApi

**Coverage:** A-001..A-005 present for log/show/status/revert/diff. **A-005 includes source mode** — largely aligned with TS. Minor: no AS wires session commands to EditSession mutation paths (integration AS may be needed later).

---

### G-004/T-001 — Edit operations + edit gate

**TS output:** Tree-validity edit gate {h008}/{h009}.

**Gap:** Dispatch layer (A-002) covers gate; **handler edit-op AS A-005..A-007** delegate to legacy tree-temp engines without encoding valid/invalid mode or hide/unhide (session responsibility per TS, but gate enforcement at apply boundary incomplete in prompts).

---

### G-004/T-002 — Preview FINAL-1

**TS excerpt:**
> full_text_max_lines default 200; inline vs drilldown; `[node_id]` line prefix; JSON pretty-print before line count; IndentedBlock transparent; legacy Python identity comment strip.

**Gap:** A-001 PreviewSelector and A-002 PreviewNavigation omit **all FINAL-1 {i005}-{i008}** semantics.

---

### G-005, G-006, G-007

- **G-005:** TS READMEs match disk (12 AS). a10 gaps limited to a9 on T-001 A-003..A-007.
- **G-006:** Single AS; covers C-024 functions — aligned with TS.
- **G-007:** Seven AS; depends_on empty on A-001 — **ordering risk** (should depend on G-006 + G-004 preview/edit base).

---

## 4. a9 gaps (verification completeness)

**Standard:** `type` ∈ {pytest, import, static_analysis, manual}; `target` and `expected` required prose.

| step_id | File | Missing / invalid |
|---------|------|-------------------|
| A-003 | `G-005/T-001/.../A-003-block-assembler-drop-mtime-sort.yaml` | **expected** absent |
| A-004 | `G-005/T-001/.../A-004-ggrep-drop-mtime-zero.yaml` | **expected** absent |
| A-005 | `G-005/T-001/.../A-005-tree-query-drop-mtime-zero.yaml` | **expected** absent |
| A-006 | `G-005/T-001/.../A-006-mrs-and-readme-sync.yaml` | **expected** absent; **type: yaml_lint** (not allowed) |
| A-007 | `G-005/T-001/.../A-007-hrs-and-spec-drop-g004.yaml` | **expected** absent; **type: yaml_lint** (not allowed) |

**All other 68 AS:** verification block present and a9-complete (note: some `expected` fields contain inline code snippets — flagged in prior G-001 audit as style violation but fields are populated).

---

## 5. a3 size risks (embedded file content in prompts >400 lines)

| step_id | File | Embedded lines (max ``` block) | Risk |
|---------|------|-------------------------------|------|
| A-002 | `G-000/T-003/.../A-002-write-command-drop-promote-pending.yaml` | **515** | **violation** — post-prior state alone exceeds 400 |
| A-006 | `G-000/T-003/.../A-006-tree-saver-drop-promote-pending.yaml` | **403** | **violation** |
| A-008 | `G-000/T-003/.../A-008-move-nodes-command-sibling-cutover.yaml` | **381** | borderline (under 400 file limit but large) |
| A-001 | `G-005/T-003/.../A-001-indexer-checksum-skip-guard.yaml` | **372** | borderline |

**Additional note:** `G-003/T-001/A-001-edit-session-entity.yaml` embeds ~230 lines of target Python — combined with prompt prose may approach budget limits but under 400.

---

## 6. depends_on / wave ordering issues

### Cross-TS depends_on notation (G-000)

Several G-000 AS use non-standard depends_on values (`A-001 (T-001)`) — valid as prose cross-TS deps but not parseable as A-NNN within TS (a7 style).

### Phase ordering vs locked stack

| Issue | Detail |
|-------|--------|
| **ChecksumSyncPolicy before TreeBuilder** | G-002 T-002 A-001 has no cross_ts on G-001; OK within G-002. Missing **builder.py AS** breaks T-003→T-004 chain. |
| **Marker contract before handlers** | G-001 T-002 handler AS depend on same-TS A-001 (FormatHandler base) — OK. G-001 T-003 A-003 `default_registry` has **empty depends_on** — should declare T-002 A-003..A-007. |
| **G-002 T-004 after T-003** | parallel-waves correct; **AS files missing**. |
| **G-007 after stack** | G-007 A-001..A-005 have **empty depends_on**; A-006/A-007 depend only on same-TS identity-map steps — **missing G-006 and G-004 prerequisites**. |
| **G-005 T-002 A-001** | depends_on `['A-002', 'A-004']` within T-002 — schema before persist — OK. |
| **G-003 T-001 priority** | A-002 and A-003 both **priority 2** on different files — valid (local per file). |

### G-004/T-001 handler edit-op priorities

A-003/A-004 share priority 3 (different files — OK). A-005/A-006/A-007 share priority 1 on different files — OK. **Logical order:** A-005..A-007 should depend on G-001 handler create steps (cross-TS) — not declared.

---

## 7. File paths — all 73 A-*.yaml (sorted)

```
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-001-path-resolution/atomic_steps/A-001-tree-sidecar-sibling-cutover.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-002-write-path/atomic_steps/A-001-delete-sidecar-paths.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-002-write-path/atomic_steps/A-002-write-commit-sibling.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-002-write-path/atomic_steps/A-003-open-support-sibling.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-002-write-path/atomic_steps/A-004-tree-temp-init-drop-trees-reexport.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-001-tree-representation-sibling-cutover.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-002-write-command-drop-promote-pending.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-003-grep-block-resolver-sibling.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-004-stable-tree-sibling-cutover.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-005-close-command-drop-promote-pending.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-006-tree-saver-drop-promote-pending.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-007-checksum-drop-dead-fallback.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-008-move-nodes-command-sibling-cutover.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-009-test-tree-sidecar-sibling-alignment.yaml
docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/T-003-read-path-and-consumers/atomic_steps/A-010-tree-builder-docstring-cst-cleanup.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-001-marker-contract-and-node-id/atomic_steps/A-001-tree-package-init.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-001-marker-contract-and-node-id/atomic_steps/A-002-contracts.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-001-format-handler-base.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-002-handlers-package-init.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-003-text-handler.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-004-markdown-handler.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-005-yaml-handler.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-006-json-handler.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-002-format-handlers/atomic_steps/A-007-python-handler.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-003-handler-registry-and-tree-node/atomic_steps/A-001-tree-node.yaml
docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/T-003-handler-registry-and-tree-node/atomic_steps/A-002-handler-registry.yaml
docs/plans/marked_tree_unification/G-002-tree-storage-and-lifecycle/T-001-sibling-storage-convention/atomic_steps/A-001-sibling-convention-module.yaml
docs/plans/marked_tree_unification/G-002-tree-storage-and-lifecycle/T-002-checksum-sync-policy/atomic_steps/A-001-checksum-sync-policy-class.yaml
docs/plans/marked_tree_unification/G-002-tree-storage-and-lifecycle/T-003-tree-lifecycle-and-builder/atomic_steps/A-001-tree-lifecycle-and-builder-classes.yaml
docs/plans/marked_tree_unification/G-002-tree-storage-and-lifecycle/T-003-tree-lifecycle-and-builder/atomic_steps/A-002-tree-lifecycle-package-init.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-001-edit-session-lifecycle/atomic_steps/A-001-edit-session-entity.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-001-edit-session-lifecycle/atomic_steps/A-002-edit-session-package-init.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-001-edit-session-lifecycle/atomic_steps/A-003-active-session-registry.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-002-session-repo/atomic_steps/A-001-session-repo-module.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-002-session-repo/atomic_steps/A-002-session-repo-package-export.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-002-session-repo/atomic_steps/A-003-edit-session-wire-session-repo.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-002-session-repo/atomic_steps/A-004-declare-dulwich-dependency.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-003-session-git-api/atomic_steps/A-001-session-git-log-command.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-003-session-git-api/atomic_steps/A-002-session-git-show-command.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-003-session-git-api/atomic_steps/A-003-session-git-status-command.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-003-session-git-api/atomic_steps/A-004-session-git-revert-command.yaml
docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/T-003-session-git-api/atomic_steps/A-005-session-git-diff-command.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-001-format-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-002-edit-operations-dispatch.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-003-text-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-004-markdown-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-005-yaml-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-006-json-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-001-edit-operations/atomic_steps/A-007-python-handler-edit-operations.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-002-preview-navigation-and-selector/atomic_steps/A-001-preview-selector.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-002-preview-navigation-and-selector/atomic_steps/A-002-preview-navigation.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-003-tree-query-and-cst-selector/atomic_steps/A-001-cst-query-selector.yaml
docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/T-003-tree-query-and-cst-selector/atomic_steps/A-002-tree-query.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-001-grep-tree-lifecycle-routing.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-002-grep-source-mtime-invariant.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-003-block-assembler-drop-mtime-sort.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-004-ggrep-drop-mtime-zero.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-005-tree-query-drop-mtime-zero.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-006-mrs-and-readme-sync.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-001-grep-consumer-integration/atomic_steps/A-007-hrs-and-spec-drop-g004.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-002-watcher-integration/atomic_steps/A-001-watcher-tree-lifecycle-precondition.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-002-watcher-integration/atomic_steps/A-002-watcher-checksum-persist-idempotent-schema.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-002-watcher-integration/atomic_steps/A-003-schema-version-bump.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-002-watcher-integration/atomic_steps/A-004-persist-tree-checksum-in-file-row.yaml
docs/plans/marked_tree_unification/G-005-consumer-integration/T-003-indexer-checksum-guard/atomic_steps/A-001-indexer-checksum-skip-guard.yaml
docs/plans/marked_tree_unification/G-006-universal-node-id/T-001-universal-node-id-functions/atomic_steps/A-001-universal-node-id-functions.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-001-apply-identity-remap.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-002-identity-map-markdown-handler.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-003-identity-map-yaml-handler.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-004-identity-map-json-handler.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-005-identity-map-python-handler.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-006-remap-in-preview-navigation.yaml
docs/plans/marked_tree_unification/G-007-identity-remap-integration/T-001-remap-in-preview-and-edit/atomic_steps/A-007-remap-in-edit-operations.yaml
```

**Absent but referenced:** `G-002/T-004/atomic_steps/A-001-wire-validate-to-unified-build.yaml`, `A-002-parity-test-module.yaml`, `G-002/T-003/atomic_steps/A-001-tree-builder-class.yaml`, `G-001/T-002/atomic_steps/A-008-python-cst-deferral-tracker.yaml`.

---

## Executive summary (Phase 3 dovodka priorities)

1. **Author G-002/T-004 AS from scratch** (2 steps) — blocks unified pipeline completion.
2. **Replace/supplement G-002/T-003 A-001** with A1-compliant `builder.py` AS; resolve duplicate A-001 / missing A-003.
3. **Rewrite G-003/T-001 and T-002 AS** for FINAL-2, {d003} hide/unhide + DEGRADED, {h008}/{h009}.
4. **Rewrite G-004/T-002 AS** for FINAL-1 {i005}-{i008}.
5. **Fix G-005/T-001 A-003..A-007 a9** (5 verification gaps).
6. **Split or trim G-000/T-003 A-002, A-006** (a3 >400 embedded lines).
7. **Add cross_ts_depends_on** on G-001/T-003 A-003, G-007 A-001, G-004 handler edit ops.
