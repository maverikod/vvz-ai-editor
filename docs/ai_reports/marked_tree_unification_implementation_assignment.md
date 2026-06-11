# Marked Tree Unification — Plan State & Coding Handoff

**Plan:** `marked_tree_unification`  
**Repository root:** `/home/vasilyvz/projects/tools/code_analysis`  
**Date:** 2026-05-30  
**Status:** Plan dovodka Phase F **GREEN** — ready for code execution

> **Audience:** coder models, implementers, plan maintainers, and orchestrators. **Task:** execute atomic steps in dependency order. **Do not edit HRS (`source_spec.md`)** without human authorization; MRS changes only via cascade.

All paths below are **repo-relative** to the repository root unless stated otherwise.

---

## Current plan state

Snapshot as of 2026-05-30 (node-id cascade + Phase F close-out):

| Layer | Status |
|-------|--------|
| HRS (`source_spec.md`) | **overall_green: true** — approved, user-owned; node-id labels cascaded ({a007}, {n001}–{n003}); retired {l001}–{l003}, {m001}, {m002} |
| MRS (`spec.yaml`) | Aligned; C-024 TreeNodeUuid (MAP-only UUID4); C-025 NodeIdMap; C-026 SearchSessionFinding (no mtime); cycle_1 c1–c3 green |
| Global steps | **7** — G-000 through G-006; **G-007 removed** (directory absent on disk) |
| Tactical steps | **21/21 green** (Phase F sweep) |
| Atomic steps | **85** total; **atomic GREEN** — Phase F F-001–F-004 resolved |
| TS README ↔ disk A-*.yaml | **0 mismatches** (1:1) |
| `cross_ts_depends_on` YAML fields in AS files | **0** |
| `step_id_prose` in AS prompts | **0** |

### Per-GS tactical and atomic inventory

| GS | TS count | AS count | GS status on disk |
|----|----------|----------|-------------------|
| G-000 | 3 | 25 | `ready_for_review` |
| G-001 | 3 | 13 | `needs_review` |
| G-002 | 4 | 7 | `needs_review` |
| G-003 | 4 | 14 | `ready_for_review` |
| G-004 | 3 | 11 | `ready_for_review` |
| G-005 | 3 | 14 | `ready_for_review` |
| G-006 | 1 | 1 | `ready_for_review` |

**Totals:** 21 TS READMEs, 85 AS files on disk.

**G-003 delta (prior cascade):** +1 TS (T-004 session-write-command), +1 AS (`session_write` MCP); four existing AS revised for two-stage WRITE (`{d004}` preview / `{n7k2}` confirm). GS-level `G-003/parallel-waves.yaml` adds wave_5 for T-004/A-001.

**Node-id cascade delta:** G-007 removed (−7 AS); G-000 +9 AS, G-001 +1 AS, G-005 +3 AS; G-006 repurposed to NodeIdMap (1 AS). Authoritative record: `marked_tree_unification_dovodka_audit.yaml` → `node_id_cascade_phase_f` (supersedes `full_plan_reverify` at 79 AS / 8 GS).

### Verification layer summary

| Gate | Verdict | Notes |
|------|---------|-------|
| Phase A — HRS/MRS cascade (node-id model) | green | UUID4 MAP-only; short_id markers; 3-section tree file |
| Phase B — GS I1 + cycle_2 | green | 7 GS triples; G-007 absent |
| Phase C — Tactical t5–t13 | green | 21/21 TS |
| Phase D — Atomic a1–a10 per GS | green | F-001–F-004 resolved |
| Phase E — Cascade phases | green | Per parent orchestrator |
| Phase F — Final sweep | green | Close-out 2026-05-30; F-001–F-004 resolved |
| cycle_1 (c1–c3) | green | Binding HRS labels covered; retired {l*}/{m*} removed from active model |
| cycle_2 | green | All 7 GS triples autonomous |
| Tactical overall_green | green | 21/21 TS |
| Atomic overall_green | green | Phase F close-out; F-001–F-004 resolved |
| I1 (plan level) | green | GS concepts ≡ MRS; source_labels cover binding paragraphs |
| I2 (plan level) | pending | Execute AS per verification fields during code implementation |

**Audit record:** `docs/ai_reports/marked_tree_unification_dovodka_audit.yaml` (authoritative `node_id_cascade_phase_f`; `full_plan_reverify` retained for two-stage WRITE history).

