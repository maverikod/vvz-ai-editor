<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step: `annotation_pytest_cst_modify_tree_command`

## 1. Executor role

`coder_auto`

## 2. Execution directive

Add pytest coverage in `tests/test_cst_modify_tree_command.py` for leaf `Annotation` replace: one test for parameter type annotation, one for return annotation, and one optional equivalence test mirroring `TestBatchedTwoParamReplacesEquivalence` for two `Annotation` replaces on the same signature line. Follow patterns from `TestReplaceLeafParamAndName` and `TestBatchedTwoParamReplacesEquivalence` in the same file.

## 3. Parent links (mandatory)

- Technical specification: `docs/tech_spec/tech_spec.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Parent tactical task: `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_annotation_fine_grained_signature_edits.md`

## 4. Step scope

| action | Target file (repo root relative) |
|--------|----------------------------------|
| modify | `tests/test_cst_modify_tree_command.py` |

## 5. Dependency contract

- **Depends on:** `annotation_replace_and_validate_wiring` completed (replace + validate wired for `Annotation`).
- **Blocks:** none (last serial step).

## 6. Required context

- Tests use `create_tree_from_code`, `build_tree_operations`, `modify_tree`, `get_tree`, same as existing leaf-replace tests near line 830.
- Source example from tactical task: `def g(x: int) -> None:\n    pass` (four spaces before `pass`).

## 7. Read first

- `tests/test_cst_modify_tree_command.py` — full file (especially `TestReplaceLeafParamAndName`, `TestBatchedTwoParamReplacesEquivalence`, helpers `_node_id_first_type`, `_param_node_ids_on_line`, and module imports).

## 8. Expected file change

- Append module-level constant `SOURCE_ANNOTATION_SIGNATURE` (or equivalent name) holding the multi-line string for `def g(x: int) -> None:` with `pass` body.
- Add helper `_annotation_node_ids_on_line(tree, line: int) -> list[str]` that collects all `meta.type == "Annotation"` on the given line, sorts by `(start_col, end_col)`, requires `len >= 2`, returns ids (same pattern as `_param_node_ids_on_line`).
- Add class `TestReplaceLeafAnnotation` with:
  - `test_build_ops_replace_param_annotation_keeps_return_and_body` — replace first annotation id with `code_lines`: `[": str"]` (or `code` string `: str`); assert resulting code contains `x: str` and still contains `-> None` and `pass`.
  - `test_build_ops_replace_return_annotation_keeps_param_and_body` — fresh tree from same source; replace **second** annotation id with `["-> bool"]`; assert `x: int` remains and return becomes `-> bool`, body unchanged.
- Add class `TestBatchedTwoAnnotationReplacesEquivalence` (optional but recommended) with:
  - `test_two_annotation_replaces_one_modify_matches_sequential` — same structure as `TestBatchedTwoParamReplacesEquivalence.test_two_param_replaces_one_modify_matches_sequential`: sequential path loads tree, replaces first annotation to `: str`, reloads tree, replaces second to `-> bool`, captures `code_seq`; batch path loads fresh tree, `build_tree_operations` with two replace ops in one list (ids from `_annotation_node_ids_on_line` for first tree), `modify_tree` once, assert `code_batch == code_seq`.

## 9. Forbidden alternatives

- Do not edit production modules in this step.
- Do not add tests under `test_data/` or touch `vast_srv`.
- Do not use `typing.Any` in new helpers unless already used in file for same pattern (prefer omit).

## 10. Atomic operations

1. Add constant and helper near existing `SOURCE_TWO_PARAMS` / `_param_node_ids_on_line`.
2. Add test classes after `TestBatchedTwoParamReplacesEquivalence` block (end of file region) to keep related tests grouped.

## 11. Expected deliverables

- At least two new tests proving param and return annotation replace behavior.
- Optional third test proving batch equivalence for two annotations.
- Full `pytest tests/test_cst_modify_tree_command.py` passes.

---

## LLAMA-readiness — target: `tests/test_cst_modify_tree_command.py`

### Target file full path

`tests/test_cst_modify_tree_command.py` — **action:** modify.

### File header (module docstring)

Unchanged (existing module docstring stays).

### Imports (complete list after edit)

No new imports required beyond existing:

- `from __future__ import annotations`
- `import pytest`
- Existing imports from `code_analysis.commands.cst_modify_tree_command`, `cst_modify_tree_ops_build`, `tree_builder`, `tree_modifier`, `mcp_proxy_adapter.commands.result`

If a new symbol is unused, do not import it.

### Class/function skeleton — new symbols

```text
SOURCE_ANNOTATION_SIGNATURE = """def g(x: int) -> None:
    pass
"""

def _annotation_node_ids_on_line(tree, line: int) -> list[str]:
    """Return Annotation node_ids on `line` sorted left-to-right."""

class TestReplaceLeafAnnotation:
    def test_build_ops_replace_param_annotation_keeps_return_and_body(self, tmp_path: ...) -> None: ...
    def test_build_ops_replace_return_annotation_keeps_param_and_body(self, tmp_path: ...) -> None: ...

class TestBatchedTwoAnnotationReplacesEquivalence:
    def test_two_annotation_replaces_one_modify_matches_sequential(self, tmp_path: ...) -> None: ...
