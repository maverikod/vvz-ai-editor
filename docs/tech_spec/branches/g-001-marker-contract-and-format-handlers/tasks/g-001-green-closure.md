# G-001 Green Closure — Corrective Tactical Task

## Purpose

Close G-001 (Marker Contract and Format Handlers) to GREEN: fix T-002 format-handler deviations found in verification, restore Python unmark byte-exact invertibility, and re-run the G-001 pytest suite until all non-xfail tests pass.

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- HRS: `docs/plans/marked_tree_unification/source_spec.md` (Blocks 1–2, labels `{a001}`–`{a007}`, `{b000}`–`{b005}`, `{n001}`)
- MRS: `docs/plans/marked_tree_unification/spec.yaml` (C-001, C-002, C-005, C-007, C-008, C-009, C-024, C-025)
- Global step: `docs/plans/marked_tree_unification/G-001-marker-contract-and-format-handlers/README.yaml`
- Tactical steps: T-001, T-002, T-003 under same G-001 directory

## Scope

**Included:**
- Fix Python handler hybrid marker scheme per A-007 / HRS `{b005}` (metadata `___id___` on def/class/async-def/decorator; trailing comment fallback only when metadata unsupported)
- Fix Python handler `AsyncFunctionDef` mark/unmark coverage (all-nodes rule `{b000}`)
- Fix Python handler unmark trailing-whitespace regression (parity test blockers)
- Fix JSON handler byte-exact unmark (preserve trailing newline from source)
- Run `black` on `python_handler.py`; fix mypy `no-any-return` in tree package files flagged by verification (minimal, no scope creep)
- Re-run `pytest tests/tree_pipeline_parity/` until all non-xfail tests pass

**Excluded:**
- Markdown handler full block-type expansion (tables, hr, etc.) — defer unless parity tests fail
- YAML semantic-only round-trip policy change — escalate to global orchestrator if byte-exact cannot be achieved without HRS change
- Dedicated `tests/tree/test_contracts.py` suite — P1 follow-on, not blocking GREEN if parity suite passes
- `FormatHandler.op_*` edit methods — belong to G-004; do not remove in this closure
- HRS/MRS/spec.yaml edits — escalate to global orchestrator
- `test_data/` — server-guarded; not touched

## Boundaries

- Do NOT modify `source_spec.md` or `spec.yaml`
- Do NOT touch `test_data/`
- Do NOT refactor unrelated modules outside `code_analysis/tree/` and parity tests if test updates required

## Dependencies

- none

## Parallelization note

Two independent coder tracks may run in parallel:
1. Python handler fixes (metadata, AsyncFunctionDef, unmark whitespace)
2. JSON handler trailing-newline fix

## Expected outcome

- T-001 remains GREEN (no changes expected)
- T-002 becomes GREEN (Python hybrid + JSON byte round-trip)
- T-003 remains GREEN (no changes expected)
- `pytest -v tests/tree_pipeline_parity/` — all non-xfail tests pass (currently 2 failures in Python roundtrip)
- `flake8 code_analysis/tree/` — pass
- `black --check code_analysis/tree/` — pass

## Correction items (from verification 2026-05-31)

### P0 — Test blockers

1. **`code_analysis/tree/handlers/python_handler.py` — unmark invertibility**: `_comment_trailing()` attaches `SimpleWhitespace(" ")` before `# ___id___:<sid>`; unmark leaves trailing space before newline. Fails `test_python_unified_unmark_roundtrip` and `test_python_node_id_set_parity_documented`. Unmark must restore original source bytes exactly.

2. **`code_analysis/tree/handlers/python_handler.py` — hybrid marker scheme (A-007)**: Plan requires `metadata["___id___"] = <int>` on `FunctionDef`, `ClassDef`, `AsyncFunctionDef`, `Decorator`. Current code uses header comment on `IndentedBlock` instead. Mark path must write metadata when node supports it; unmark must clear metadata (path partially exists).

3. **`code_analysis/tree/handlers/python_handler.py` — AsyncFunctionDef gap**: `_MarkTransformer` / `_UnmarkTransformer` implement `leave_FunctionDef` only; `AsyncFunctionDef` is addressable in `parse_content` but not marked. Add symmetric `leave_AsyncFunctionDef` handlers.

4. **`code_analysis/tree/handlers/json_handler.py` — byte-exact unmark**: `json.dumps` drops trailing `\n`. Detect `content.endswith("\n")` in mark/unmark and preserve trailing newline so `unmark(mark(source)) == source`.

### P1 — Hygiene (same branch, non-blocking for GREEN if parity passes)

5. **`code_analysis/tree/format_handler.py`**: Move `compute_content_checksum` import to module level per A-001; ensure `resolve_short_id_for_uuid` propagates `UnknownTreeNodeUuidError` per spec.

6. **mypy**: Fix `no-any-return` in `format_handler.py`, `python_handler.py`, `cst_query_selector.py` (minimal annotations only).

## Questions/escalation rule

Escalate to global orchestrator if:
- YAML handler cannot achieve byte-exact round-trip without relaxing HRS byte-exact invariant
- Python libcst metadata API cannot support `___id___` on required node types without plan change
- Removing pre-loaded G-004 `op_*` methods from FormatHandler is required for G-001 freeze (currently accepted as scope bleed, not blocking)

## Subordinate verification checkpoint

After coder_auto completes P0 items, tester_auto must re-run:
```bash
pytest -v tests/tree_pipeline_parity/
black --check --target-version py314 code_analysis/tree/
flake8 code_analysis/tree/
```

Researcher_code must re-audit T-002 only and confirm GREEN or list remaining gaps.
