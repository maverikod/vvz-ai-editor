<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic parallel waves — tactical_annotation_fine_grained_signature_edits

## Reference documents

- Technical specification: `docs/tech_spec/tech_spec.md`
- Parent global step: `docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`
- Parent tactical task: `docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_annotation_fine_grained_signature_edits.md`

## Waves

All atomic steps in this tactical task are **serial**. There is **no** parallel wave: each step depends on the previous one completing successfully.

| Wave | Steps | Notes |
|------|-------|--------|
| 1 | `annotation_parse_frozenset_and_barrel_exports` | Must complete first |
| 2 | `annotation_replace_and_validate_wiring` | Depends on wave 1 |
| 3 | `annotation_pytest_cst_modify_tree_command` | Depends on wave 2 |

## Executor

`coder_auto` (per step files).
