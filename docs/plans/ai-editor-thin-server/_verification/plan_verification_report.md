# Plan Verification Report: `ai-editor-thin-server`

**Plan path:** `docs/plans/ai-editor-thin-server/`  
**Verification date:** 2026-06-09  
**Standards applied:**

1. `docs/standards/planning/plan_standard_machine.yaml`
2. `docs/standards/planning/hrs_mrs_gs_consistency_verification_standard.yaml`
3. `docs/standards/planning/tactical_step_creation_standard.yaml`
4. `docs/standards/planning/atomic_step_creation_standard.yaml`

**Method:** Zero-trust re-read of plan artifacts by three delegated `researcher_doc` passes (levels 1–3, level 4, level 5). No fixes applied.

**Binding-reference note:** This plan uses `source_ranges` (line numbers) in `spec.yaml` and global steps rather than paragraph-label `source_labels`. Cycle_1/I1 checks were applied against line ranges and `{xxxx}` paragraph labels in `source_spec.md`.

---

## Summary Verdicts by Level

| Level | Artifacts | Verdict |
|-------|-----------|---------|
| **1** | `source_spec.md` | **has-findings** (structural GREEN; strict I1.c binding-line coverage fails) |
| **2** | `spec.yaml` | **has-findings** (cycle_1 c1 failures on source_ranges) |
| **3** | `G-001` … `G-010` `README.yaml` | **has-findings** (conceptual-test leaks, cycle_2 c6/c7/c8 failures, count at indicator threshold) |
| **4** | 47 `T-NNN-*/README.yaml` | **has-findings** (t12 gaps in G-010, t13 overlaps in G-001/G-003/G-004/G-007, t10 open decisions) |
| **5** | 106 `atomic_steps/*.yaml` | **has-findings** (a8 corrupted embedded files, a5 cross-AS refs, a10 G-003/T-003 gap, outer_a8 drift) |

**Overall:** **has-findings** — plan is **not ready to freeze or descend** to implementation until blockers are resolved.

---

## Findings Count by Severity

| Severity | Count |
|----------|------:|
| **blocker** | 16 |
| **major** | 37 |
| **minor** | 12 |
| **Total** | **65** |

---

## Independent Fix Groups (for parallel delegation)

| Fix group | Finding IDs | Scope |
|-----------|-------------|-------|
| `source_spec.md` | F-001 | Top-level HRS structural binding lines |
| `spec.yaml` | F-002–F-008 | MRS source_ranges and concept quality |
| `G-001` | F-010, F-026, F-035, F-036, F-045 | GS conceptual test + TS t13/t10/t5 |
| `G-002` | F-011, F-031–F-034, F-041, F-042, F-055, F-060 | GS conceptual test + TS t10/t5 + AS outer_a8 |
| `G-003` | ~~F-012, F-013, F-014, F-027, F-039, F-048, F-051, F-053, F-058~~ **RESOLVED** | GS autonomy/source_ranges + TS t13/t5 + AS a8/a10 — **GREEN** |
| `G-004` | F-015, F-028, F-043, F-054, F-061, F-062 | GS conceptual test + TS t13 + AS a8/outer_a8 |
| `G-005` | F-016, F-017, F-030, F-056, F-059, F-063 | GS autonomy + TS t10 + AS a5/a4 |
| `G-006` | F-018, F-019, F-064 | GS source_ranges + conceptual test + AS a9 |
| `G-007` | F-020, F-029, F-037, F-040, F-044, F-049, F-050, F-052, F-057 | GS source_ranges + TS t13/t10/T-000 + AS a8/a5 |
| `G-008` | ~~F-021, F-046, F-047~~ **RESOLVED** | GS conceptual test + TS t5 — **GREEN** |
| `G-009` | F-022, F-038 | GS conceptual test + TS t10 |
| `G-010` | F-023, F-024, F-025 | GS conceptual test + TS t12 gaps |
| Plan-wide structure | F-009 | Global step count (10 at indicator threshold) |
| Plan-wide layout | F-065 | Atomic step artifact path convention |

---

## Findings

### Level 1 — `source_spec.md`

**F-001** | minor | I1.c / cycle_1 c2  
**File:** `docs/plans/ai-editor-thin-server/source_spec.md`  
**Location:** Lines 1–4, 6, 8, 10–12, 14, 16, 18–20, 22, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58–60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88–90, 92 (structural headings and blanks)  
**Description:** Binding lines (section headings `## …`, blanks) fall outside the union of `source_ranges` in `spec.yaml` and all global steps. All labeled tezises `{xxxx}` on semantic lines are covered, but strict I1.c over all binding lines fails for structural lines.  
**Recommended fix:** Either mark structural headings/blanks `<!-- non-binding -->`, or extend MRS/GS `source_ranges` to include them.  
**Fix-group:** `source_spec.md`

---

### Level 2 — `spec.yaml`

**F-002** | blocker | cycle_1 c1  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-015].source_ranges` → `{start: 47, end: 49}`  
**Description:** C-015 (Broken Session Policy) claims rules from `{6z8a}` (line 55: reject all except write/close) and `{4c2d}` (line 57: zombie cleanup), but `source_ranges` point to lines 47–49 — Close stage header `{5v0w}`, a blank, and section heading `## Валидация сессии…`. Cited lines do not justify the concept definition or properties.  
**Recommended fix:** Rebind `C-015.source_ranges` to lines 55–57 (and split zombie cleanup to `C-025` if needed).  
**Fix-group:** `spec.yaml`

**F-003** | blocker | cycle_1 c1  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-016].source_ranges` → `{start: 53, end: 55}`  
**Description:** C-016 (MCP Workflow Surface) maps to lines 53–55, but line 53 is `{d5g3}` (Session Guard), line 55 is `{6z8a}` (Broken Session Policy). Actual MCP surface text is `{8g7f}` on line 61.  
**Recommended fix:** Change `C-016.source_ranges` to `{start: 61, end: 61}` (or 61–63 if including upstream non-registration). Reassign 53/55 to `C-024`/`C-015`.  
**Fix-group:** `spec.yaml`

**F-004** | major | cycle_1 c1  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-014].source_ranges` → `{start: 45, end: 45}`  
**Description:** Line 45 is `{e6h4}` (`write_mode=preview` / lockfile semantics), not Session Validation. Properties require touch via `session_list_file_locks` (lines 51, 13).  
**Recommended fix:** Remove line 45 from `C-014`; keep 51 (and 13 if needed). Bind 45 to `C-012`.  
**Fix-group:** `spec.yaml`

