<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic parallel waves — tactical_mutable_batch_fine_grained_fallback

## Reference

- Technical specification: [`docs/tech_spec/tech_spec.md`](../../../../../tech_spec.md)
- Parent global step: [`docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`](../../../../../steps/improve_precise_micro_edit_semantics.md)
- Parent tactical task: [`../../tactical_mutable_batch_fine_grained_fallback.md`](../../tactical_mutable_batch_fine_grained_fallback.md)

## Waves

| Wave | Step files | Parallel within wave | Notes |
|------|------------|----------------------|-------|
| 1 | `extend_use_mutable_batch_path_fine_grained_gate.md` | n/a (single step) | Must complete before wave 2 |
| 2 | `test_batched_two_param_replaces_equivalence.md` | n/a (single step) | Depends on wave 1 implementation |

## Summary

Steps are **strictly sequential**: production gating in `tree_modifier.py` first, then pytest additions. They must **not** run in parallel with each other.

## Cross-task parallelization

Per the parent tactical task, this task may run in parallel with **other tactical tasks** that do not edit `code_analysis/core/cst_tree/tree_modifier.py` or `tests/test_cst_modify_tree_command.py`.
