<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Parent global step: Improve Precise Micro Edit Semantics
-->

# Tactical Task: Mutable-batch fallback for fine-grained Param/Name edits

## Purpose

After the CST leaf replace repair (Param/Name promotion and LibCST `replace_node` path), multi-operation `cst_modify_tree` batches still route through the mutable CST batch path (`_use_mutable_batch_path`), which applies replacements via statement-level parsing and does not preserve fine-grained Param/Name semantics. This task forces the LibCST sequential path whenever any replace or delete targets a node whose CST metadata type is in `FINE_GRAINED_REPLACE_NODE_TYPES`, so batched micro-edits remain safe and equivalent to separate single-op calls.

## Parent links

- Technical specification: `docs/tech_spec/tech_spec.md`
- Global implementation plan: `docs/tech_spec/implementation_plan.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Prior CST repair context: `docs/tech_spec/steps/repair_cst_editing_for_server_only_vast_srv.md`
- Prior tactical repair inventory: `docs/tech_spec/branches/repair_cst_editing_for_server_only_vast_srv/tasks/tactical_cst_leaf_replace_repair.md`

## Scope

**Included**

- Change decision logic in `code_analysis/core/cst_tree/tree_modifier.py` so `_use_mutable_batch_path` returns `False` when any `REPLACE` or `DELETE` operation targets a node whose type (from the tree metadata map) is in `FINE_GRAINED_REPLACE_NODE_TYPES` defined in `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` (import the constant; do not duplicate the frozenset literal).
- Add pytest coverage in `tests/test_cst_modify_tree_command.py` proving batched fine-grained replaces (two `Param` or `Name` replaces in one `modify_tree`) match two sequential calls; optional batch mixing replace+delete on a `Param` if the public API allows.

**Excluded**

- Reimplementing `replace_node` inside `code_analysis/core/mutable_cst/edits.py`
- Expanding `FINE_GRAINED_REPLACE_NODE_TYPES` to `Annotation` (addressed in `tactical_annotation_fine_grained_signature_edits.md`), `Decorator`, or other kinds (separate tactical task)
- `compose_cst_module` / `patcher.py` changes
- Any direct reads or writes under `test_data/vast_srv` (verification harness only via `tester_ca` if explicitly required after unit proof)

## Boundaries

- Do not change MCP command contracts or request schemas for `cst_modify_tree`.
- Do not weaken validation in `tree_modifier_validate.py` except where required by the new path selection (should not be needed).
- Do not touch `test_data/vast_srv` with `coder_auto` or `tester_auto`.

## Dependencies

- none (builds on completed repair in `repair_cst_editing_for_server_only_vast_srv`)

## Parallelization note

- May run in parallel with other tactical tasks that do not edit the same files; this task edits `tree_modifier.py` and one test module—serialize with any sibling that touches those paths.

## Expected outcome

1. Batches containing only fine-grained targets use the LibCST sequential path; behavior matches single-op leaf tests.
2. Batches with only statement-level replaces (no fine-grained targets) still use the mutable batch path when other `_use_mutable_batch_path` conditions are met.
3. `pytest` for `tests/test_cst_modify_tree_command.py` passes; no regressions in related CST tree tests if run in CI scope.
4. One git commit records this logical repair batch (full message body describing mutable-batch fallback for Param/Name).

## Correction items

- none at task open; add here if parent global step changes path selection rules.

## Questions / escalation rule

- Escalate to global orchestrator if `tech_spec.md` or global step forbids LibCST sequential path for performance, or if `FINE_GRAINED_REPLACE_NODE_TYPES` ownership must move to a new module.

## File inventory

| action  | path | purpose |
|---------|------|---------|
| modify | `code_analysis/core/cst_tree/tree_modifier.py` | Import `FINE_GRAINED_REPLACE_NODE_TYPES`; extend `_use_mutable_batch_path` to return `False` when any `REPLACE`/`DELETE` op’s target `node_id` has metadata type in that set. |
| modify | `tests/test_cst_modify_tree_command.py` | Add tests for batched fine-grained replace (and optional delete) vs sequential equivalence. |

## Class / function inventory

| dotted path | base | purpose | public methods (this task) |
|-------------|------|---------|----------------------------|
| `code_analysis.core.cst_tree.tree_modifier` (module-level helpers / class hosting `_use_mutable_batch_path`) | n/a | Tree modification orchestration | `_use_mutable_batch_path(operations, ...) -> bool` — extend condition as specified; preserve existing triggers for `REPLACE_RANGE`/`MOVE` and multi-op rules. Exact parameter list must be taken from the current file at implementation time. |

(Implementer: open `tree_modifier.py` and mirror existing signature and call sites exactly.)

## Data structures

- No new dataclasses; use existing `TreeOperation` and tree metadata map entries as today.

## Import map

**`tree_modifier.py`**

- `from code_analysis.core.cst_tree.tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES` (or from `tree_modifier_ops` if that module re-exports it without circular import—choose the same import style as sibling imports in this file).

**`tests/test_cst_modify_tree_command.py`**

- Existing imports plus any fixtures/helpers already used by `TestReplaceLeafParamAndName`.

## Error handling map

- No new exception types. If a `node_id` is missing from `metadata_map`, follow existing `_use_mutable_batch_path` behavior for unknown nodes (do not crash; prefer conservative path: if unknown, do not force LibCST path unless consistent with existing code for missing metadata).

## Config dependency

- none

## Test plan

| test file | test name pattern | asserts |
|-----------|-------------------|---------|
| `tests/test_cst_modify_tree_command.py` | new class or methods under leaf-replace suite | Two `replace` ops on two distinct `Param` or `Name` node IDs in one `modify_tree` produce the same source as two sequential `modify_tree` calls (or one combined save). |
| same | optional | Replace+delete batch involving `Param` if supported without schema change. |

Use existing patterns from `TestReplaceLeafParamAndName` for tree load, node resolution, and save.

## Concrete examples

1. **Input:** Function `def f(a: int, b: int) -> None: pass` loaded; `node_id` for first `Param` (`a`) and second `Param` (`b`). **Operation:** single `modify_tree` with two `replace` ops renaming parameters to `x` and `y` via `code_lines` snippets that are single `Param` each. **Expected:** Source becomes `def f(x: int, y: int) -> None: pass` and matches applying two separate replaces in sequence.

## Algorithm / logic description

1. At the start of `_use_mutable_batch_path` (after existing fast exits), iterate `operations`.
2. For each op with action `REPLACE` or `DELETE`, resolve `node_id` from the op (same field names as used elsewhere in this function).
3. Look up `tree.metadata_map.get(node_id)`; read `type` (or equivalent attribute used elsewhere for CST node type string).
4. If `type in FINE_GRAINED_REPLACE_NODE_TYPES`, return `False` immediately (use LibCST sequential path).
5. Otherwise continue existing logic unchanged.

## Forbidden approaches

- Duplicating the `{"Param", "Name"}` frozenset in `tree_modifier.py`
- Editing `test_data/vast_srv` with non-`tester_ca` agents
- Broad refactors of `mutable_cst` or `tree_modifier_ops_replace.py` beyond what is required to import the constant and gate the path

## Research evidence (consolidated)

- Fine-grained set: `FINE_GRAINED_REPLACE_NODE_TYPES` in `tree_modifier_ops_parse.py`.
- Batch path: `_use_mutable_batch_path` in `tree_modifier.py`; mutable apply uses `_replace_node_source` / `parse_code_snippet` without leaf logic in `mutable_cst/edits.py`.
- Prior single-op tests: `TestReplaceLeafParamAndName` in `test_cst_modify_tree_command.py`.
