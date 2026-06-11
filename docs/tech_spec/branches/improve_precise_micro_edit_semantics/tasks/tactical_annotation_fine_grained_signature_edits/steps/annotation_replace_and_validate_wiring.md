<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step: `annotation_replace_and_validate_wiring`

## 1. Executor role

`coder_auto`

## 2. Execution directive

Wire `libcst.Annotation` leaf replacement into `replace_node` and route REPLACE validation for metadata type `Annotation` to `parse_annotation_snippet`, matching existing `Name` and `Param` fine-grained behavior. Depends on `parse_annotation_snippet` and `FINE_GRAINED_REPLACE_NODE_TYPES` from the previous step.

## 3. Parent links (mandatory)

- Technical specification: `docs/tech_spec/tech_spec.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Parent tactical task: `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_annotation_fine_grained_signature_edits.md`

## 4. Step scope

| action | Target file (repo root relative) |
|--------|----------------------------------|
| modify | `code_analysis/core/cst_tree/tree_modifier_ops_replace.py` |
| modify | `code_analysis/core/cst_tree/tree_modifier_validate.py` |

## 5. Dependency contract

- **Depends on:** `annotation_parse_frozenset_and_barrel_exports` completed ( `parse_annotation_snippet` exists; frozenset includes `"Annotation"` ).
- **Blocks:** `annotation_pytest_cst_modify_tree_command` until complete and validated.

## 6. Required context

- `replace_node` already uses `find_leaf_node_in_module_by_position` when `metadata.type in FINE_GRAINED_REPLACE_NODE_TYPES`; adding `"Annotation"` to the frozenset in the previous step already enables leaf resolution for annotation nodes—do not change that condition logic except imports and the new `isinstance` branch.
- `_validate_operation` for REPLACE must call `parse_annotation_snippet` when `meta.type == "Annotation"`, never `parse_param_snippet` or bare `parse_code_snippet` for that type.

## 7. Read first

- `code_analysis/core/cst_tree/tree_modifier_ops_replace.py` (entire file)
- `code_analysis/core/cst_tree/tree_modifier_validate.py` (entire file)
- `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` (for `parse_annotation_snippet` reference only)

## 8. Expected file change

- **`tree_modifier_ops_replace.py`:** Import `parse_annotation_snippet` from `tree_modifier_ops_parse`. In `replace_node`, between the `cst.Param` branch and the fallback `parse_code_snippet` branch, add an `elif isinstance(node, cst.Annotation):` that sets `replacements_list` to a single-element list containing `parse_annotation_snippet(code=new_code)` (same argument pattern as `parse_param_snippet` for `replace_node`—only `code=` is passed because `replace_node` signature is `(module, tree, node_id, new_code: str)`).
- **`tree_modifier_validate.py`:** Import `parse_annotation_snippet` from `tree_modifier_ops` (same pattern as existing `parse_param_snippet` import from `tree_modifier_ops`) **or** from `tree_modifier_ops_parse` if that matches project consistency—**mandatory:** import from the same package path style as `parse_param_snippet` in this file (currently `from .tree_modifier_ops import ...`). Add `parse_annotation_snippet` alongside `parse_param_snippet` in that import. Replace the fine-grained REPLACE validation block so that:
  - `meta.type == "Name"` → unchanged (`cst.parse_expression` on stripped text from `code`/`code_lines`).
  - `meta.type == "Annotation"` → `parse_annotation_snippet(code=operation.code, code_lines=operation.code_lines)`.
  - `meta.type == "Param"` → `parse_param_snippet(code=operation.code, code_lines=operation.code_lines)`.
  - If `meta.type` is in `FINE_GRAINED_REPLACE_NODE_TYPES` but not one of the three above, raise `ValueError` with a message that includes the unexpected type (defensive; should not occur if frozenset matches).

## 9. Forbidden alternatives

- Do not call `parse_code_snippet` for `meta.type == "Annotation"`.
- Do not call `parse_param_snippet` for `Annotation` nodes in validation or replace.
- Do not modify `tree_modifier_ops_parse.py` in this step (parse step is closed).
- Do not change MCP JSON schemas or command handlers.
- Do not add `typing.Any` or bare `except:`.

## 10. Atomic operations

1. Edit imports and `replace_node` branching in `tree_modifier_ops_replace.py`.
2. Edit imports and `_validate_operation` REPLACE branch in `tree_modifier_validate.py`.

## 11. Expected deliverables

- Replacing an `Annotation` CST node uses `parse_annotation_snippet` and produces a single `cst.Annotation` replacement.
- Validation preflight for REPLACE on `Annotation` metadata uses `parse_annotation_snippet` only.

---

## LLAMA-readiness — target A: `tree_modifier_ops_replace.py`

### Target file full path

`code_analysis/core/cst_tree/tree_modifier_ops_replace.py` — **action:** modify.

### File header (module docstring)

Unchanged.

### Imports (complete list after edit)

Add to the `from .tree_modifier_ops_parse import (` block, in alphabetical order with existing parse imports:

- `parse_annotation_snippet`

Full list must be:

- `FINE_GRAINED_REPLACE_NODE_TYPES`
- `parse_annotation_snippet`
- `parse_code_snippet`
- `parse_param_snippet`

### Class/function skeleton — modified function

`replace_node(module: cst.Module, tree: CSTTree, node_id: str, new_code: str) -> cst.Module` — signature unchanged.

### Method logic — `replace_node` (delta only)

After identifying `replacements_list`:

1. Keep existing: `if isinstance(node, cst.Name):` → `replacements_list = [cst.parse_expression(stripped)]` where `stripped = new_code.strip()` (existing code uses `stripped` for Name).
2. Keep existing: `elif isinstance(node, cst.Param):` → `replacements_list = [parse_param_snippet(code=new_code)]`.
3. **New:** `elif isinstance(node, cst.Annotation):` → `replacements_list = [parse_annotation_snippet(code=new_code)]`.
4. Keep existing: `else:` → `parse_code_snippet(new_code)` as today.

**Order constraint:** `Annotation` branch must appear **before** the `else` that calls `parse_code_snippet`, and **after** `Param` (or between `Param` and `else`).

### Error handling — `replace_node`

- Errors from `parse_annotation_snippet` propagate as `ValueError`; no additional catching.

### Return value

- Unchanged: `cst.Module` after successful transform.

### Edge cases

- Empty `new_code` after strip still triggers delete path **before** `isinstance` checks (existing early return); do not change that.

### Constants and literals

- None new.

---

## LLAMA-readiness — target B: `tree_modifier_validate.py`

### Target file full path

`code_analysis/core/cst_tree/tree_modifier_validate.py` — **action:** modify.

### File header (module docstring)

Unchanged.

### Imports (complete list after edit)

Extend `from .tree_modifier_ops import (` to include:

- `parse_annotation_snippet`

Alphabetical order among parse-related imports:

- `FINE_GRAINED_REPLACE_NODE_TYPES`
- `parse_annotation_snippet`
- `parse_code_snippet`
- `parse_param_snippet`

### Class/function skeleton — modified function

`_validate_operation(tree: CSTTree, operation: TreeOperation) -> None` — signature unchanged.

### Method logic — `_validate_operation` REPLACE branch (delta only)

Inside `elif operation.action == TreeOperationType.REPLACE:` after `meta = tree.metadata_map.get(operation.node_id)`, within the existing `try` for syntax validation:

1. If `meta and meta.type in FINE_GRAINED_REPLACE_NODE_TYPES`:
   - If `meta.type == "Name":` keep existing block (build `text` from `code_lines` or `code`, `cst.parse_expression(text.strip())`).
   - Else if `meta.type == "Annotation":` call `parse_annotation_snippet(code=operation.code, code_lines=operation.code_lines)` and do not use the result beyond confirming no exception.
   - Else if `meta.type == "Param":` call `parse_param_snippet(code=operation.code, code_lines=operation.code_lines)`.
   - Else: `raise ValueError(f"Unexpected fine-grained replace type: {meta.type!r}")`.
2. Else (not fine-grained): keep existing `parse_code_snippet(code=operation.code, code_lines=operation.code_lines)`.

### Error handling

- Outer `except Exception as e: raise ValueError(f"Invalid code syntax for replace: {e}") from e` remains; `parse_annotation_snippet` failures must surface through this pattern.

### Edge cases

- `code_lines` vs `code` precedence matches `parse_param_snippet` / `_snippet_as_string` rules inside `parse_annotation_snippet`.

### Constants and literals

- Error prefix string remains `Invalid code syntax for replace:`.

---

## 12. Mandatory validation

From repository root, `.venv` active:

```text
black code_analysis/core/cst_tree/tree_modifier_ops_replace.py code_analysis/core/cst_tree/tree_modifier_validate.py
```
→ Success as in prior step; exit 0.

```text
flake8 code_analysis/core/cst_tree/tree_modifier_ops_replace.py code_analysis/core/cst_tree/tree_modifier_validate.py
```
→ No output; exit 0.

```text
mypy code_analysis/core/cst_tree/tree_modifier_ops_replace.py code_analysis/core/cst_tree/tree_modifier_validate.py
```
→ Success: no issues found.

```text
pytest tests/test_cst_modify_tree_command.py -q
```
→ All tests PASSED.

## 13. Decision rules

- Prefer importing `parse_annotation_snippet` in `tree_modifier_validate.py` from `tree_modifier_ops` to match `parse_param_snippet`; if circular import occurs (unlikely), import from `tree_modifier_ops_parse` instead—only if mypy/import fails, and document the chosen import path in a one-line comment next to the import (allowed).

## 14. Blackstops

- Stop if `tree_modifier_validate` cannot import `parse_annotation_snippet` without cycle; report and try `tree_modifier_ops_parse` as fallback once.
- Stop if pytest fails after two fix attempts.

## 15. Handoff package

- Both files saved; validation passes; ready for pytest step.

## Exact test expectations (this step)

- No new tests in this step; existing suite must pass.

## Forbidden patterns (summary)

- No markdown doc files; no edits to `tests/` in this step.