**Historical review package:** `docs/ai_reports/marked_tree_unification_hrs_review_package.md` (audit trail only; superseded by canonical plan).

### Governing standards (reference for coders)

| Standard | Path |
|----------|------|
| Plan structure, cascade, invariants I1–I3 | `docs/standards/planning/plan_standard_machine.yaml` |
| HRS↔MRS and GS triple autonomy | `docs/standards/planning/hrs_mrs_gs_consistency_verification_standard.yaml` |
| Tactical layer | `docs/standards/planning/tactical_step_creation_standard.yaml` |
| Atomic layer | `docs/standards/planning/atomic_step_creation_standard.yaml` |

---

## Context & goal

**Plan name:** `marked_tree_unification`

**What it is:** A development plan to replace fragmented per-format tree storage and editing paths with a **unified marked-tree pipeline**. Every supported source format (Python, JSON, YAML, Markdown, plain text) gets a `FormatHandler` that embeds **short_id** markers in tree content (TREE section), stores a co-located sibling tree file with CHECKSUMS→MAP→TREE layout (`<stem>.<ext>.tree`), and participates in a single lifecycle module (`core/tree_lifecycle/`) for validity checks and tree creation. External API uses **(file path, short_id)** only.

**Handoff goal:** Execute atomic steps in canonical dependency order to implement the plan in production code. Planning is complete; coders read AS prompts only (self-contained per atomic step standard).

**Unified pipeline (plan semantics):** One canonical build path — `HandlerRegistry.default_registry().resolve(source_abs)` → `FormatHandler.mark` → write sibling tree → record checksum — serves preview, edit sessions, grep, watcher, and indexer. Edit sessions use a **session directory** next to the source file with ephemeral dulwich git history, per-mutation commits (`{d003}`), and **two-stage WRITE** (`{d004}` preview diffs in-session vs live external files; `{n7k2}` confirm atomically copies both artefacts only on explicit confirmation — `session_write` MCP in G-003/T-004). Legacy paths (`recreate_tree_from_content`, `.cst/` JSON sidecars, `.trees/` mirror, `.tree_sidecar`) remain as **parity oracles** until global step G-000 cutover.

**Canonical execution order:** G-001 → G-002 → G-003 → G-004 → G-005 → **G-006** (NodeIdMap) → **G-000** (cutover). **G-007 removed** — no identity-remap global step.

**Canonical plan artifacts:**

| Artifact | Path |
|----------|------|
| Human-readable specification (HRS) | `docs/plans/marked_tree_unification/source_spec.md` |
| Machine-readable specification (MRS) | `docs/plans/marked_tree_unification/spec.yaml` |
| Global steps | `docs/plans/marked_tree_unification/G-*/README.yaml` |
| Tactical steps | `docs/plans/marked_tree_unification/G-*/T-*/README.yaml` |
| Atomic steps | `docs/plans/marked_tree_unification/G-*/T-*/atomic_steps/A-*.yaml` |
| Handoff audit | `docs/ai_reports/marked_tree_unification_dovodka_audit.yaml` |

---

## Locked decisions (do NOT re-open)

These decisions are **fixed** in HRS, MRS, GS, and AS prompts. Coders must implement them as specified; do not re-open during implementation.

### N0 — Node identity model (locked node-id cascade)

| Rule | Specification |
|------|---------------|
| **short_id** | Per-file monotonic integer marker embedded in the TREE section of the tree file; format-native syntax per handler |
| **Canonical identity** | UUID4 stored **MAP-only** (MRS **C-024 TreeNodeUuid**); never in marked content; never crosses external API |
| **Tree file layout** | Three ordered sections: **CHECKSUMS → MAP → TREE** |
| **NodeIdMap** | MRS **C-025** — exactly three operations: `build`, `validate_and_repair`, `resolve` (short_id↔UUID both directions) |
| **External API** | All commands (preview, edit, query, grep/indexer) address nodes as **(file path, short_id)** only |
| **G-006** | NodeIdMap module (single AS); absorbs per-format id wiring formerly scoped to G-007 |
| **G-007** | **REMOVED** — no identity-remap global step; directory absent on disk |
| **Preview prefix** | `[<short_id>]` at start of physical line; **minimal integer width** padding for column alignment |
| **SearchSessionFinding** | MRS **C-026** — finding record carries **no mtime** field |
| **Retired HRS labels** | `{l001}`, `{l002}`, `{l003}`, `{m001}`, `{m002}` — superseded by node-id model |
| **New HRS labels** | `{a007}` short_id allocation; `{n001}`–`{n003}` NodeIdMap / tree-file metadata tezises |

