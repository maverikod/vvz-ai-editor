<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step index — tactical_mutable_batch_fine_grained_fallback

## Reference

- Technical specification: [`docs/tech_spec/tech_spec.md`](../../../../../tech_spec.md)
- Parent global step: [`docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`](../../../../../steps/improve_precise_micro_edit_semantics.md)
- Parent tactical task: [`../../tactical_mutable_batch_fine_grained_fallback.md`](../../tactical_mutable_batch_fine_grained_fallback.md)

## Goal (from tactical task)

Force the LibCST sequential `modify_tree` path whenever any batched `REPLACE` or `DELETE` targets a node whose metadata `type` is in `FINE_GRAINED_REPLACE_NODE_TYPES`, and prove batched two-`Param` replaces match sequential application.

## Steps

| ID | File | Target path | Depends on |
|----|------|-------------|------------|
| A1 | `extend_use_mutable_batch_path_fine_grained_gate.md` | `code_analysis/core/cst_tree/tree_modifier.py` | — |
| A2 | `test_batched_two_param_replaces_equivalence.md` | `tests/test_cst_modify_tree_command.py` | A1 |

## Execution order

A1 → A2 (see `parallel_waves.md`).