**F-005** | major | cycle_1 c1  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-024].source_ranges` → `{start: 45, end: 49}`  
**Description:** Range includes Close stage `{5v0w}` (line 47) and section header (line 49), not Session Guard. Guard text is `{d5g3}` line 53 and `{1x5y}` line 51.  
**Recommended fix:** Replace 45–49 with `{start: 51, end: 53}`; move close-stage lines to `C-013`.  
**Fix-group:** `spec.yaml`

**F-006** | major | cycle_1 c1  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-004].source_ranges` → `{start: 45, end: 45}`  
**Description:** Line 45 (`write_mode` / lockfile) does not justify CA Session multi-file lock semantics (lines 29–31).  
**Recommended fix:** Remove line 45 from `C-004`; use 21, 29–31 only.  
**Fix-group:** `spec.yaml`

**F-007** | minor | plan_standard_machine machine_spec.concept_definition  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-019].properties[2]` — text `({f7i5})`  
**Description:** Property cites a paragraph label while MRS/GS bind via `source_ranges`. Terminology inconsistency.  
**Recommended fix:** Replace `{f7i5}` with `source_ranges: {start: 29, end: 29}` reference in prose, or cite line 29 explicitly.  
**Fix-group:** `spec.yaml`

**F-008** | minor | cycle_1 c4  
**File:** `docs/plans/ai-editor-thin-server/spec.yaml`  
**Location:** `concepts[C-022]` (Product Acceptance Criteria)  
**Description:** Borderline entity — verification checklist rather than runtime behavior. Acceptable if treated as invariant-owning concept; weak vs "entity with behavior."  
**Recommended fix:** Keep as concept with explicit "verification-only" invariant, or fold properties into `C-009` and drop `C-022`.  
**Fix-group:** `spec.yaml`

---

### Level 3 — Global Steps

**F-009** | major | plan_standard_machine count_guidance  
**File:** `docs/plans/ai-editor-thin-server/` (all `G-*/README.yaml`)  
**Location:** Global step set size = 10  
**Description:** Ten steps equals `indicator_threshold: 10` and exceeds `typical_range: [3, 7]`. Signals possible over-decomposition or plan size.  
**Recommended fix:** Review merge candidates (e.g. G-006+G-009 cleanup, G-008 client into G-006) or split into sub-plans.  
**Fix-group:** plan-wide structure

**F-010** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/README.yaml`  
**Location:** `description` — "storage paths", "format groups", "конфигурация контейнера/Debian"  
**Description:** Leaked implementation/tactics beyond domain objects and operations.  
**Recommended fix:** Rewrite using `C-018`, `C-005`–`C-008` only; move path resolver detail to `executor_brief` or tactical layer.  
**Fix-group:** G-001

**F-011** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/README.yaml`  
**Location:** `description` — `session_list_file_locks`, `session_open_file`, `session_close_file`, "chunked transfer", "in-memory client_sessions"  
**Description:** Names concrete CA commands and implementation artifacts, violating conceptual test.  
**Recommended fix:** Describe via `C-017`, `C-023`, `C-014`; reserve command names for tactical/atomic layers.  
**Fix-group:** G-002

**F-012** | blocker | cycle_2 c7, cycle_2 c8  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/README.yaml`  
**Location:** `description`; `depends_on: [G-007]`; `concepts` includes `C-024`  
**Description:** Open orchestration lists `C-024` but `description` omits Session Guard behavior (touch, reject on NOT_FOUND). `depends_on: G-007` supplies that only from a sibling — silent sibling dependency.  
**Recommended fix:** Add executor-facing Guard semantics to `description` or `executor_brief`; document open rejection rules locally.  
**Fix-group:** G-003

**F-013** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/README.yaml`  
**Location:** `description` — "editor UUID"  
**Description:** Implementation detail (legacy group UUID removal) at global level.  
**Recommended fix:** State via `C-004` property ("no separate editor group UUID").  
**Fix-group:** G-003

**F-014** | major | cycle_2 c6  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/README.yaml`  
**Location:** `source_ranges` — only `{start: 35, end: 35}` for Open; missing 37, 39  
**Description:** C-010 (Open Stage) includes `{7m3q}` (line 37) and `{c4f2}` create=true (line 39), but GS ranges cover only line 35 intro. Off-target/incomplete mapping for this step's scope.  
**Recommended fix:** Extend `source_ranges` to `{start: 35, end: 40}` and `{start: 47, end: 47}` for close.  
**Fix-group:** G-003

**F-015** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-004-edit-engine-adaptation/README.yaml`  
**Location:** `description` — "format groups", "CST", "tree-temp", "text buffer", `draft_path`, `lockfile`, `sidecar`  
**Description:** Leaked module/artifact names.  
**Recommended fix:** Describe via `C-011`, `C-008`, `C-019` only.  
**Fix-group:** G-004

**F-016** | blocker | cycle_2 c7  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/README.yaml`  
**Location:** `description` (no `write_mode`); `concepts` includes `C-012`  
**Description:** `{e6h4}` (lines 43–45) defines `write_mode=preview` vs `commit`. C-012 properties include this; GS `description` omits preview branch — executor incompleteness for Write Stage.  
**Recommended fix:** Add `write_mode=preview` (local diff, no upload) vs commit compare-and-upload to `description` or `executor_brief`.  
**Fix-group:** G-005

**F-017** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/README.yaml`  
**Location:** `description` — "format-group export/commit", "lockfile"  
**Description:** Implementation tactics at global level.  
**Recommended fix:** Use `C-012` export/compare semantics without naming internal format groups.  
**Fix-group:** G-005

**F-018** | blocker | cycle_2 c6  
**File:** `docs/plans/ai-editor-thin-server/G-006-mcp-surface-cleanup/README.yaml`  
**Location:** `source_ranges` → `{start: 53, end: 55}`  
**Description:** Lines 53–55 are Session Guard (`{d5g3}`) and Broken Session (`{6z8a}`), not MCP Workflow Surface (`{8g7f}` line 61). Off-target ranges for this step.  
**Recommended fix:** Change to `{start: 61, end: 63}`; move 53–55 to G-007.  
**Fix-group:** G-006

**F-019** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-006-mcp-surface-cleanup/README.yaml`  
**Location:** `description` — `session_*`, `subordinate_session_*`, `project_file_transfer_*`, `advisory lock`, `move_nodes`, `session_git_*`, `undo/redo`, `session_write`  
**Description:** Enumerates concrete command families — leaked tactics.  
**Recommended fix:** Summarize as "duplicate MCP families under `C-020` removed from `C-016` surface."  
**Fix-group:** G-006