**HRS/MRS:** `{a001}`, `{a002}`, `{a007}`, `{n001}`–`{n003}`; C-024, C-025, C-026; G-006/T-001

### A1 — Unified pipeline via HandlerRegistry

The canonical tree build path is:

```
HandlerRegistry.default_registry().resolve(source_abs)
  → FormatHandler.mark(content)
  → write to FormatHandler.sidecar_path(source_abs)
  → record content_checksum in tree file AND returned reference
```

Entry point: `TreeBuilder.build(*, content, source_abs, file_path, content_checksum)` in `code_analysis/core/tree_lifecycle/builder.py` (or path specified by atomic steps). Dispatch by file extension through the registry — **not** by `TreeFormatKind` / `kind` parameter.

**HRS/MRS:** `{c005}`, C-010, C-011

### A2 — PythonHandler is external to default_registry parse path; thin wrapper over cst_tree

- `PythonHandler` is registered in `HandlerRegistry.default_registry()` like other format handlers.
- `parse_content` is a **thin wrapper** over existing `code_analysis/core/cst_tree` `create_tree_from_code`, adapting `metadata_map` → `List[TreeNode]` and mapping stable internal ids ↔ canonical UUID via NodeIdMap.
- `mark` / `unmark` implement the **short_id marker scheme** per HRS `{b005}` — integer short_id in metadata dict for named CST constructs; trailing `# ___id___:<short_id>` comment for others. **No UUID in markers.**
- **Do not** reuse the legacy `.cst/` JSON sidecar for marking. Python tree files use the sibling `<file>.py.tree` convention like all other formats.
- `unmark` must reproduce original source **byte-for-byte** (SHA-256 verified).

**HRS/MRS:** `{b005}`, C-001, C-007; G-001/T-002/A-007

### C1 — Python CST owned in this plan; G2-CORR-001 superseded

Cross-plan deferral record **G2-CORR-001** (Python CST integration delegated to `py_cst_tree_package`) is **superseded**. Python CST integration is **in scope** of `marked_tree_unification` via G-001/T-002/A-007 (`PythonHandler`). Deferral tracker A-008 records `resolved_in_plan`. AS prompts specify real `PythonHandler` — not `NotImplementedError` stub.

### Target edit-session lifecycle {d001}–{d006}

The HRS Block 4 (`{d001}`–`{d006}`) and Block 5 (`{e001}`–`{e006}`) define the **target** model. Current `code_analysis/commands/universal_file_edit/` uses an in-memory `EditSession` with `.draft` lockfiles — G-003 AS scope closes this gap in implementation.

**`{d001}` — Session directory model**

An edit session is a **directory** placed next to the source file:

- Directory name: `<FileName>-<UUID4>` where `FileName` is the source file base name and `UUID4` is a randomly generated UUID.
- Session TEMP artefacts inside mirror the project's source + tree layout; they are **not** the live project files until WRITE copy-out.

**`{d002}` — Open protocol + FINAL-2 content rule**

Opening performs four steps **in order**:

1. Create the session directory.
2. Copy the source file into the session directory.
3. Validate the co-located tree file by checksum — if valid, copy it into the session directory; if missing or invalid, build a new tree from source content inside the session directory.
4. Initialize a git repository (dulwich 1.2.4) inside the session directory and create the initial commit containing the source copy and the tree file.

**FINAL-2 content-supply rule:** When the caller supplies `content` on open:

- **Accepted ONLY** when the target file is **non-existent** OR its source/tree is **broken/corrupted** (invalid checksum, unreadable tree, or missing co-located tree where required).
- **ERROR** if the target file exists and is valid — supplying `content` is forbidden.
- When accepted: **first** write the provided source into the session code file, **then** follow the standard open protocol (build tree, write tree, record checksums, session git initial commit).

This rule applies to **all formats**.

**`{d003}` — Per-mutation invariant (full + DEGRADED)**

During an open session, the tree file inside the session directory is the **source of truth**.

