# G-004 Green Closure — Corrective Tactical Task (v3 — final)

## Purpose

Close G-004 to **full GREEN** on both criteria: (1) code coherent with plan/MRS and (2) all branch tests pass. Global orchestrator rejected Partial-GREEN on criterion (1).

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- HRS: `docs/plans/marked_tree_unification/source_spec.md` (Blocks 6, 8, 9, 10)
- MRS: `docs/plans/marked_tree_unification/spec.yaml` (C-015–C-019, C-025)
- Global step: `docs/plans/marked_tree_unification/G-004-edit-operations-preview-and-tree-query/README.yaml`
- Tactical steps: T-001, T-002, T-003 under same G-004 directory

## Scope (v2 — global orchestrator decisions 2026-05-31)

**IN SCOPE — must fix for full GREEN:**

1. **C-015 `op_edit_attributes`** — real metadata mutation (not no-op) for Python, JSON, YAML handlers minimum; Text/Markdown if they claim to implement the op. Tests must prove: content unchanged, position unchanged, short_id unchanged, attribute changed.

2. **HRS `{j003}` XPath grammar** — engine MUST parse and evaluate exactly:
   `//ClassDef//FunctionDef[@name='execute'][start_line>=100]`
   (descendant `//` step after a prior step). Test must use this exact selector string. Escalate only on concrete technical impossibility.

3. **`universal_file_preview` command wiring** — **IN G-004 per README line 24–25 and HRS `{f001}`:**
   > "Establishes that the preview command builds a valid marked tree via TreeLifecycle before returning navigation results if the tree is absent or invalid."
   Wire preview command to `PreviewNavigation` + `TreeLifecycle`; int `short_id` at API boundary per `{f002}`.

4. **Operator confirmation** — MRS C-019 `ge/le/gt/lt` prose = engine `>=`/`<=`/`>`/`<`; no MRS edit. Confirm via test only.

**OUT OF SCOPE — report to global orchestrator (do NOT assign to G-005):**

- **`apply_edit_operation` ↔ EditSession wiring** — G-003 owns per-mutation cycle `{d003}`; G-004 defines EditOperation contract only. Coordinate via global orchestrator with G-003.

- **TreeQuery MCP consumer wiring** — pending researcher confirmation of which command(s) HRS/G-004 assign; `{j001}` defines system behavior but does not name a command file. Report finding before coding.

**Excluded:** HRS/MRS edits, `test_data/` direct access, EditSession internals from this branch.

## Boundaries

- Do NOT modify `source_spec.md` or `spec.yaml`
- Do NOT modify G-003 EditSession mutation internals
- Do NOT touch `test_data/` (server-guarded)

## Dependencies

- Wave 1 (edit-attributes + XPath grammar) can run parallel with wave 2 (preview command wiring) after researcher confirms tree-query consumer scope

## Parallelization note

Up to 4 concurrent coder tracks:
1. op_edit_attributes + tests (T-001)
2. CSTQuery double-`//` grammar + exact HRS test (T-003)
3. universal_file_preview → PreviewNavigation + TreeLifecycle (T-002 / {f001})
4. researcher_code: tree-query consumer command identification

## Expected outcome

- C-015 attribute invariant proven by tests for each implemented format
- HRS `{j003}` example selector passes parse + evaluate test
- `universal_file_preview` uses TreeLifecycle build-before-navigate and PreviewNavigation with int short_id
- Full G-004 pytest suite green (tests/tree/, parity, related unit tests)
- Clear scope report for TreeQuery consumer and EditSession wiring

## Correction items (v2)

### P0 — C-015 edit-attributes (mandatory)
- Implement `op_edit_attributes` in `python_handler.py`, `json_handler.py`, `yaml_handler.py` (and text/markdown if applicable)
- Persist metadata without changing content, position, or short_id
- Add `tests/tree/test_edit_attributes.py` (or extend `test_edit_operations.py`)

### P0 — HRS XPath grammar (mandatory)
- Extend `code_analysis/cst_query/parser.py` (and executor if needed) for chained `//` steps
- Update `tests/tree/test_cst_query_selector.py` to use EXACT selector from `{j003}` line 570