**F-020** | blocker | cycle_2 c6, cycle_2 c7  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/README.yaml`  
**Location:** `source_ranges` → `{start: 45, end: 49}`, `{start: 51, end: 51}`; missing line 55  
**Description:** Core `{6z8a}` policy (line 55) absent from `source_ranges`. Range 45–49 maps to Close stage + section header, not broken-session rules. Triple autonomy for `C-015` is incomplete at GS level.  
**Recommended fix:** Replace ranges with `{start: 55, end: 57}`; drop misaligned 45–49.  
**Fix-group:** G-007

**F-021** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-008-client-single-facade/README.yaml`  
**Location:** `description` — `UniversalFileClient`, `FileSessionClient`, `EditorFileClient`, `LocalEditWorkspace`, `CLIENT_FACADE_COMMANDS`, `ai-editor-client`  
**Description:** Class/module/API names at global level.  
**Recommended fix:** Express via `C-003`, `C-009`, `C-016`, `C-020` ("single client facade").  
**Fix-group:** G-008

**F-022** | major | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-009-legacy-removal/README.yaml`  
**Location:** `description` — `commands/sessions`, `FAISS`, `CLI/main`, `worker shutdown`  
**Description:** Concrete paths and subsystems at global level.  
**Recommended fix:** Scope via `C-020`, `C-021` only.  
**Fix-group:** G-009

**F-023** | minor | plan_standard_machine conceptual_test  
**File:** `docs/plans/ai-editor-thin-server/G-010-acceptance-tests/README.yaml`  
**Location:** `description` — "mock Upstream Client", "universal_file тестов"  
**Description:** Test implementation detail at global level (borderline for acceptance step).  
**Recommended fix:** Frame as verification of `C-022` criteria; defer mock/test mechanics to tactical layer.  
**Fix-group:** G-010

---

### Level 4 — Tactical Steps

**F-024** | blocker | t12  
**File:** `docs/plans/ai-editor-thin-server/G-010-acceptance-tests/README.yaml` + TS set  
**Location:** GS `description` (C-022 help criterion); no TS `concepts` includes C-016 for help acceptance  
**Description:** GS requires verifying "help без дублирующих семейств" (C-022 property). TS set (T-001–T-004) has no tactical step whose scope is help/MCP surface verification. G-006 T-004 covers this for G-006, not G-010.  
**Recommended fix:** Add G-010 TS (or extend T-001/T-003) explicitly covering C-016/C-022 help acceptance.  
**Fix-group:** G-010

**F-025** | blocker | t12  
**File:** `docs/plans/ai-editor-thin-server/G-010-acceptance-tests/README.yaml`  
**Location:** GS `concepts`: C-008, C-011; union of T-001–T-004 `concepts`  
**Description:** GS lists C-008 (Edit Subdirectory) and C-011 (Edit Stage). No G-010 TS lists C-008 or C-011 in `concepts`, despite GS implying acceptance of "open создаёт edit subdir" and edit-stage behavior.  
**Recommended fix:** Add C-008/C-011 to relevant G-010 TS `concepts` and description, or add dedicated acceptance TS.  
**Fix-group:** G-010

**F-026** | major | t13  
**File:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/T-003-edit-session-root-base/README.yaml`, `T-004-format-group-path-adaptation/README.yaml`, `T-006-sidecar-tree-temp-workspace-paths/README.yaml`  
**Location:** `description` — all three modify Internal Edit Engine (C-019) path layout  
**Description:** T-003 changes session_root/file_subtree binding; T-004 changes FormatGroup/DraftFile paths; T-006 changes sidecar/tree-temp paths. All modify the same entity (C-019).  
**Recommended fix:** Merge into one TS or split C-019 sub-entities so each TS touches a distinct target.  
**Fix-group:** G-001

**F-027** | major | t13  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-002-open-orchestration/README.yaml`, `T-003-multi-file-same-session/README.yaml`  
**Location:** `description` — open orchestration vs multi-file open extension  
**Description:** T-002 implements `universal_file_open`; T-003 adds multi-file open behavior. Both perform open-stage work on the same command/flow target.  
**Recommended fix:** Fold multi-file rules into T-002 or split open orchestration so scopes do not overlap.  
**Fix-group:** G-003

**F-028** | major | t13  
**File:** `docs/plans/ai-editor-thin-server/G-004-edit-engine-adaptation/T-002-preview-opened-file/README.yaml`, `T-003-preview-one-shot-ca-read/README.yaml`  
**Location:** `description` — both adapt `universal_file_preview`  
**Description:** T-002 adapts preview for opened Edit Subdirectory; T-003 adds one-shot CA read mode. Both modify the same command entity.  
**Recommended fix:** Single TS for preview modes with non-overlapping sub-actions, or split preview into distinct domain entities.  
**Fix-group:** G-004

**F-029** | major | t13  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-000-oversized-command-split/README.yaml`, `T-002-reject-open-edit-preview/README.yaml`  
**Location:** T-000 `description` (open, write, preview modules); T-002 `description` (integrate Session Guard into open/edit/preview)  
**Description:** T-000 refactors open/preview command modules; T-002 integrates Session Guard into the same commands. Both modify the same command targets.  
**Recommended fix:** Remove T-000 from tactical layer (move to atomic/implementation constraint) or merge with T-002.  
**Fix-group:** G-007

**F-030** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/T-001-origin-edit-comparison/README.yaml`  
**Location:** `description` line 4: "байтовое **или** эквивалентное сравнение"  
**Description:** Unresolved comparison strategy fork.  
**Recommended fix:** Bind to one rule in TS (byte compare vs format-specific export) per C-012/MRS.  
**Fix-group:** G-005

**F-031** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-001-upstream-config-contract/README.yaml`  
**Location:** `description` line 4: "секция code_analysis_server **или** upstream"  
**Description:** Unresolved config key name.  
**Recommended fix:** Pick one canonical section name in TS.  
**Fix-group:** G-002

**F-032** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-002-session-validation-wrapper/README.yaml`  
**Location:** `outputs[0].description` line 19: "valid, not_found, invalid **или** эквивалент контракта СА"  
**Description:** Validation result enum left open.  
**Recommended fix:** Fix exact enum values matching C-023/C-014.  
**Fix-group:** G-002

**F-033** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-003-open-file-download-wrapper/README.yaml`  
**Location:** `description` line 4: "session_open_file **(или эквивалент)**"  
**Description:** Unresolved CA lock API name.  
**Recommended fix:** Bind to `session_open_file` per C-023 or name the exact equivalent.  
**Fix-group:** G-002

**F-034** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-004-close-file-unlock-wrapper/README.yaml`  
**Location:** `description` line 4: "session_close_file **(или эквивалент)**"  
**Description:** Unresolved CA unlock API name.  
**Recommended fix:** Bind to `session_close_file` per C-023.  
**Fix-group:** G-002

**F-035** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/T-001-workspace-config-schema/README.yaml`  
**Location:** `description` line 4: "workspace_root **(или алиас** editor_workspace_dir)"  
**Description:** Unresolved config field name.  
**Recommended fix:** Pick one key or define deterministic alias precedence.  
**Fix-group:** G-001

