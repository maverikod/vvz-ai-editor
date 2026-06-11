<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step: `annotation_parse_frozenset_and_barrel_exports`

## 1. Executor role

`coder_auto`

## 2. Execution directive

Implement fine-grained `Annotation` support at the parse layer: extend `FINE_GRAINED_REPLACE_NODE_TYPES`, add `parse_annotation_snippet`, and re-export the new symbol from `tree_modifier_ops.py`. Do not modify replace, validate, or tests in this step.

## 3. Parent links (mandatory)

- Technical specification: `docs/tech_spec/tech_spec.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Parent tactical task: `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_annotation_fine_grained_signature_edits.md`

## 4. Step scope

This handoff intentionally updates **two** files (parse module + barrel) as one serial step per parent planner instruction “parse + frozenset + exports”:

| action | Target file (repo root relative) |
|--------|----------------------------------|
| modify | `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` |
| modify | `code_analysis/core/cst_tree/tree_modifier_ops.py` |

## 5. Dependency contract

- **Depends on:** none (first serial step).
- **Blocks:** `annotation_replace_and_validate_wiring` until complete and validated.

## 6. Required context

- Leaf-level `Annotation` nodes must parse `: T` and `-> T` fragments into a single `libcst.Annotation`, matching the tactical task algorithm.
- `FINE_GRAINED_REPLACE_NODE_TYPES` must remain a **single** frozenset literal in `tree_modifier_ops_parse.py` (no duplicated literals elsewhere).

## 7. Read first

- `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` (entire file)
- `code_analysis/core/cst_tree/tree_modifier_ops.py` (entire file)

## 8. Expected file change

- **`tree_modifier_ops_parse.py`:** Add `"Annotation"` to `FINE_GRAINED_REPLACE_NODE_TYPES`. Add public function `parse_annotation_snippet` with behavior specified below. Preserve existing module docstring and existing functions unchanged except the frozenset line and the new function block.
- **`tree_modifier_ops.py`:** Import `parse_annotation_snippet` from `tree_modifier_ops_parse`, add it to `__all__` immediately before `"parse_code_snippet"` so the `parse_*` names stay alphabetically ordered (`parse_annotation_snippet`, `parse_code_snippet`, `parse_code_snippet_or_comment`, `parse_param_snippet`).

## 9. Forbidden alternatives

- Do not add `parse_annotation_snippet` to any file other than `tree_modifier_ops_parse.py` and the barrel import/`__all__` in `tree_modifier_ops.py`.
- Do not duplicate the frozenset contents string in another module.
- Do not change `replace_node`, `_validate_operation`, or any test file in this step.
- Do not use `parse_param_snippet` to validate or build `Annotation` nodes.
- Do not add `typing.Any` or bare `except:`.

## 10. Atomic operations

1. In `tree_modifier_ops_parse.py`, set `FINE_GRAINED_REPLACE_NODE_TYPES = frozenset({"Annotation", "Name", "Param"})` (set membership must include these three strings exactly).
2. In the same file, append `parse_annotation_snippet` after `parse_param_snippet` (or immediately before `parse_code_snippet` if that matches local organization—prefer grouping with other snippet parsers near `parse_param_snippet`).
3. In `tree_modifier_ops.py`, add the import and `__all__` entry as in section 8.

## 11. Expected deliverables

- Updated frozenset including `"Annotation"`.
- Fully implemented `parse_annotation_snippet` per sections below (signatures, algorithms, errors).
- Barrel re-export so downstream code can import `parse_annotation_snippet` from `tree_modifier_ops` if needed.

---

## LLAMA-readiness — target A: `tree_modifier_ops_parse.py`

### Target file full path

`code_analysis/core/cst_tree/tree_modifier_ops_parse.py` — **action:** modify.

### File header (module docstring)

Keep the existing module docstring exactly as it is today (do not replace the file header).

### Imports (complete list for new/edited symbols in this file)

Use the file’s existing imports. If `Tuple` is unused, do not add it. Required minimum remains:

- `from __future__ import annotations`
- `from typing import List, Optional, Union, cast`
- `import libcst as cst`

No new imports are required unless the implementation needs them (e.g. none beyond the above for the described algorithm).

### Class/function skeleton — new symbol only

```text
def parse_annotation_snippet(
    code: Optional[str] = None,
    code_lines: Optional[List[str]] = None,
) -> cst.Annotation:
    """Parse a parameter or return annotation snippet for leaf Annotation replacement."""
