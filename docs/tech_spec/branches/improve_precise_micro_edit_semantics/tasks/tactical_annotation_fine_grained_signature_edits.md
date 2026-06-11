<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Parent global step: Improve Precise Micro Edit Semantics
-->

# Tactical Task: Fine-grained `Annotation` replace for tiny signature edits

## Purpose

Parameter and return type annotations in function signatures are indexed as LibCST `Annotation` nodes with metadata `type="Annotation"`, but they are not in `FINE_GRAINED_REPLACE_NODE_TYPES`. Clients resolving an annotation `node_id` therefore get promoted to the enclosing `FunctionDef`, and `replace_node` validates replacement text with `parse_code_snippet`, which cannot accept fragments like `: int` or `-> None`. This task adds coherent leaf-level `Annotation` support (constant, dedicated snippet parser, replace and validation branches, tests) so tiny signature-adjustment edits are practical in the server-only workflow without full-function rewrites.

## Parent links

- Technical specification: `docs/tech_spec/tech_spec.md`
- Global implementation plan: `docs/tech_spec/implementation_plan.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Prior related tactical task (Param/Name batch path): `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_mutable_batch_fine_grained_fallback.md`

## Scope

**Included**

- Add `"Annotation"` to `FINE_GRAINED_REPLACE_NODE_TYPES` in `code_analysis/core/cst_tree/tree_modifier_ops_parse.py`.
- Implement `parse_annotation_snippet` in the same module: accept snippets for parameter annotations (e.g. `: int`) and return annotations (e.g. `-> None`), returning a single `libcst.Annotation` using small synthetic parses consistent with existing `parse_param_snippet` / indentation helpers.
- In `code_analysis/core/cst_tree/tree_modifier_ops_replace.py` `replace_node`, branch on `isinstance(node, cst.Annotation)` to build replacement from `parse_annotation_snippet` (mirror `Param` / `Name` structure).
- In `code_analysis/core/cst_tree/tree_modifier_validate.py` `_validate_operation`, validate `Annotation` targets with `parse_annotation_snippet` (not `parse_param_snippet` or bare `parse_code_snippet` for those nodes).
- Update `code_analysis/core/cst_tree/tree_modifier_ops.py` `__all__` if the project exports parsers from that barrel.
- Pytests: `tests/test_cst_modify_tree_command.py` — at least one test replacing a parameter annotation and one replacing a return annotation; optional batched two-annotation equivalence test mirroring `TestBatchedTwoParamReplacesEquivalence`.

**Excluded**

- Broad changes to `compose_cst_module` / `patcher.py`.
- Adding `Decorator` or other types to fine-grained set in this batch.
- Direct edits under `test_data/vast_srv` (harness verification via `tester_ca` only if parent requires after unit proof).

## Boundaries

- Do not change MCP JSON schemas for `cst_modify_tree`.
- Do not weaken statement-level validation for non-fine-grained nodes.
- `coder_auto` / `tester_auto` must not touch guarded `vast_srv` paths.

## Dependencies

- Depends on completed prior batch: mutable-batch gate for Param/Name (`ee5239d` lineage) so `_use_mutable_batch_path` and promotion rules are already aligned for fine-grained types; this task extends the same mechanism to `Annotation`.

## Parallelization note

- Serial with any other task touching `tree_modifier_ops_parse.py`, `tree_modifier_ops_replace.py`, `tree_modifier_validate.py`, and the same test module in the same release window.

## Expected outcome

1. `cst_modify_tree` replace on a `node_id` whose metadata type is `Annotation` replaces only that annotation in the source.
2. Validation accepts only snippets that `parse_annotation_snippet` can turn into a valid `libcst.Annotation`.
3. Batches containing `Annotation` replace/delete use LibCST sequential path via existing `_use_mutable_batch_path` rule extended by the updated frozenset.
4. Targeted pytest passes; one git commit for this logical repair batch.

## Questions / escalation rule

- Escalate to global orchestrator if LibCST cannot represent a required annotation form in one `Annotation` node replacement, or if `AnnAssign` / non-signature `Annotation` contexts need incompatible rules.

## Research evidence (consolidated)

- `FINE_GRAINED_REPLACE_NODE_TYPES` currently `{"Param", "Name"}` only; `Annotation` uses wrong find path and `parse_code_snippet`.
- `_resolve_to_replaceable_node_id` keeps ids only for types in `FINE_GRAINED_REPLACE_NODE_TYPES`.
- `replace_node` uses `parse_expression` for `Name`, `parse_param_snippet` for `Param`, else `parse_code_snippet`.

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` | Extend frozenset; add `parse_annotation_snippet`. |
| modify | `code_analysis/core/cst_tree/tree_modifier_ops_replace.py` | `replace_node` branch for `cst.Annotation`. |
| modify | `code_analysis/core/cst_tree/tree_modifier_validate.py` | Validate Annotation replaces with new parser. |
| modify | `code_analysis/core/cst_tree/tree_modifier_ops.py` | Export new symbol if required by package pattern. |
| modify | `tests/test_cst_modify_tree_command.py` | Tests for param + return annotation replace (and optional batch). |

