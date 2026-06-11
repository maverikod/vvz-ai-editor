<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step index — tactical_annotation_fine_grained_signature_edits

## Reference documents

- Technical specification: `docs/tech_spec/tech_spec.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Parent tactical task: `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_annotation_fine_grained_signature_edits.md`

## Steps (serial)

| ID | File | Target files | Depends on |
|----|------|--------------|------------|
| `annotation_parse_frozenset_and_barrel_exports` | `annotation_parse_frozenset_and_barrel_exports.md` | `tree_modifier_ops_parse.py`, `tree_modifier_ops.py` | — |
| `annotation_replace_and_validate_wiring` | `annotation_replace_and_validate_wiring.md` | `tree_modifier_ops_replace.py`, `tree_modifier_validate.py` | `annotation_parse_frozenset_and_barrel_exports` |
| `annotation_pytest_cst_modify_tree_command` | `annotation_pytest_cst_modify_tree_command.md` | `tests/test_cst_modify_tree_command.py` | `annotation_replace_and_validate_wiring` |

## Executor

`coder_auto`.