**When tree is valid — full invariant before each mutation:**

1. Hide markers: any node metadata carrying markers is converted into format-native comments (or equivalent inline marker form) in the tree content.
2. Apply the mutation to the temporarily denuded representation.
3. Restore markers and metadata to canonical positions — short_id in metadata slot where the format provides one; otherwise format-native comment at the **END** of the block.

**After every tree modification without exception (valid tree):**

1. Write the updated tree file to disk inside the session directory.
2. Export the in-session source copy: strip all special marker comments via `unmark`, write clean source into the session directory (session TEMP mirrors project layout, not live files).
3. Record SHA-256 content checksums for **both** the tree file and the exported source copy.
4. Create a git commit in the session repository capturing both artefacts.

**When tree is invalid — DEGRADED path:** source + checksum + git commit only (no full marker cycle). Re-validation via `TreeBuilder.build` when plain-text edit makes source parseable resumes full invariant per `{h009}`.

**One tree modification = one git commit.** No exceptions.

**`{d004}` — WRITE (external copy-out; stage 1 preview)**

In-session artefacts are already finalized per mutation by `{d003}`. The write command gates **external copy-out only** — two API stages:

1. **Stage 1 — preview (`{d004}`):** Computes diffs between in-session artefacts and their external counterparts **without modifying any external file**. In-session side: unmark-exported source copy and in-session tree file inside the session directory. External side: live project source file and co-located sibling tree file. Returns both diffs. **No-op when no diffs** (in-session source matches live source and in-session tree matches external tree); nothing is written externally.

   **Distinct from `{e003}`:** this compares in-session artefacts against **live external files**, not session git history. `{e003}` source mode compares a tree revision against the most recent per-mutation unmark-exported in-session source; the live project file is not an input.

2. **Stage 2 — confirm (`{n7k2}`):** Only upon **explicit confirmation** (second call or `confirm` parameter) atomically copies both artefacts to external co-located positions: in-session unmark-exported source over the live project file, in-session tree onto sibling tree path. **Atomic:** both external writes succeed or neither does. Without explicit confirmation, no external file is modified.

**`{d005}` — CLOSE**

Delete the session directory entirely, including its git repository, **without performing any validation, checksum, or consistency checks**. Only the final co-located tree file survives (if previously written out via WRITE). Session git history is ephemeral.

**`{d006}` — Dulwich dependency**

Declare `dulwich` in the project dependency manifest (`requirements.txt` or `pyproject.toml`).

**HRS/MRS:** C-012 (`{d004}`, `{n7k2}`); C-013; C-014 untouched; G-003 T-001/T-004 TS/AS

### Session Git API {e001}–{e006} (with corrected {e003})

All commands require `session_id`. Commands without an active session return an error.

| Command | Behavior |
|---------|----------|
| `{e001}` | Session-scoped MCP command set; no filesystem access without valid session context. |
| `{e002}` `session_git_log(session_id)` | Commit history: hash, message, timestamp. Use `repo.get_walker()` (dulwich); do **not** use `porcelain.log` (writes stdout, returns None). |
| `{e003}` `session_git_diff(session_id, *, mode, rev_a, rev_b=None)` | Mode `tree`: diff two tree-file versions (two commits) at marker/node level. Mode `source`: diff tree-file version `rev_a` against the in-session source. The in-session source is the copy made at open and **re-exported after every mutation via `unmark`** (per `{d003}`). The live project file on disk is **not** an input. Mode `source` compares `rev_a` against the **most recent per-mutation unmark-exported in-session source**. |
| `{e004}` `session_git_show(session_id, rev)` | Full tree file content at given commit. |
| `{e005}` `session_git_status(session_id)` | Uncommitted changes relative to HEAD. Under `{d003}` invariant this should always be empty; exists as consistency check. |
| `{e006}` `session_git_revert(session_id, rev)` | Roll session tree back to state at `rev` via new revert commit. History preserved; no commit deleted. One mutation = one commit, so revert rolls back individual node edits. |

### Tree-validity edit gate {h008}/{h009}

**`{h008}`:** When session tree is **VALID** → short_id six edit operations + full `{d003}` invariant. When **INVALID** → plain-text edits only + DEGRADED `{d003}` path.