**F-036** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/T-004-format-group-path-adaptation/README.yaml`  
**Location:** `description` line 4: "относительно Edit Subdirectory (C-008) **или** File Subtree (C-006)"  
**Description:** Unresolved path anchor for draft/lockfile/sidecar.  
**Recommended fix:** Resolve anchor per format group in TS.  
**Fix-group:** G-001

**F-037** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-003-permit-terminating-write-close/README.yaml`  
**Location:** `description` line 4: "write (попытка save **если СА допускает**)"  
**Description:** Conditional terminating-write behavior not bound to a concrete predicate.  
**Recommended fix:** State exact behavior per C-024/C-015 (upload attempt + CA error + draft retained).  
**Fix-group:** G-007

**F-038** | major | t10  
**File:** `docs/plans/ai-editor-thin-server/G-009-legacy-removal/T-004-remove-transfer-mcp-modules/README.yaml`  
**Location:** `description` line 4: "**если** логика полностью перенесена"  
**Description:** Conditional deletion gate not bound to a verifiable predicate.  
**Recommended fix:** Replace with concrete precondition (e.g. G-002 T-005 + G-006 T-002 complete).  
**Fix-group:** G-009

**F-039** | major | t5  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-002-open-orchestration/README.yaml`  
**Location:** `description` references C-006, C-018, C-019; `concepts` omits them  
**Description:** Concept_ids used in description but absent from `concepts` list.  
**Recommended fix:** Add C-006, C-018, C-019 to `concepts`.  
**Fix-group:** G-003

**F-040** | major | t5/t7  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-002-reject-open-edit-preview/README.yaml`  
**Location:** `description` line 4: "Session Guard"; `concepts` lacks C-024  
**Description:** Core entity C-024 referenced in prose but not in `concepts`.  
**Recommended fix:** Add C-024 (and C-014 if integration uses validation) to `concepts`.  
**Fix-group:** G-007

**F-041** | major | t5  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-005-upload-transfer-wrapper/README.yaml`  
**Location:** `description` references C-012; `concepts`: only C-017, C-023  
**Description:** Write Stage (C-012) referenced but not listed.  
**Recommended fix:** Add C-012 to `concepts`.  
**Fix-group:** G-002

**F-042** | major | t5  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-006-download-without-lock/README.yaml`  
**Location:** `description` references C-011; `concepts`: only C-017, C-023  
**Description:** Edit Stage preview concept C-011 referenced but not listed.  
**Recommended fix:** Add C-011 to `concepts`.  
**Fix-group:** G-002

**F-043** | major | forbidden_in_ts  
**File:** Multiple TS (representative: `G-004-edit-engine-adaptation/T-001-edit-paths-in-workspace/README.yaml`)  
**Location:** `description` line 4: "EditCommand", "facade abs_path", "draft_path"  
**Description:** Class/module/function implementation details leak into tactical layer. Same pattern in G-006 (`hooks_register_part1/part2`), G-009 (module paths), G-005 T-003 (`confirm_external_copy_out`).  
**Recommended fix:** Replace with domain entities (Edit Stage command contract, MCP registration surface, etc.).  
**Fix-group:** G-004 (pattern spans G-005, G-006, G-009)

**F-044** | major | plan_standard_machine L4  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-000-oversized-command-split/README.yaml`  
**Location:** `description` lines 4–10; `atomic_steps` lines 27–38  
**Description:** T-000 is atomic-layer concern (400-line file limit, `modify_file AS`, facade/runtime split) placed at tactical level with 11 atomic steps pre-populated. Violates TS conceptual boundary.  
**Recommended fix:** Remove T-000 from tactical layer or reframe as a single infrastructure TS without AS-level detail.  
**Fix-group:** G-007

**F-045** | minor | t5  
**File:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/T-003-edit-session-root-base/README.yaml`  
**Location:** `description` line 4: C-018; `inputs[0].description` line 14: C-005, C-006; `concepts` omits C-018, C-005, C-006  
**Description:** Referenced concept_ids missing from `concepts` list.  
**Recommended fix:** Add missing concept_ids to `concepts`.  
**Fix-group:** G-001

**F-046** | minor | t5  
**File:** `docs/plans/ai-editor-thin-server/G-008-client-single-facade/T-002-deprecate-parallel-facades/README.yaml`  
**Location:** `description` references C-016; `concepts`: only C-020  
**Description:** C-016 referenced but not listed.  
**Recommended fix:** Add C-016 to `concepts`.  
**Fix-group:** G-008

**F-047** | minor | t5  
**File:** `docs/plans/ai-editor-thin-server/G-008-client-single-facade/T-003-update-server-api-examples/README.yaml`  
**Location:** `description` references C-009; `concepts` omits C-009  
**Description:** C-009 referenced but not listed.  
**Recommended fix:** Add C-009 to `concepts`.  
**Fix-group:** G-008

**F-048** | minor | t5  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-004-close-orchestration/README.yaml`  
**Location:** `description` references C-016; `concepts` omits C-016  
**Description:** C-016 referenced but not listed.  
**Recommended fix:** Add C-016 to `concepts`.  
**Fix-group:** G-003

**F-049** | minor | status  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-000-oversized-command-split/README.yaml`  
**Location:** `status` field line 39: `draft`  
**Description:** Only TS still `draft`; siblings are `ready_for_review`.  
**Recommended fix:** Complete T-000 or remove it; set `ready_for_review` when stable.  
**Fix-group:** G-007

**F-050** | minor | t7  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-003-permit-terminating-write-close/README.yaml`  
**Location:** `concepts`: C-012, C-013, C-015; omits C-024, C-017  
**Description:** Terminating write/close per C-024 uses Upstream Client (C-017); neither listed.  
**Recommended fix:** Add C-024 and C-017 to `concepts`; clarify upstream touch behavior in `description`.  
**Fix-group:** G-007

---

### Level 5 — Atomic Steps

**F-051** | blocker | a8  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-002-open-orchestration/atomic_steps/A-002-open-orchestration-upstream.yaml`  
**Location:** `field:prompt` (CURRENT FILE CONTENT fence)  
**Description:** Embedded `open_command_runtime.py` is corrupted/truncated (`"""Workspace open orchestration — implemented in     raise NotImplementedError(`). Not valid post-prior-AS file state.  
**Recommended fix:** Replace embedded block with complete, syntactically valid file content after A-001 and G-007/T-000 runtime split.  
**Fix-group:** G-003/T-002