## Class / function inventory

| symbol | purpose |
|--------|---------|
| `parse_annotation_snippet(snippet: str) -> libcst.Annotation` | Parse `: T` or `-> T`-shaped text into one `Annotation`; raise `ValueError` with clear message on failure. |
| `replace_node` (existing) | Add branch before generic `parse_code_snippet` for `cst.Annotation`. |
| `_validate_operation` (existing) | Route `meta.type == "Annotation"` to `parse_annotation_snippet`. |

Exact signatures of existing functions must match current file contents at implementation time.

## Data structures

- No new public dataclasses; use `libcst.Annotation` and existing `TreeNodeMetadata`.

## Import map

- **parse module:** `libcst as cst`, existing internal helpers (`_normalize_snippet_indentation`, etc.—follow `parse_param_snippet`).
- **replace module:** existing imports; add use of `parse_annotation_snippet`.
- **validate module:** import `parse_annotation_snippet` for Annotation path.

## Error handling map

- `parse_annotation_snippet`: raise `ValueError` for unparseable snippets; callers (`replace_node`, `_validate_operation`) propagate or match existing replace validation behavior for other fine-grained types.

## Config dependency

- none

## Test plan

| file | tests | asserts |
|------|-------|---------|
| `tests/test_cst_modify_tree_command.py` | New class e.g. `TestReplaceLeafAnnotation` | Load tree for `def f(a: int) -> None: pass`; replace param `Annotation` to `: str`; replace return `Annotation` to `-> bool`; source matches expected. |
| same | optional | Two annotation replaces in one `modify_tree` vs sequential, if stable with current sequential rebuild. |

## Concrete examples

1. Source `def g(x: int) -> None:\n    pass`. Replace annotation on `x` with snippet `: str` → `def g(x: str) -> None:`.
2. Same source. Replace return annotation with `-> bool` → `def g(x: int) -> bool:`.

## Algorithm / logic description — `parse_annotation_snippet`

1. Strip and normalize snippet per same rules as `parse_param_snippet` opening.
2. If snippet matches return form (starts with `->`), parse `def __f() <snippet>:\n  pass` and return `FunctionDef.returns` as `Annotation` (unwrap if needed).
3. Else parse parameter-annotation form via synthetic `def __p(x <snippet>): pass` or equivalent and take `Param.annotation`.
4. Return `libcst.Annotation` instance; ensure whitespace/whitespace nodes match LibCST conventions used elsewhere.

(Implementer must align exact stub shapes with LibCST parse behavior.)

## Forbidden approaches

- Adding `"Annotation"` to the frozenset without `parse_annotation_snippet` + replace + validate branches.
- Using `parse_param_snippet` for `Annotation` metadata type in validation.
- Duplicating frozenset literals outside `tree_modifier_ops_parse.py`.

## Implementation record (orchestrator)

- **Repair batch commit:** `e805508` — `fix(cst): fine-grained Annotation replace for signature edits`
- **Verification:** `tester_auto` — `pytest tests/test_cst_modify_tree_command.py tests/test_tree_modifier.py tests/test_mutable_cst_layer.py` → **47 passed** (post-batch).

## Parent resynchronization (2026)

- Global step `improve_precise_micro_edit_semantics.md` requires not stopping after the first micro-edit class and addressing known **signature-adjustment** awkwardness. This tactical task closes the **`Annotation`** leaf path (param/return type fragments) together with prior **`ee5239d`** Param/Name batch semantics.
- **Explicit deferral (not the same bug class as batching/parsing):** first-class **removal** of an annotation via empty `REPLACE` or verified **`DELETE` on `Annotation`** remains optional follow-up if the workflow requires stripping types often; see `researcher_code` audit in orchestrator handoff.

## Correction items

- If annotation removal becomes mandatory for a campaign, add atomic work: validate empty replace for fine-grained `Annotation` or document/test `DELETE` on `Annotation` nodes.
- Otherwise none; implementation record above reflects committed repair.