**`{h009}`:** Re-validation via `TreeBuilder.build` when plain-text edit makes source parseable; resume short_id edit mode and full `{d003}`. In DEGRADED mode marked content has no markers; MAP metadata (UUIDs, map, next_free) preserved; re-validation rebuilds markers via NodeIdMap.

**HRS/MRS:** C-012, C-015; G-004/T-001

### Marker contract {b000}/{b005}

**`{b000}` — Universal format handler contract**

Every format has a dedicated handler implementing four operations:

| Operation | Signature | Purpose |
|-----------|-----------|---------|
| `parse_content` | `(file_path, content) → list[TreeNode]` | Build node tree from source |
| `mark` | `(content) → marked_text` | Embed **short_id** markers using format-native syntax |
| `unmark` | `(marked_text) → content` | Strip all markers; reproduce original source bytes exactly |
| `sidecar_path` | `(source_abs) → Path` | Return sibling tree-file path |

Handlers live under `code_analysis/core/tree_handlers/` (or path specified by G-001 atomic steps), registered in `HandlerRegistry` keyed by file extension. No handler may use another format's marker syntax.

**Universal all-nodes rule:** Every addressable node in every format receives a **short_id marker** in the TREE section without exception:

- Where the format provides a metadata field or equivalent structured slot → short_id lives in that metadata.
- Where no such slot exists → marker appears as a format-native comment at the **END** of the block (never mid-lexeme, per `{a004}`).

Canonical UUID4 for each node is written only in the tree-file **MAP** section via NodeIdMap — handlers do not embed UUIDs in markers.

**`{b005}` — Python hybrid marking scheme (short_id tokens)**

| CST node type | Marker placement |
|---------------|------------------|
| Nodes with metadata dict (FunctionDef, ClassDef, decorated statements, etc.) | **short_id** in metadata dict under reserved key |
| Nodes without metadata dict (simple statements, expressions, imports, assignments) | Trailing `# ___id___:<short_id>` on **last physical line** of the logical block |

**Block granularity rules:**