**F-052** | blocker | a8  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-001-open-command-runtime.yaml`  
**Location:** `field:prompt` (create_file template)  
**Description:** Same corrupted NotImplementedError stub in the `create_file` template for `open_command_runtime.py`.  
**Recommended fix:** Fix starter template to valid Python before downstream modify AS depend on it.  
**Fix-group:** G-007/T-000

**F-053** | blocker | a8  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-004-close-orchestration/atomic_steps/A-001-close-orchestration-unlock.yaml`  
**Location:** `field:prompt` (embedded `close_command.py`)  
**Description:** CURRENT FILE contains invalid syntax `async # close-guard-integrated` before `def execute`. Embedded state is not compilable Python.  
**Recommended fix:** Embed full, valid `close_command.py` reflecting post-G-007/T-003 guard integration baseline.  
**Fix-group:** G-003/T-004

**F-054** | blocker | a8  
**File:** `docs/plans/ai-editor-thin-server/G-004-edit-engine-adaptation/T-001-edit-paths-in-workspace/atomic_steps/A-001-edit-command-workspace-paths.yaml`  
**Location:** `field:prompt` (embedded `edit_command.py`)  
**Description:** Invalid embedded syntax `async # edit-guard-integrated` before `def execute`.  
**Recommended fix:** Replace with complete valid file after G-007/T-002 guard integration.  
**Fix-group:** G-004/T-001

**F-055** | blocker | outer_a8  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-003-open-file-download-wrapper/atomic_steps/A-001-lock-file-and-download.yaml`  
**Location:** `field:prompt` (embedded `code_analysis_client.py`)  
**Description:** Embedded file shows `validate_ca_session` as docstring-only stub, but G-002/T-002 A-001 should have added the full implementation. Later G-002 TS on the same file assume cumulative state.  
**Recommended fix:** Refresh CURRENT FILE to include complete `validate_ca_session` body from T-002 AS output; repeat for T-004…T-007 chain.  
**Fix-group:** G-002/T-003

**F-056** | blocker | a5  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/T-003-upload-and-origin-sync/atomic_steps/A-001-write-upload-sync-origin.yaml`  
**Location:** `field:prompt` (task section)  
**Description:** Prompt says "Add upload branch after the no-op branch from the **prior step on this file**" — cross-AS execution-order prose (forbidden).  
**Recommended fix:** Remove prose reference; rely on `priority: 2` within TS and show full post-T-002 file content inline.  
**Fix-group:** G-005/T-003

**F-057** | blocker | a5  
**File:** `docs/plans/ai-editor-thin-server/G-007-broken-session-policy/T-002-reject-open-edit-preview/atomic_steps/A-001-integrate-guard-normal-ops.yaml`  
**Location:** `field:prompt` (closing lines)  
**Description:** Prompt ends with "Edit and preview integration — **see sibling AS** and" — incomplete cross-AS reference.  
**Recommended fix:** Remove sibling AS reference; keep open_command-only scope self-contained.  
**Fix-group:** G-007/T-002

**F-058** | blocker | a10  
**File:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/T-003-multi-file-same-session/README.yaml` (+ sole AS file)  
**Location:** `field:description` / AS set  
**Description:** TS requires повторный open, multi-file `file_path` rules for edit/write/close, and `multi_file_bundle` output. Sole AS only creates a unit test; no production AS implements multi-file open orchestration end-to-end.  
**Recommended fix:** Add AS targeting open/edit/write/close modules for multi-file behavior, or narrow TS description to "verification only" if behavior is fully owned elsewhere.  
**Fix-group:** G-003/T-003

**F-059** | major | a4  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/T-001-origin-edit-comparison/atomic_steps/A-001-write-compare-helper.yaml`  
**Location:** `field:prompt` (`compare_session_to_origin` body)  
**Description:** `create_file` prompt defines signatures/docstring but leaves implementation empty (sidecar/tree-temp/text export paths unspecified). Coder cannot implement format-specific compare without reading other modules.  
**Recommended fix:** Add explicit export helper names, import paths, and per-format algorithm steps in prompt (MRS excerpt for C-012).  
**Fix-group:** G-005/T-001

**F-060** | major | a4  
**File:** `docs/plans/ai-editor-thin-server/G-002-upstream-ca-client/T-001-upstream-config-contract/atomic_steps/A-002-upstream-init-exports.yaml`  
**Location:** `field:prompt` (closing paragraph)  
**Description:** Open conditional: "If CaSessionStatus not yet defined when this runs, add export in same commit wave after priority 2 AS" — unresolved fork / cross-AS timing instruction.  
**Recommended fix:** Bind to deterministic priority/depends_on or embed definitive export list with complete upstream state.  
**Fix-group:** G-002/T-001

**F-061** | major | a4  
**File:** `docs/plans/ai-editor-thin-server/G-004-edit-engine-adaptation/T-003-preview-one-shot-ca-read/atomic_steps/A-001-preview-one-shot-upstream-read.yaml`  
**Location:** `field:prompt` (metadata note)  
**Description:** Conditional open decision: "Document behavior in preview_command_metadata.py in **separate AS if file exceeds 400 lines**" — not resolved in this AS set (only one AS in TS).  
**Recommended fix:** Either add metadata AS to this TS or commit to updating metadata in this AS with explicit content.  
**Fix-group:** G-004/T-003

**F-062** | major | outer_a8  
**File:** `docs/plans/ai-editor-thin-server/G-004-edit-engine-adaptation/T-002-preview-opened-file/atomic_steps/A-001-preview-opened-workspace-copy.yaml`  
**Location:** `field:prompt` (embedded `universal_file_preview_command.py`)  
**Description:** Embedded CURRENT FILE includes `# preview-guard-integrated` marker implying post-G-007/T-002 state, while TS runs as first preview adaptation step unless execution is strictly post-G-007.  
**Recommended fix:** Align embedded baseline with actual execution order (G-004 depends on G-007 — embed post-guard-split facade state explicitly and completely).  
**Fix-group:** G-004/T-002

**F-063** | major | a5  
**File:** `docs/plans/ai-editor-thin-server/G-005-write-compare-upload/T-002-write-no-op-branch/atomic_steps/A-001-write-noop-branch.yaml`  
**Location:** `field:prompt` (task section)  
**Description:** "The compare helper module must **already exist** in the same package" — external dependency on G-005/T-001 without embedding `write_compare.py` contract in prompt.  
**Recommended fix:** Include `write_compare` API excerpt in prompt or add cross-TS execution dependency with embedded post-T-001 file state.  
**Fix-group:** G-005/T-002

**F-064** | minor | a9  
**File:** `docs/plans/ai-editor-thin-server/G-006-mcp-surface-cleanup/T-004-verify-help-surface/atomic_steps/A-001-verify-help-command-list.yaml`  
**Location:** `field:verification.expected`  
**Description:** Expected result references "after G-006 T-001..T-003 applied" — cross-TS ordering prose in verification field.  
**Recommended fix:** State expected pytest outcome without referencing sibling TS numbers.  
**Fix-group:** G-006/T-004