### P0 — Preview command coherence (mandatory per {f001})
- Wire `code_analysis/commands/universal_file_preview/` to `PreviewNavigation`, `PreviewSelector`, TreeLifecycle
- int short_id node_ref at command boundary

### P1 — TreeQuery consumer (research first)
- Identify which MCP command implements `{j001}` tree query system
- Report whether G-004 README assigns wiring to this branch or another

## Questions/escalation rule

Escalate to global orchestrator only if:
- Double-`//` XPath is technically impossible in current parser architecture (must cite specific blocker)
- TreeQuery consumer assignment contradicts plan hierarchy

## Completion status (v3 — 2026-05-31)

### Criterion (1) — plan/MRS coherence: **PASS**

| P0 item | Status | Evidence |
|---------|--------|----------|
| C-015 `op_edit_attributes` | DONE | `python/json/yaml_handler.op_edit_attributes`; `tests/tree/test_edit_attributes.py` |
| HRS `{j003}` chained `//` | DONE | `cst_query/parser.py`, `executor.py`; exact selector in `test_cst_query_selector.py` |
| Preview `{f001}` wiring | DONE | `marked_tree_loader.py`, `marked_tree_navigation.py`, `navigation.py`; `test_marked_tree_preview.py` |
| C-019 operators | DONE | Parser/executor implement `>=`, `<=`, `>`, `<`; `>=` covered by `{j003}` tests |

### Criterion (2) — tests pass: **PASS**

134 passed, 0 failed, 4 expected xfails (parity legacy-oracle).

### Routed out of G-004 (global orchestrator action)

1. **TreeQuery MCP consumer** — `{j001}` behavior defined; no G-004 atomic step assigns command wiring. `TreeQuery` exists in `code_analysis/tree/tree_query.py`; no MCP command imports it. Route to appropriate global step.
2. **`apply_edit_operation` ↔ EditSession** — G-003 owns per-mutation cycle `{d003}`. G-004 defines contract only. Coordinate G-003 integration separately.
3. **Text/Markdown `op_edit_attributes` MAP persistence** — in-memory only; not in closure minimum (py/json/yaml tested).

## Full preview module verification (2026-05-31 follow-up)

Global orchestrator requested FULL preview modules (not curated subset):

| Module | Result |
|--------|--------|
| `tests/test_tree_temp_universal_yaml_preview_sessions.py` | 5/5 pass |
| `tests/test_tree_temp_universal_json_preview_sessions.py` | 5/5 pass |
| `tests/commands/universal_file_preview/` (4 files) | 15/15 pass |
| `tests/test_universal_file_preview_smoke.py` | 44/44 pass |
| **Total (7 modules)** | **69/69 pass** |

Previously-failing `test_tree_temp_universal_*_preview_sessions` tests: **PASS**.

## Session preview routing fix (2026-05-31 — G-003 routed)

Five tests outside the 7-module preview glob (diagnosed G-004 preview-routing):

| Test | Module | Result |
|------|--------|--------|
| `test_yaml_tree_temp_insert_visible_in_session_preview` | `tests/test_tree_temp_edit_session_preview.py` | pass |
| `test_yaml_tree_temp_replace_visible_in_session_preview` | `tests/test_tree_temp_edit_session_preview.py` | pass |
| `test_json_tree_temp_preview_matches_draft` | `tests/test_tree_temp_edit_session_preview.py` | pass |
| `test_tree_temp_preview_without_commit_leaves_source_unchanged` | `tests/test_tree_temp_edit_session_preview.py` | pass |
| `test_create_invalid_json_preview_returns_raw_text` | `tests/test_edit_on_invalid_files.py` | pass |

Fix scope: `marked_tree_navigation.py`, `marked_tree_loader.py`, `navigation.py` (+ minimal `tree_temp_edit_batch.py` insert-index for draft block order). No EditSession internals changed.

Verification: 5/5 named + 69/69 preview suite + 33/33 G-003 edit-session modules (8 files).