```

Use the same `tmp_path` typing style as neighboring tests (with or without annotation—match file).

### Method logic — `test_build_ops_replace_param_annotation_keeps_return_and_body`

1. Build path `str(tmp_path / "ann_param.py")`.
2. `tree = create_tree_from_code(path, SOURCE_ANNOTATION_SIGNATURE)`.
3. `tree_id = tree.tree_id`.
4. `ids = _annotation_node_ids_on_line(tree, line=1)`; assert `len(ids) >= 2` (param annotation first, return second).
5. `param_ann_id = ids[0]`.
6. `ops, err = build_tree_operations(tree, [{"action": "replace", "node_id": param_ann_id, "code_lines": [": str"]}])`.
7. Assert `err is None`, `len(ops) == 1`, `ops[0].node_id == param_ann_id`.
8. `modify_tree(tree_id, ops)`; `out = get_tree(tree_id)`; assert `out is not None`.
9. `code = out.module.code`; assert `"x: str"` in `code` or substring showing `str` as param type; assert `-> None` still in `code`; assert `pass` in `code`.

### Method logic — `test_build_ops_replace_return_annotation_keeps_param_and_body`

1. New path and new tree from same `SOURCE_ANNOTATION_SIGNATURE`.
2. `ids = _annotation_node_ids_on_line(tree, line=1)`; use `return_ann_id = ids[1]`.
3. Replace with `code_lines`: `["-> bool"]`.
4. After modify, assert code still has `x: int` (parameter type unchanged) and contains `-> bool` and does not contain `-> None`; assert `pass` remains.

### Method logic — `_annotation_node_ids_on_line`

1. Collect pairs `(nid, meta)` where `meta.type == "Annotation"` and `meta.start_line == line`.
2. Sort by `(meta.start_col, meta.end_col)`.
3. If `len < 2`, `pytest.fail` with message naming expected at least two annotations on that line.
4. Return list of `nid` strings.

### Method logic — `test_two_annotation_replaces_one_modify_matches_sequential` (optional)

Mirror `TestBatchedTwoParamReplacesEquivalence.test_two_param_replaces_one_modify_matches_sequential` line-for-line structure:

1. Sequential: first replace `ids[0]` with `": str"` via single-op modify; reload tree; recompute `_annotation_node_ids_on_line` on updated tree for line 1 for second op (ids may change—same pattern as param test uses `ids_mid`).
2. Second replace second annotation with `"-> bool"`.
3. Batch: fresh tree, `build_tree_operations` with two replaces: first id `ids_b[0]` with `": str"`, second id `ids_b[1]` with `"-> bool"` in one list—**note:** for batch, both node_ids must refer to the **initial** tree’s annotation ids; if the tactical batch semantics require bottom-to-top or id refresh, follow the same resolution strategy as the Param batch test (read that test: it uses initial `ids_b` for both ops). If batch fails because second id is stale, adjust only test ordering to match established batch contract (document in test docstring)—**mandatory:** final assertion `code_batch == code_seq`.

### Error handling

- Tests use assertions only; no try/except except as existing tests do (none expected).

### Return values

- Test functions return `None`.

### Edge cases

- Line number `1` holds both annotations for the given source; if tree builder reports a different line (e.g. leading blank line), use the line where `Param`/`Annotation` nodes actually land—**mandatory:** discover line from metadata: e.g. first `Annotation`’s `start_line` instead of hardcoding if needed.

### Constants and literals

- `SOURCE_ANNOTATION_SIGNATURE` exact text:
  - Line 1: `def g(x: int) -> None:`
  - Line 2: four spaces + `pass`
- Replace snippets: `": str"`, `"-> bool"` as `code_lines` single-element lists as specified.

---

## 12. Mandatory validation

From repository root, `.venv` active:

```text
black tests/test_cst_modify_tree_command.py
flake8 tests/test_cst_modify_tree_command.py
mypy tests/test_cst_modify_tree_command.py
```

(If mypy is not run on tests in this project, follow `docs/PROJECT_RULES.md` CR-007 for touched paths—if tests are excluded from mypy, run mypy only on changed production files from prior steps is not required here; **minimum:** black + flake8 on this test file.)

```text
pytest tests/test_cst_modify_tree_command.py -v
```
→ All tests **PASSED**.

```text
pytest tests/ -q
```
→ Full suite passes (mandatory completion condition).

## 13. Decision rules

- If optional batch test cannot be made stable without production changes, remove the optional class and keep only the two required tests; document skip reason in tactical report, not in code comments longer than one line.

## 14. Blackstops

- Stop if `len(_annotation_node_ids_on_line(...)) < 2` on the sample source; inspect metadata types/lines from `tree.metadata_map` and adjust `SOURCE_ANNOTATION_SIGNATURE` or line discovery per section “Edge cases”.

## 15. Handoff package

- Test file updated; `pytest tests/` green; tactical task ready for commit per parent task.

## Exact test expectations (summary)

| Test | Assert |
|------|--------|
| `test_build_ops_replace_param_annotation_keeps_return_and_body` | After replace, signature shows `str` for `x`, return still `None`, body has `pass`. |
| `test_build_ops_replace_return_annotation_keeps_param_and_body` | Param stays `int`, return becomes `bool`, body has `pass`. |
| `test_two_annotation_replaces_one_modify_matches_sequential` (if present) | Batch code equals sequential code string. |

## Forbidden patterns (summary)

- No production code changes in this step.
- No placeholder tests (`pytest.skip` without cause).