**F-065** | minor | layout  
**File:** `docs/plans/ai-editor-thin-server/**/atomic_steps/*.yaml` (all 106)  
**Location:** artifact path  
**Description:** AS live under `atomic_steps/*.yaml`, not `A-NNN-<slug>/README.yaml` per `atomic_step_creation_standard.yaml` §artifact_location, nor inline under TS README per `plan_standard_machine.yaml` level-5 `location`.  
**Recommended fix:** Document accepted plan convention or migrate paths to standard layout (planning hygiene, not execution blocker).  
**Fix-group:** plan-wide layout

---

## Cross-Cutting Summary

### Structural conformance (passes)
- Layout: `source_spec.md`, `spec.yaml`, `G-NNN-<slug>/README.yaml`, `T-NNN-<slug>/README.yaml`, `atomic_steps/*.yaml` — present
- Identifiers: G-001…G-010, T-NNN, A-NNN, C-001…C-025 zero-padded — OK
- GS required fields — OK
- TS required fields (47/47) — OK
- AS required fields (106/106) — OK
- Relation types — only allowed 7 types used

### I1 Coverage
| Check | Result |
|-------|--------|
| I1.a concepts union ≡ spec | **PASS** |
| I1.b relations union ≡ spec | **PASS** |
| I1.c source_ranges union ≡ binding lines | **FAIL** (F-001, F-002–F-006, F-014, F-018, F-020) |

### cycle_1 / cycle_2
- **cycle_1:** **FAIL** — source_ranges misalignment (F-002–F-006)
- **cycle_2:** **FAIL** on G-005, G-006, G-007 (autonomy and source_ranges); **G-003 GREEN** (see G-003 Re-conformance)

### Level 4 per-GS t12/t13
| GS | t12 | t13 |
|----|-----|-----|
| G-001 | PASS | FAIL |
| G-002 | PASS | PASS |
| G-003 | PASS | **PASS** |
| G-004 | PASS | FAIL |
| G-005 | PASS | PASS |
| G-006 | PASS | PASS |
| G-007 | PASS | FAIL |
| G-008 | PASS | PASS |
| G-009 | PASS | PASS |
| G-010 | **FAIL** | PASS |

### Level 5 inventory
- **106** atomic steps across **47** tactical steps
- **8** production files touched by multiple TS (outer_a8 risk): `code_analysis_client.py`, `write_command.py`, `open_command.py`, `close_command.py`, `edit_command.py`, `universal_file_preview_command.py`, `edit_session.py`, `hooks_register_part2.py`

---

## G-001 Workspace Session Directory

**Status:** **GREEN** (post-fix re-check)  
**Branch path:** `docs/plans/ai-editor-thin-server/G-001-workspace-session-directory/`  
**Verified on disk:** YES (2026-06-09)

### Findings resolved

| ID | Resolution |
|----|------------|
| **F-010** | GS `description` rewritten using domain concepts C-018, C-005–C-008 only; implementation/tactics removed from global step |
| **F-035** | Canonical `workspace_root` only; `editor_workspace_dir` alias removed from T-001 and all affected atomic steps |
| **F-036** | All edit artifacts anchored to Edit Subdirectory (C-008) within File Subtree (C-006); path-anchor fork closed |
| **F-026** | T-003, T-004, and T-006 scoped to distinct artifact families: session base / draft-lockfile / sidecar-tree-temp |
| **F-045** | T-003 `concepts` list extended to include C-018, C-005, C-006 referenced in description and inputs |

### Re-check results (GREEN)

| Check | Result |
|-------|--------|
| conceptual_test (GS) | **PASS** |
| t5 (GS + TS + AS) | **PASS** — C-001 added to GS `concepts`; C-007 and C-008 carried on atomic steps |
| t10 (all TS) | **PASS** |
| t13 (T-003 / T-004 / T-006) | **PASS** — non-overlapping artifact families |

### Files modified (19 planning artifacts + 2 `parallel-waves.yaml`)

**Global step**

- `G-001-workspace-session-directory/README.yaml`

**Tactical steps (6)**

- `G-001-workspace-session-directory/T-001-workspace-config-schema/README.yaml`
- `G-001-workspace-session-directory/T-002-path-resolver-entity/README.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/README.yaml`
- `G-001-workspace-session-directory/T-004-format-group-path-adaptation/README.yaml`
- `G-001-workspace-session-directory/T-005-packaging-workspace-volume/README.yaml`
- `G-001-workspace-session-directory/T-006-sidecar-tree-temp-workspace-paths/README.yaml`

**Atomic steps (13)**