- Minimally addressable block = complete logical statement/expression as parsed by CST, never an individual physical line within it.
- Multiline docstring = one block; marker on line containing closing `"""`, after the quotes.
- Line continuations (`\`) and bracket-continuation expressions = one block; marker on last physical line of continuation.
- Shebang line (`#!/...`) is **not** addressable; carries no marker.

**Unmark:** Remove metadata-dict short_id entries and trailing `# ___id___:` comments without altering any other whitespace. Must reproduce original source **byte-for-byte**.

**Tree file sections:** After `FormatHandler.mark`, persist as CHECKSUMS → MAP (UUID map, next_free, content_checksum) → TREE (marked content with short_id tokens).

**Explicit exclusion:** Do not use legacy `.cst/` JSON sidecar or `# cst-node-ids:` / `# @node-id:` comment blocks for new marking (those are legacy identity comments stripped at preview per `{i008}`).

### Unified build {c005}

Per HRS `{c005}`:

```python
TreeBuilder.build(*, content, source_abs, file_path, content_checksum)
```

**Steps:**

1. Resolve handler: `HandlerRegistry.default_registry().resolve(source_abs)`.
2. Produce marked content: `FormatHandler.mark(content)` (short_id tokens only).
3. Build MAP via NodeIdMap.build; write tree file as CHECKSUMS → MAP → TREE to `FormatHandler.sidecar_path(source_abs)` (sibling of source).
4. Record `content_checksum` in CHECKSUMS/MAP **and** expose it in the returned tree reference.

**Ownership:** `code_analysis/core/tree_lifecycle/` is the single owner of tree validity and tree creation (`{c006}`). No other module writes tree files on the canonical unified path.

**Legacy parity oracle:** `recreate_tree_from_content(*, kind, content, source_path, tree_path, content_checksum)` with `TreeFormatKind` dispatch in existing checksum module remains **untouched**. Parity tests diff unified pipeline output vs legacy oracle on real fixtures. Physical removal deferred to **G-000**.

**Checksum helpers** (`{c004}`): `compute_content_checksum(content: str) → str` (SHA-256 hex); `is_tree_valid(content_checksum, stored_checksum) → bool`. Pure functions, no filesystem side effects.

**Sibling convention** (`{c001}`): Tree file named `<stem>.<ext>.tree` in the same directory as `<stem>.<ext>`.

### Preview behavior {i003}/{i005}(FINAL-1)/{i006}/{i007}/{i008}

Preview must match existing preview code behavior except where HRS explicitly revises thresholds.

**Per-format `full_text_max_lines` (`{i005}` FINAL-1)**

| Format | Extensions | Default threshold |
|--------|------------|-------------------|
| Python | `.py` | 200 source lines |
| JSON | `.json` | 200 source lines |
| YAML | `.yaml`, `.yml` | 200 source lines |
| Markdown | `.md` | 200 source lines |
| Plain text | `.txt`, `.rst` | 200 source lines |

- Threshold **0** disables full inline rendering for that format (drilldown only).
- Thresholds measured in **source lines**, not bytes.
- **JSON:** normalize content to printable (pretty-printed) form **before** line counting and inline rendering.
- Inline rendering used when node line span **strictly less than** format threshold; otherwise collapsed structural drilldown.
- Separate `max_chars` budget may paginate the serialized preview envelope; it does **not** control inline-vs-drilldown.

**`{i003}` — Session-scoped preview**

When `session_id` is supplied, navigation operates on the in-session tree or draft held by the active `EditSession` rather than only last committed on-disk artefacts. Closed or non-existent `session_id` returns an error.

**`{i006}` — Python CST preview blocks**

- Block labels: `FunctionDef`, `ClassDef`, `ImportFrom`, etc.; source line ranges `L<start>-<end>`; attribute summaries.
- **`IndentedBlock` transparent:** not emitted as separate blocks; direct statement children appear in place.
- Compound statements (`If`, `For`, `While`, `Try`, `With`, `Match`, function/class bodies): header line may appear as summary row with ellipsis when nested compounds present.
- Drilldown follows CST parent-child relationships via stable ids in sidecar metadata.
- Optional `tree_id` from prior `cst_load_file` may replace `file_path`.

**`{i007}` — short_id prefix placement**

In annotated and full-text rendering modes, every short_id marker prefix is at the **start** of the physical source line using **minimal integer width** for column alignment:

```
[<short_id>] <original line content>
```

No trailing or inline marker placement. Lines without associated short_id use blank padding of fixed width for column alignment.

**`{i008}` — Strip legacy identity comments before render**

Before preview renders Python source text, remove from logical source used for display:

- Trailing `# cst-node-ids: begin` … `# cst-node-ids: end` block
- Whole-line `# @node-id: <uuid>` comments

Stripping applies to committed on-disk source and in-session draft lines. Preview output never shows these comments; short_ids in preview come from MAP/TREE metadata prefixes, not preserved inline comment markers.

### mtime → checksum guard ({g003}/{g004}, C-020/C-022/C-026)

- **Indexer** (`{g003}`, C-022): skip guard compares source vs tree checksum; content-driven reindex; no mtime-driven reindex.
- **GrepConsumer** (`{g004}`, C-020): Finding carries no file mtime; ranking by relevance + result_id tie-break only.
- **SearchSessionFinding** (C-026): structural search finding record has **no mtime** field.

### Strategy: new alongside old (parity-oracle constraint)

| Rule | Detail |
|------|--------|
| Build location | New `code_analysis/tree/` pipeline alongside existing `code_analysis/core/cst_tree` and `recreate_tree_from_content` |
| Legacy touch policy | Do **not** modify legacy oracle code paths during G-001..G-005 |
| Parity tests | **Mandatory** in G-002/T-004 AS — diff new pipeline vs legacy on real fixtures |
| Legacy removal | Deferred exclusively to **G-000** (`.cst/`, `.trees/`, `.tree_sidecar`, pending-sidecar mechanism) |
| Backup before edit | Place existing file in `old_code` via `BackupManager` before any write (project rule CR versioning) |

---

## Global step scope (implementation reference)

Execute in canonical order: **G-001 → G-002 → G-003 → G-004 → G-005 → G-006 → G-000**.

**AS execution waves (where defined):** G-001 `parallel-waves.yaml` (GS-level); G-002 T-003 and T-004 each have `parallel-waves.yaml`; G-003 GS-level waves 1–5 (wave_5 gates T-004/A-001 after T-001/A-003). All other GS: ascending AS `priority` within each target file; respect `depends_on` within TS; TS order within GS README.

### G-001 — Marker contract and format handlers

**Path:** `docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/`  
**AS:** 13 (3 TS)  
**Scope:** `MarkerContract` / `FormatHandler` four-operation interface; `TreeNode`, short_id markers, `HandlerRegistry.default_registry()`; five format handlers; universal all-nodes short_id rule; Python hybrid `{b005}` via A-007; NodeIdMap.resolve integration references.

### G-002 — Tree storage and lifecycle

**Path:** `docs/plans/marked_tree_unification/G-002-tree-storage-and-lifecycle/`  
**AS:** 7 (4 TS)  
**Scope:** Sibling storage convention; `ChecksumSyncPolicy`; `TreeBuilder.build` canonical path; `TreeLifecycle` single owner; T-004 unified pipeline integration + parity tests.

### G-003 — Edit session and session Git API

**Path:** `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/`  
**AS:** 14 (4 TS)  
**Scope:** Session **directory** model; open protocol + FINAL-2; hide/unhide mutation cycle; valid/invalid dual-mode per-mutation; per-mutation git commit; **two-stage WRITE** — stage 1 preview (`{d004}`) diffs in-session vs external without external writes; stage 2 confirm (`{n7k2}`) atomic copy-out on explicit confirmation; `session_write` MCP (T-004); CLOSE blind delete; five `session_git_*` MCP commands.

**Execution waves:** `G-003/parallel-waves.yaml` — waves 1–5; wave_5 runs T-004/A-001 after T-001/A-003 registry.

### G-004 — Edit operations, preview, and tree query

**Path:** `docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/`  
**AS:** 11 (3 TS)  
**Scope:** Six uniform edit operations by **(file, short_id)** (with tree-validity gate `{h008}`/`{h009}`); preview navigation; per-format thresholds FINAL-1; session draft preview; tree query (XPath-compatible structural search).

### G-005 — Consumer integration

**Path:** `docs/plans/marked_tree_unification/G-005-consumer-integration/`  
**AS:** 14 (3 TS)  
**Scope:** GrepConsumer tree-validity via `TreeLifecycle`; watcher TreeLifecycle wrapper + DB checksum; indexer mtime→checksum guard; SearchSessionFinding without mtime (C-026).

### G-006 — NodeIdMap module

**Path:** `docs/plans/marked_tree_unification/G-006-node-id-map/`  
**AS:** 1 (1 TS)  
**Scope:** NodeIdMap (C-025) — `build`, `validate_and_repair`, `resolve`; MAP section read/write; short_id↔UUID both directions; absorbs per-format id wiring formerly scoped to removed G-007.

### G-000 — Sidecar layout migration (cutover)

**Path:** `docs/plans/marked_tree_unification/G-000-sidecar-layout-migration/`  
**AS:** 25 (3 TS)  
**Depends on:** G-001..G-006 verified end-to-end  
**Scope:** Hard cutover. Redirect remaining call sites from legacy layouts (`.cst/` subdirectory, `.trees/` mirror, `.tree_sidecar` adjacent file) to sibling convention via `sibling_tree_path`. Remove legacy resolvers and pending-sidecar mechanism. Migrate consumers to 3-section tree files and (file, short_id) API.

---

## Milestones

| Milestone | Status | Notes |
|-----------|--------|-------|
| HRS approved | **complete** | User-owned; node-id cascade applied |
| Phase A — HRS/MRS node-id cascade | **complete** | green |
| Phase B — GS I1 + cycle_2 | **complete** | green; 7 GS |
| Phase C — Tactical (21 TS) | **complete** | green |
| Phase D — Atomic a1–a10 | **complete** | green — F-001–F-004 resolved |
| Phase E — Cascade phases | **complete** | green |
| Phase F — Final sweep | **complete** | green — close-out 2026-05-30 |
| G-003 two-stage WRITE ({d004}/{n7k2}, T-004) | **complete** | Plan AS; prior cascade |
| Plan dovodka (atomic layer) | **green** | Phase F close-out; ready for code execution |
| **Code execution** | **ready** | Execute AS in dependency order |

---

## Coder constraints (from AS prompts — execute, do not re-plan)

| Constraint | Requirement |
|------------|-------------|
| Virtual environment | Activate `.venv` before Python commands |
| Backup before write | `BackupManager` → `old_code` before modifying existing files |
| test_data access | Code under `test_data/` — read and write **only** via code-analysis-server MCP commands |
| Legacy removal | Do **not** remove legacy paths until G-000 |
| Parity tests | G-002/T-004 AS requires parity vs legacy oracle on fixtures |
| Static analysis | black / flake8 / mypy on touched paths (CR-007) |
| Indexing | Run indexing if `USE_CODE_MAP=yes` after code changes (CR-006) |
| New alongside old | Build new pipeline alongside legacy; legacy untouched until G-000 |

---

## Phase F blocking findings (resolved — close-out 2026-05-30)

Phase F close-out verdict: **GREEN**. All findings below resolved; atomic layer ready for code execution.

| ID | Check | Location | Summary | Status |
|----|-------|----------|---------|--------|
| **F-001** | atomic a5 | `G-001/.../A-001-format-handler-base.yaml:110` | Cross-AS path reference to G-006 A-001; lines 108–109 cite G-006 NodeIdMap.resolve | **RESOLVED** — inlined NodeIdMap.resolve contract; removed cross-AS G-006 path ref |
| **F-002** | directory slug | `G-006-node-id-map/` (was `G-006-universal-node-id/`) | Retired `universal-node-id` terminology in directory slug | **RESOLVED** — renamed directory; updated all path refs; removed stale duplicate tree |
| **F-003** | TS README status | `G-006-node-id-map/T-001-node-id-map-module/README.yaml:75` | status `needs_review` | **RESOLVED** — G-006 T-001 README status → `ready_for_review` |
| **F-004** | atomic a5 boilerplate | 10 G-004 AS prompts | Literal `cross_ts_depends_on` in prohibition blockquote (not YAML fields) | **RESOLVED** — rephrased G-004 AS prohibition blockquotes; zero literal in prompts |

**GREEN areas (unchanged):** cycle_1, I1, cycle_2, tactical (21 TS READMEs), G-007 directory absent on disk.

**Authoritative audit:** `docs/ai_reports/marked_tree_unification_dovodka_audit.yaml` → `node_id_cascade_phase_f`.

---

## Known a3/a8 waivers (NOT blockers)

These items are documented and accepted; they do not block code execution.

### (a) a3/a8 waivers on pre-existing oversized files

| AS | Target file | Pattern |
|----|-------------|---------|
| G-000/T-003/A-002 | `code_analysis/commands/universal_file_edit/write_command.py` | Sectioned embed — `_second_call` sidecar block only |
| G-000/T-003/A-006 | `code_analysis/core/cst_tree/tree_saver.py` | Region-only embed with anchor markers |
| G-005/T-002/A-001 | `code_analysis/core/file_watcher_pkg/processor_queue.py` | Method-only integration seam |
| G-005/T-002/A-002 | `code_analysis/core/database/schema_definition_tables_core.py` | Region-only files-table embed |

Each waiver AS includes explicit immutable-region contract and documents waiver in `verification.expected`. Additional region-only a3 waivers may appear in other AS (e.g. oversized command modules) per each AS `verification.expected`.

### (b) AS prompt constraints carried for future coders

- **parity-oracle:** new-alongside-old strategy; legacy untouched until G-000
- **backup-before-write:** `BackupManager` → `old_code` mandatory
- **test_data-via-MCP:** no direct file tools on `test_data/` code
- **no-legacy-removal-before-G-000:** cutover deferred to G-000 AS set
- **external-api-short-id:** address nodes as (file path, short_id) only; UUID MAP-internal

### (c) Optional status-field housekeeping

GS/TS README `status` fields on disk may lag Phase F verdict (e.g. G-001, G-002 still `needs_review`). Promotion to `frozen` is plan-maintainer housekeeping.

---

## How to execute

1. **Read** parent GS README and parent TS README for context (orchestrator responsibility).
2. **Execute AS** in ascending `priority` within each target file; respect `depends_on` within the same TS.
3. **Follow GS order:** G-001 → G-002 → G-003 → G-004 → G-005 → G-006 → G-000.
4. **Verify** each AS per its `verification` field (pytest, import, static_analysis, or manual).
5. **Report** completion in orchestrator workflow; do not modify plan artifacts unless cascade is authorized.

**Authoritative audit:** `docs/ai_reports/marked_tree_unification_dovodka_audit.yaml` → `node_id_cascade_phase_f`

---

*End of coding handoff document.*
