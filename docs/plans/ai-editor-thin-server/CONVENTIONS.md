# ai-editor-thin-server — Plan Conventions

This document records **accepted deviations** from the planning standards (`docs/standards/planning/*.yaml`) for the `ai-editor-thin-server` plan. These decisions were made by the global orchestrator. Future verification passes should treat them as **documented conventions**, not defects.

**Plan root:** `docs/plans/ai-editor-thin-server/`

---

## F-009 — Global Step Count (10 steps)

**Standard reference:** `plan_standard_machine.yaml` — `global_step.count_guidance`: `typical_range: [3, 7]`, `indicator_threshold: 10` (indicator, not a hard limit).

**Decision:** Keep **10 global steps** (G-001 through G-010). Do **not** merge steps.

**Rationale:** The assignment scope decomposes naturally into 10 independent workstreams:

1. Workspace/session directories  
2. Upstream CA client  
3. Open/close orchestration  
4. Edit-engine adaptation  
5. Write/compare/upload  
6. MCP surface cleanup  
7. Broken-session policy  
8. Client facade  
9. Legacy removal  
10. Acceptance tests  

Merging would couple independent branches and trigger a large cascade with no structural benefit.

**Maintenance note:** If scope changes materially, reassess step count against `count_guidance` before adding or removing global steps.

---

## F-065 — Atomic Step Artifact Layout

**Standard reference:**

- `atomic_step_creation_standard.yaml` § `artifact_location`: `docs/plans/<plan_name>/G-NNN-<slug>/T-NNN-<slug>/atomic_steps/A-NNN-<slug>.yaml` (per-directory README variant also cited in some standards text)
- `plan_standard_machine.yaml` level-5: atomic steps **inline** under tactical-step `README.yaml`

**Decision:** Accept the **existing** layout for this plan:

```
docs/plans/ai-editor-thin-server/G-*/T-*/atomic_steps/<A-NNN-slug>.yaml
```

Do **not** migrate the current ~106 atomic-step files to inline TS README or per-step directory layouts.

**Rationale:** The `atomic_steps/*.yaml` tree is already complete and executable. Migration would be high churn with no execution benefit.

**Maintenance note:** New atomic steps for this plan should continue to use `atomic_steps/<A-NNN-slug>.yaml` under the parent tactical-step directory.

---

## Source Binding Mechanism — `source_ranges` (line ranges)

**Standard reference:** `plan_standard_machine.yaml` level-1 — binding paragraphs use stable `{xxxx}` paragraph labels in `source_labels` on machine_spec and global steps.

**Decision:** This plan binds level-2 (`spec.yaml`) and level-3 (global-step `README.yaml`) artifacts to `source_spec.md` via **`source_ranges`** (line-number ranges), not `{xxxx}` `source_labels`.

**Rationale:** Adopted during plan authoring for this repository snapshot; changing the binding mechanism now would require a broad, low-value rework across plan artifacts.

**Maintenance note:** Line-range bindings are **position-sensitive**. Any edit to `source_spec.md` that shifts line numbers requires re-checking and updating `source_ranges` on affected `spec.yaml` and global-step files. Prefer localized edits; after structural edits to `source_spec.md`, run consistency verification on source binding coverage.

---

## Infrastructure tactical step (G-007 T-000)

**Standard reference:** `tactical_step_creation_standard.yaml` — tactical steps refine global steps into concrete entities and actions; infrastructure concerns are typically folded into application global steps rather than isolated as separate tactical steps.

**Decision:** Accept **T-000** (`oversized-command-split`) under **G-007** as a dedicated infrastructure tactical step.

**Rationale:** Three oversized editor command modules (open, write, preview families) must be split into facade+runtime pairs before G-003 and G-004 can implement orchestration and edit-engine adaptation within the plan's 400-line file limit. The split is structural groundwork for broken-session policy work in the same global step, not an independent product feature.

**TS count note:** Plan-wide tactical-step count is **48** versus a typical expectation of **47** specifically because of T-000. This is **accepted, not a defect**. T-000 produces the facade/runtime module split that G-003 and G-004 depend on.

**Maintenance note:** Do **not** flag TS-count mismatch in future verification passes for this plan.

---

## F-001 — Structural Lines Outside `source_ranges` (DEFERRED)

**Standard reference:** Invariant I1.c — union of source bindings should cover binding content in `source_spec.md`.

**Finding:** Some structural lines in `source_spec.md` (section headings `## …` and blank lines) fall outside the union of `source_ranges`.

**Status:** **DEFERRED** — `source_spec.md` is human-owned and was intentionally **not** edited during the fix campaign.

**Resolution options (human decision):**

| Option | Action |
|--------|--------|
| (a) | Wrap structural headings and incidental blank lines in `<!-- non-binding -->` … `<!-- /non-binding -->` markers in `source_spec.md` |
| (b) | Accept as a known minor deviation and document in verification reports |

**Orchestrator note:** Do not auto-fix F-001; await explicit human choice between (a) and (b).