- `G-001-workspace-session-directory/T-001-workspace-config-schema/atomic_steps/A-001-config-json-workspace-dir.yaml`
- `G-001-workspace-session-directory/T-002-path-resolver-entity/atomic_steps/A-001-editor-workspace-paths-module.yaml`
- `G-001-workspace-session-directory/T-002-path-resolver-entity/atomic_steps/A-002-unit-test-editor-workspace-paths.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-001-workspace-layout-helper.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-002-split-edit-session-impl.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-003-recreate-edit-session-facade.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-004-edit-session-open-workspace-mode.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-005-delete-edit-session-monolith.yaml`
- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-006-edit-session-mutations.yaml`
- `G-001-workspace-session-directory/T-004-format-group-path-adaptation/atomic_steps/A-001-format-group-workspace-paths.yaml`
- `G-001-workspace-session-directory/T-005-packaging-workspace-volume/atomic_steps/A-001-docker-readme-workspace.yaml`
- `G-001-workspace-session-directory/T-006-sidecar-tree-temp-workspace-paths/atomic_steps/A-001-sidecar-paths-workspace.yaml`
- `G-001-workspace-session-directory/T-006-sidecar-tree-temp-workspace-paths/atomic_steps/A-002-tree-temp-open-workspace.yaml`

**Parallel waves (2)**

- `G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/parallel-waves.yaml`
- `G-001-workspace-session-directory/T-006-sidecar-tree-temp-workspace-paths/atomic_steps/parallel-waves.yaml`

### Note

Cross-branch reference in G-003 to `layout.edit_subdir` is outside G-001 scope. Flagged for G-003 resync; no change applied in this fix pass.

---

## G-008 Client Single Facade

**Status:** **GREEN** (post-fix re-check)  
**Branch path:** `docs/plans/ai-editor-thin-server/G-008-client-single-facade/`  
**Verified on disk:** YES (2026-06-09)

### Findings resolved

| ID | Resolution |
|----|------------|
| **F-021** | GS `description` rewritten using domain concepts only (C-003, C-004, C-009, C-016, C-020, C-022); removed `UniversalFileClient`, `FileSessionClient`, `EditorFileClient`, `LocalEditWorkspace`, `CLIENT_FACADE_COMMANDS`, `ai-editor-client` |
| **F-046** | T-002 `concepts` extended with C-016 (referenced in description) |
| **F-047** | T-003 `concepts` extended with C-009 (referenced in description) |

### Re-check results (GREEN)

| Check | Result |
|-------|--------|
| conceptual_test (GS) | **PASS** — no concrete class/module/constant/package names in G-008 `description` |
| t5 (GS + TS + AS) | **PASS** — every `C-NNN` cited in description/prompt fields appears in that artifact's `concepts` list |
| t12/t13 (G-008 TS set) | **PASS** (unchanged) |

### Files modified (8 planning artifacts)

**Global step**

- `G-008-client-single-facade/README.yaml` — `description` (F-021)

**Tactical steps (2)**

- `G-008-client-single-facade/T-002-deprecate-parallel-facades/README.yaml` — `concepts` (F-046)
- `G-008-client-single-facade/T-003-update-server-api-examples/README.yaml` — `concepts` (F-047)

**Atomic steps (5)** — concept sync + a4/a5/a8 LLAMA-readiness pass

- `G-008-client-single-facade/T-001-universal-client-ca-session/atomic_steps/A-001-universal-file-client-ca-session.yaml`
- `G-008-client-single-facade/T-002-deprecate-parallel-facades/atomic_steps/A-001-deprecate-parallel-facades.yaml` — added C-016
- `G-008-client-single-facade/T-002-deprecate-parallel-facades/atomic_steps/A-002-deprecate-init-exports.yaml` — added C-016
- `G-008-client-single-facade/T-003-update-server-api-examples/atomic_steps/A-001-align-server-api-examples.yaml` — added C-009
- `G-008-client-single-facade/T-003-update-server-api-examples/atomic_steps/A-002-update-universal-files-example.yaml` — added C-009

### Note

Pre-existing **a10** gap: T-003 description references documenting File Workflow (C-009) in client library README; no AS targets `client/README.md`. Out of scope for F-021/F-046/F-047; flag for future AS if required.

---

## G-003 Re-conformance (2026-06-09)

**Status:** **GREEN** (post-fix re-check)  
**Branch path:** `docs/plans/ai-editor-thin-server/G-003-open-close-orchestration/`  
**Verified on disk:** YES (2026-06-09)

### Findings resolved

| ID | Resolution |
|----|------------|
| **F-012** | Session Guard (C-024) semantics added to GS `description` and `executor_brief` (touch, NOT_FOUND reject on normal open); `depends_on: G-007` clarified as implementation-order only, not silent sibling dependency |
| **F-013** | GS `description` reframed via C-004 property — «отдельный editor group UUID запрещён» — instead of implementation-level «editor UUID» |
| **F-014** | GS `source_ranges` extended to cover Open stage lines 35–40 (`{7m3q}`, `{c4f2}`) and Close line 47 (`{5v0w}`), plus supporting session/bundle lines 21, 29, 31 |
| **F-027** | T-002 scoped to single-file-per-invocation open orchestration; T-003 owns repeat-open and N>1 `file_path` disambiguation — non-overlapping TS scopes (t13 PASS) |
| **F-039** | T-002 `concepts` extended with C-006, C-018, C-019 referenced in description |
| **F-048** | T-004 `concepts` extended with C-016 referenced in description |
| **F-051** | T-002 A-002 embedded `open_command_runtime.py` replaced with syntactically valid post-G-007/T-000 baseline shell (`raise NotImplementedError` stub, not corrupted truncation) |
| **F-053** | T-004 A-001 embedded `close_command.py` replaced with valid post-T-003 A-006 + G-007 guard baseline (no `async # …` syntax corruption) |
| **F-058** | T-003 expanded from verification-only AS to full production AS set (A-001–A-007): error code, bundle helpers, repeat-open runtime, edit/write/close disambiguation, unit test |

### Re-check results (GREEN)

| Check | Result |
|-------|--------|
| cycle_2 c6 (source_ranges) | **PASS** — G-003 `source_ranges` align with Open/Close stage binding lines |
| cycle_2 c7 (executor completeness) | **PASS** — Session Guard, open rejection, and stage semantics present in GS triple |
| cycle_2 c8 (no silent sibling dependency) | **PASS** — Guard semantics local to G-003 text; `depends_on G-007` documented as order only |
| t5 (GS + TS + AS) | **PASS** — every `C-NNN` cited in description/prompt fields appears in that artifact's `concepts` list |
| t13 (T-002 / T-003) | **PASS** — single-file open vs multi-file extension scopes do not overlap |
| a8 (embedded file state) | **PASS** — mandatory CURRENT FILE blocks in A-002, A-003, A-001 (T-004) are complete and syntactically valid |
| a10 (TS coverage by AS set) | **PASS** — T-003 AS set covers repeat-open, multi-file disambiguation, and `multi_file_bundle` output |
| ast.parse (mandatory blocks) | **PASS** — 0 failures on embedded Python in mandatory CURRENT FILE fences |

### Files modified/created (20 planning artifacts)

**Global step**

- `G-003-open-close-orchestration/README.yaml`

**Tactical steps (5)**

- `G-003-open-close-orchestration/T-001-ca-session-bundle-registry/README.yaml`
- `G-003-open-close-orchestration/T-002-open-orchestration/README.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/README.yaml`
- `G-003-open-close-orchestration/T-004-close-orchestration/README.yaml`
- `G-003-open-close-orchestration/T-005-open-close-schemas-metadata/README.yaml`

**Atomic steps (13)**