```

### Method logic — `parse_annotation_snippet` (numbered algorithm)

1. Call `_snippet_as_string(code, code_lines)` → `raw` (`str`). This enforces mutual exclusivity of `code` and `code_lines` the same way as `parse_param_snippet`.
2. If `raw.strip()` is empty, raise `ValueError` with message: `Annotation replacement code is empty`.
3. Set `normalized = _normalize_snippet_indentation(raw)` (same as `parse_param_snippet`).
4. Set `text = normalized.strip()`.
5. **Return form:** If `text.startswith("->")`:
   - Build `wrapped = f"def __ann_return__(){text}:\n    pass\n"` (exactly one blank line structure as needed so `cst.parse_module(wrapped)` succeeds; use four spaces before `pass` on its own line).
   - Call `cst.parse_module(wrapped)` inside `try`; on `cst.ParserSyntaxError` as `e`, raise `ValueError(f"Invalid return annotation syntax: {e}")` from `e`.
   - If `mod.body` is empty or the first node is not `cst.FunctionDef`, raise `ValueError("Return annotation snippet did not parse as a function return annotation")`.
   - Let `fd = mod.body[0]` (cast or `isinstance` check). Read `fd.returns`.
   - If `fd.returns` is `None` or not an instance of `cst.Annotation`, raise `ValueError("Parsed function has no Annotation for returns")`.
   - Return `fd.returns` (the `cst.Annotation` node).
6. **Parameter annotation form:** Else (does not start with `->`):
   - Build `wrapped = f"def __ann_param__(x{text}):\n    pass\n"` so that when `text` is like `: int`, the parameter list becomes `x: int` (no extra space requirement beyond valid Python).
   - Parse with `cst.parse_module(wrapped)`; on `cst.ParserSyntaxError` as `e`, raise `ValueError(f"Invalid parameter annotation syntax: {e}")` from `e`.
   - If `mod.body` is empty or first node is not `cst.FunctionDef`, raise `ValueError("Parameter annotation snippet did not parse as a function parameter")`.
   - Let `fd = mod.body[0]`. From `fd.params.params`, require at least one `cst.Param`; take `param0 = fd.params.params[0]`.
   - If `param0.annotation` is `None` or not `cst.Annotation`, raise `ValueError("Parsed parameter has no Annotation")`.
   - Return `param0.annotation`.

### Error handling — `parse_annotation_snippet`

- Raise `ValueError` for empty input, parse failures, or structure mismatch (messages as above or same intent with clear text).
- Catch `cst.ParserSyntaxError` only at parse boundaries and re-raise as `ValueError` with context; do not swallow stack traces (`from e`).

### Return value — `parse_annotation_snippet`

- Returns one `libcst.Annotation` instance suitable for plugging into `replace_node`’s replacement list in a later step.

### Edge cases — `parse_annotation_snippet`

- Empty or whitespace-only input after strip → `ValueError("Annotation replacement code is empty")`.
- Return snippet with leading spaces before `->` removed by strip; must still detect `startswith("->")` after `text = normalized.strip()`.
- Parameter snippet must work when `text` is `: int`, `: str`, etc.
- Return snippet must work when `text` is `-> None`, `-> bool`, etc.

### Constants and literals

- Synthetic function names: `__ann_return__`, `__ann_param__` (exact strings).
- Frozenset must include exactly these string elements: `"Annotation"`, `"Name"`, `"Param"`.

---

## LLAMA-readiness — target B: `tree_modifier_ops.py`

### Target file full path

`code_analysis/core/cst_tree/tree_modifier_ops.py` — **action:** modify.

### File header (module docstring)

Keep the existing module docstring unchanged.

### Imports (complete list after edit)

The `from .tree_modifier_ops_parse import (...)` block must include, in addition to existing names:

- `parse_annotation_snippet`

Full import block shape (alphabetical within the parse import group):

- `from .tree_modifier_ops_parse import (`  
  `FINE_GRAINED_REPLACE_NODE_TYPES,`  
  `parse_annotation_snippet,`  
  `parse_code_snippet,`  
  `parse_code_snippet_or_comment,`  
  `parse_param_snippet,`  
  `)`

### `__all__`

Insert the string `"parse_annotation_snippet"` immediately before `"parse_code_snippet"` so all `parse_*` entries read alphabetically.

### Class/function skeleton

No new classes or functions; only import and `__all__` edits.

### Error handling

None for this file.

### Edge cases

None.

---

## 12. Mandatory validation

Run from repository root with `.venv` activated (`docs/PROJECT_RULES.md` CR-005).

Exact commands and expected success patterns:

```text
black code_analysis/core/cst_tree/tree_modifier_ops_parse.py code_analysis/core/cst_tree/tree_modifier_ops.py
```
→ Output contains `reformatted` or `unchanged` / “already well formatted” for each file; exit code 0.

```text
flake8 code_analysis/core/cst_tree/tree_modifier_ops_parse.py code_analysis/core/cst_tree/tree_modifier_ops.py
```
→ No output; exit code 0.

```text
mypy code_analysis/core/cst_tree/tree_modifier_ops_parse.py code_analysis/core/cst_tree/tree_modifier_ops.py
```
→ `Success: no issues found` (or project-equivalent).

```text
pytest tests/test_cst_modify_tree_command.py -q
```
→ All tests **PASSED** (no new failures; annotation-specific tests may not exist yet).

## 13. Decision rules

- If `cst.parse_module` rejects the chosen wrapper strings, adjust only the wrapper string literals (still using `__ann_return__` / `__ann_param__`) until parse succeeds for the examples in section 14; do not change the public algorithm beyond fixing whitespace in wrappers.

## 14. Blackstops

- Stop and escalate if `FINE_GRAINED_REPLACE_NODE_TYPES` is required elsewhere as a duplicate literal—must remain single source in `tree_modifier_ops_parse.py` only.
- Stop if mypy or pytest fails after two corrective attempts; report the failing command output.

## 15. Handoff package

- Both modified files saved.
- Validation commands in section 12 all pass.
- Ready for `annotation_replace_and_validate_wiring`.

## Exact test expectations (this step)

- No new tests required; existing `tests/test_cst_modify_tree_command.py` must remain green.

## Forbidden patterns (summary)

- No implementation code in this markdown file beyond signatures and algorithms above.
- No edits outside the two listed files.
