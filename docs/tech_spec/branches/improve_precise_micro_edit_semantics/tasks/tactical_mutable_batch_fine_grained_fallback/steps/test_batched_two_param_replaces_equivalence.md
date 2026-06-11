<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step A2: Batched two-Param replaces equivalence test

## Executor role

`coder_auto`

## Execution directive

Add a pytest test in `tests/test_cst_modify_tree_command.py` that proves one `modify_tree` call with two `REPLACE` operations on two distinct `Param` nodes yields the same module source as two successive `modify_tree` calls each carrying a single `REPLACE`, mirroring the style and helpers of `TestReplaceLeafParamAndName`.

## Parent links (mandatory)

- Parent global step: [`docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`](../../../../../steps/improve_precise_micro_edit_semantics.md)
- Parent tactical task: [`docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_mutable_batch_fine_grained_fallback.md`](../../tactical_mutable_batch_fine_grained_fallback.md)

## Technical specification reference

- [`docs/tech_spec/tech_spec.md`](../../../../../tech_spec.md)

## Step scope

- **Target file (single):** `tests/test_cst_modify_tree_command.py`
- **Action:** modify

## Dependency contract

- **Depends on:** Atomic step A1 (`extend_use_mutable_batch_path_fine_grained_gate.md`) merged; without it, the batch of two `Param` replaces may take the mutable path and diverge from sequential behavior.
- **Downstream:** None.

## Required context

- `build_tree_operations`, `create_tree_from_code`, `get_tree`, `modify_tree` are already used in the same test module near `TestReplaceLeafParamAndName`.
- The tactical example source: function with two parameters on one signature line, renames via `code_lines` that are single-parameter snippets.

## Read first (full paths)

1. `tests/test_cst_modify_tree_command.py` — module header imports; constants `SOURCE_PARAM_AND_NAME`; helpers `_node_id_first_type`; class `TestReplaceLeafParamAndName` (full class).
2. `code_analysis/core/cst_tree/tree_modifier.py` — only if verifying behavior expectations (optional; step A1 should already be done).

## Expected file change

- Add one module-level string constant for the two-parameter function source (name and exact text specified below).
- Add one small helper function to collect ordered `Param` `node_id`s on a given line (signature and behavior specified below).
- Add one new test class containing one test method (names specified below), placed immediately after the `TestReplaceLeafParamAndName` class block to keep leaf-replace tests together.

## Forbidden alternatives

- Do not edit `code_analysis/` production code in this step.
- Do not add optional replace+delete batch tests (out of scope for this atomic step).
- Do not read or write anything under `test_data/`.
- Do not change existing tests except if a trivial import or ordering fix is required for the new symbols (prefer additive-only changes).

## Atomic operations

1. Define a module-level constant **`SOURCE_TWO_PARAMS`** with **exact** text (including final newline preferred to match nearby constants):

   - Line 1: `def f(a: int, b: int) -> None:`
   - Line 2: four spaces + `pass`
   - Ensure the string matches Python 3 syntax and matches the tactical example intent (`f`, parameters `a` and `b`, both annotated `int`, return `None`).

2. Define helper **`_param_node_ids_on_line(tree, line: int) -> list[str]`** (type hints as in project style, `from __future__ import annotations` already at top of file):

   - Build a list of tuples `(node_id, metadata)` from `tree.metadata_map.items()` where `metadata.type == "Param"` and `metadata.start_line == line`.
   - Sort that list by `(metadata.start_col, metadata.end_col)` ascending.
   - Return the list of `node_id` strings in that order.
   - If fewer than two entries, call `pytest.fail` with a message that includes the line number and expected at least two `Param` nodes.

3. Add class **`TestBatchedTwoParamReplacesEquivalence`** with one test method **`test_two_param_replaces_one_modify_matches_sequential`** taking `tmp_path` fixture:

   **Sequential branch:**

   - Build path `str(tmp_path / "seq_two_param.py")`.
   - `tree = create_tree_from_code(path, SOURCE_TWO_PARAMS)`; `tree_id = tree.tree_id`.
   - `ids = _param_node_ids_on_line(tree, line=1)`; assert length is at least 2 using the helper’s guarantee.
   - First replace: `build_tree_operations(tree, [{"action": "replace", "node_id": ids[0], "code_lines": ["x: int"]}])` → must assert `err is None` and exactly one op; `modify_tree(tree_id, ops)`.
   - Reload: `tree_mid = get_tree(tree_id)`; must not be `None`.
   - Second replace: compute `ids_mid = _param_node_ids_on_line(tree_mid, line=1)`; pick the `Param` that still corresponds to the second parameter position by taking **`ids_mid[1]`** (0-based second slot after sort by column) — this mirrors “second parameter on the same line” after the first rename.
   - `build_tree_operations(tree_mid, [{"action": "replace", "node_id": ids_mid[1], "code_lines": ["y: int"]}])` → assert `err is None`; `modify_tree(tree_id, ops)`.
   - `tree_seq = get_tree(tree_id)`; `code_seq = tree_seq.module.code` after asserting tree is not `None`.

   **Batch branch:**

   - New path `str(tmp_path / "batch_two_param.py")`.
   - `tree_b = create_tree_from_code(path_b, SOURCE_TWO_PARAMS)`; `tree_id_b = tree_b.tree_id`.
   - `ids_b = _param_node_ids_on_line(tree_b, line=1)`.
   - Single `build_tree_operations` call with **two** dicts in the list: first replace `ids_b[0]` with `code_lines` `["x: int"]`, second replace `ids_b[1]` with `code_lines` `["y: int"]`; order of dicts matches left-to-right parameter order.
   - Assert `err is None` and `len(ops) == 2`.
   - `modify_tree(tree_id_b, ops)`.
   - `tree_batch = get_tree(tree_id_b)`; `code_batch = tree_batch.module.code`.

   **Assertion:**

   - `assert code_batch == code_seq` (exact string equality). If platform newline normalization is a concern, normalize both sides with `.replace("\r\n", "\n")` only if an existing pattern in this test file already does so for similar comparisons; otherwise prefer exact equality.