- `G-003-open-close-orchestration/T-001-ca-session-bundle-registry/atomic_steps/A-001-ca-session-bundle-registry.yaml`
- `G-003-open-close-orchestration/T-002-open-orchestration/atomic_steps/A-001-open-schema-ca-session.yaml`
- `G-003-open-close-orchestration/T-002-open-orchestration/atomic_steps/A-002-open-orchestration-upstream.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-001-session-file-path-error-code.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-002-multi-file-bundle-helpers.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-003-repeat-open-runtime-branch.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-004-edit-multi-file-file-path.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-005-write-multi-file-file-path.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-006-close-multi-file-disambiguation.yaml`
- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/A-007-multi-file-bundle-unit-test.yaml`
- `G-003-open-close-orchestration/T-004-close-orchestration/atomic_steps/A-001-close-orchestration-unlock.yaml`
- `G-003-open-close-orchestration/T-005-open-close-schemas-metadata/atomic_steps/A-001-open-metadata-ca-session.yaml`
- `G-003-open-close-orchestration/T-005-open-close-schemas-metadata/atomic_steps/A-002-close-metadata-unlock.yaml`

**Parallel waves (1)**

- `G-003-open-close-orchestration/T-003-multi-file-same-session/atomic_steps/parallel-waves.yaml`

### Overall verdict

**GREEN** for G-003 branch — all nine G-003 fix-group findings resolved; cycle_2 autonomy/source_ranges, t5/t13, a8/a10, and embedded-Python parse checks pass.

### Optional non-blockers

- **T-003 `status: draft`** — tactical step remains `draft` while siblings are `ready_for_review`; promote when AS set is frozen.
- **A-005 fence hygiene** — T-003 A-005 uses partial-file `py` fence excerpts for `write_command.py`; optional normalization to full-file CURRENT FILE CONTENT convention for consistency with other AS.

---

## G-002 Module Split — `code_analysis_client.py` >400-Line Resolution (2026-06-09)

**Trigger:** Cumulative embedded `code_analysis_client.py` across T-002..T-007 reached ~529 lines (a3 / `code_file_size_limit` violation).

**Resolution:** Tactical-level split into two modules; public API unchanged on `CodeAnalysisClient`.

### Chosen module boundary

| Module | Responsibilities | Final embedded lines (T-007 terminal AS) |
|--------|------------------|----------------------------------------|
| `ai_editor/core/upstream/code_analysis_client.py` | Singleton, config/RPC, project discovery, `CaSessionStatus` / `validate_ca_session`, thin public wrappers (`lock_file_and_download`, `unlock_session_file`, `upload_session_file_content`, `download_without_lock`, `upload_create_and_lock`) delegating to transfer helpers | **345** (T-007/A-001 CURRENT FILE, includes complete final state) |
| `ai_editor/core/upstream/code_analysis_file_transfer.py` | `normalize_rel_path`, `resolve_file_id_for_path`, chunked download/upload helpers, `download_bytes_without_lock`, `upload_create_save` | **194** (T-007/A-002 CURRENT FILE) |

**Import direction:** `code_analysis_client` → `code_analysis_file_transfer` (one-way at import time; TYPE_CHECKING in transfer module).

### Files created/modified

| Action | Path |
|--------|------|
| Modified | `G-002/README.yaml` — two-module C-017 boundary |
| Modified | `T-003`, `T-004`, `T-005`, `T-006`, `T-007` `README.yaml` — module-boundary prose + `code_analysis_file_transfer_module` outputs |
| Created | `T-003/A-002-transfer-module-skeleton.yaml`, `T-003/A-003-open-download-transfer-helpers.yaml` |
| Created | `T-005/A-002-upload-bytes-transfer-helper.yaml` |
| Created | `T-006/A-002-download-without-lock-pipeline.yaml` |
| Created | `T-007/A-002-upload-create-save-helper.yaml` |
| Created | `G-002/code_analysis_file_transfer_parallel_waves.yaml` |
| Revised | `T-002..T-007` client `A-001` AS — transfer helpers removed; imports/delegation added |
| Fixed | `T-003/A-001` `depends_on: ['A-003']`, `priority: 3` (was invalid `['A-001']`) |

### Re-run checks (evidence)

| Check | Verdict | Evidence |
|-------|---------|----------|
| **a3** (each module ≤400) | **GREEN** | Client chain max 345 (T-007/A-001); transfer max 194 (T-007/A-002) |
| **a2** (one-file-per-AS) | **GREEN** | All 11 AS target exactly one of the two module paths |
| **outer_a8** (cumulative chains, valid Python) | **GREEN** | `py_compile` OK on all 11 embedded blocks; per-module chains consistent |
| **a7** (`depends_on`) | **GREEN** | T-003 client A-001 → transfer A-003; T-003 transfer A-003 → A-002 |
| **t5** (concept refs) | **GREEN** | C-017/C-023 split documented in TS READMEs; AS concepts unchanged semantically |

**Verified on disk:** YES (re-read 2026-06-09 after corrective T-007 pass).

**Remaining G-002 findings (unchanged by this pass):** F-011 (GS conceptual test), F-031–F-034 (TS t10/t5), F-041–F-042, F-060 (A-002 export fork).

---

## Recommended Fix Order (cascade-aware)

1. **`spec.yaml`** — fix `source_ranges` for C-015, C-016, C-014, C-024, C-004 (F-002–F-006) → re-run cycle_1
2. **G-007, G-006** — align GS `source_ranges` with corrected MRS (F-018, F-020); ~~G-003 F-014~~ **RESOLVED**
3. **G-005** — close cycle_2 autonomy gap (F-016); ~~G-003 F-012~~ **RESOLVED**
4. **All GS** — scrub `description` for conceptual-test leaks (F-010, F-011, ~~F-013~~, F-015, F-017, F-019, ~~F-021~~, F-022, F-023)
5. **G-010** — close t12 coverage gaps (F-024, F-025)
6. **G-001, G-004, G-007** — resolve t13 overlaps and T-000 boundary (F-026, F-028–F-029, F-044); ~~G-003 F-027~~ **RESOLVED**
7. **G-002, G-005, G-001, G-007, G-009** — resolve t10 open decisions (F-030–F-038)
8. **G-007/T-000, G-004** — fix corrupted embedded Python in AS prompts (F-052, F-054); ~~G-003 F-051, F-053~~ **RESOLVED**
9. ~~**G-002** — rebuild cumulative `code_analysis_client.py` chain (F-055)~~ **PARTIAL** — file-size split resolved (see G-002 module-split section); F-055 outer_a8 chain **GREEN** for split modules; F-060 remains
10. ~~**G-003/T-003** — add production AS or narrow TS (F-058)~~ **RESOLVED**
11. **Remaining AS** — a4/a5 self-sufficiency and outer_a8 baselines (F-056, F-057, F-059–F-063)

---

## Is the Plan Ready to Descend / Freeze?

**No.**

The plan has **16 blocker** findings across levels 2–5 (seven resolved in G-003 branch — see G-003 Re-conformance). Upper cycles (cycle_1, cycle_2) are not green plan-wide. Level 4 has t12 failures in G-010 and t13 independence failures in G-001, G-004, G-007 (G-003 **GREEN**). Level 5 has corrupted embedded file content in multiple atomic steps that would block weak-model coders (G-003 mandatory blocks **GREEN**).

**Minimum gate before freeze:**
- cycle_1 and cycle_2 green (fix `spec.yaml` source_ranges and GS autonomy/source_ranges)
- All t12/t13 checks green per GS
- All a8 blockers resolved (valid embedded file content; cross-TS chains consistent)
- All a10 blockers resolved (TS fully covered by AS set)

**After blockers:** re-run full verification before marking any level `frozen` or briefing coders.