4. Do not register new pytest plugins or change `conftest.py`.

## Expected deliverables

- The new constant, helper, class, and method only inside `tests/test_cst_modify_tree_command.py`.

## Mandatory validation

- Full success requires the entire project test suite policy; minimally run the commands in the validation section below until all pass.

## Decision rules

- Use **`code_lines`** with single-element lists for parameter snippets (same pattern as `TestReplaceLeafParamAndName.test_build_ops_replace_param_keeps_node_id_and_body_unchanged`).
- Resolve the second parameter after the first sequential replace via **fresh metadata** on `tree_mid`, not the stale `ids[1]` from the pre-first-replace tree (node identifiers may be reassigned on rebuild).

## Blackstops

- If `ids_mid` has fewer than two elements after the first replace, stop and report (signature or indexer changed); do not weaken the test with a single-Param fallback.
- If batch and sequential sources differ only by whitespace, adjust `SOURCE_TWO_PARAMS` or operations only after confirming A1 is applied; do not skip the assertion.

## Handoff package

- Diff limited to `tests/test_cst_modify_tree_command.py`.
- Validation output summary.

---

## LLAMA-readiness — target file

- **Path:** `tests/test_cst_modify_tree_command.py`
- **Action:** modify
- **Module docstring:** preserve existing file docstring and author block; do not rewrite unless a one-line addition is required to mention batched fine-grained equivalence (optional — omit if not needed).

## Imports (complete list after edit)

The file already imports `pytest`, `CSTModifyTreeCommand`, `build_tree_operations`, `create_tree_from_code`, `get_tree`, `remove_tree`, `modify_tree`, `ErrorResult`, `SuccessResult`. Add **no new imports** unless `pytest` is already sufficient and typing needs no new symbols (helper may use types from existing annotations style: `tree` parameter can stay unannotated only if consistent with `_node_id_first_type`; if the file uses annotations on helpers, annotate `tree` as the same type `create_tree_from_code` returns — inspect `tree_builder` only if the step’s read-first list is insufficient; **preferred:** mirror `_node_id_first_type(tree, node_type: str, *, line: int)` and omit `tree` type hint to avoid extra imports).

## Function / class skeleton

- **Constant:** `SOURCE_TWO_PARAMS: str` (module level).
- **Helper:** `def _param_node_ids_on_line(tree, line: int) -> list[str]:` — one-line docstring: return Param node_ids on `line` sorted left-to-right.
- **Class:** `class TestBatchedTwoParamReplacesEquivalence:`
- **Method:** `def test_two_param_replaces_one_modify_matches_sequential(self, tmp_path):` — docstring one line: batch two Param replaces equals two sequential modifies.

## Error handling

- Use `pytest.fail` inside helper when fewer than two `Param` nodes; use assertions on `build_tree_operations` error being `None`.

## Return value specification

- Helper returns ordered `node_id` strings. Test produces no return; asserts on string equality.

## Edge cases

- If LibCST places both `Param` nodes on line 1 with distinct `start_col`, sorting handles order.
- If future CST layout splits parameters across lines, this test may fail — that is acceptable signal; do not special-case beyond `line=1` for this step.

## Constants and literals

- **Snippet literals:** `"x: int"`, `"y: int"` as the sole `code_lines` entries for the two replaces.
- **Action string in dicts:** `"replace"` (lowercase) to match existing tests.
- **Line number:** `1` for signature line in `SOURCE_TWO_PARAMS`.
- **Filenames:** `seq_two_param.py`, `batch_two_param.py` under `tmp_path`.

## Exact validation commands

```text
black tests/test_cst_modify_tree_command.py
→ "reformatted" OR "already well formatted"

flake8 tests/test_cst_modify_tree_command.py
→ exit code 0

mypy tests/test_cst_modify_tree_command.py
→ "Success: no issues found" (if mypy is configured for tests; if the project excludes tests from mypy, skip mypy for this file only when project convention documented in pyproject — otherwise run mypy as for other test files)

pytest tests/test_cst_modify_tree_command.py::TestBatchedTwoParamReplacesEquivalence -v
→ all PASSED

pytest tests/test_mutable_cst_layer.py tests/test_tree_modifier.py tests/test_cst_modify_tree_command.py -v
→ all PASSED
```

## Test expectations (this step)

- **Test name:** `test_two_param_replaces_one_modify_matches_sequential`
- **Assert:** `code_batch == code_seq` (after optional newline normalization only if mandated by file convention).
- **Indirect assert:** sequential path produces `def f(x: int, y: int)` and body `pass` unchanged semantically in source text.

## Forbidden patterns (LLAMA)

- Do not parametrize this test with unrelated sources.
- Do not use `Any`.
- Do not add `print` debugging.
