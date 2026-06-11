<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Improve Precise Micro Edit Semantics

## Goal

Improve `code-analysis-server` micro-edit semantics so small, safe server-only changes to signatures and other tiny CST targets can be applied without over-replacing larger structures or forcing risky full-function rewrites.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/repair_cst_editing_for_server_only_vast_srv.md`

## Output Artifacts

1. A tactical report identifying the remaining micro-edit limitations after the CST repair already completed.
2. A tactical report describing the server-side repair batch or batches applied.
3. A tactical report confirming whether the target class of tiny edits is now safe and practical.
4. A tactical report listing any remaining exact limitations.

## Scope

1. Focus on server-side edit semantics, not on broad `vast_srv` feature work.
2. Use `vast_srv` only as a verification harness where needed.
3. Improve bounded micro-edit cases such as tiny signature adjustments and other small CST replacements that currently remain impractical.
4. Commit every logical repair batch before continuing to the next one.
5. Do not stop after the first repaired micro-edit class if a closely related remaining tiny-edit blocker is already known from the current workflow.

## Forbidden Approaches

1. Do not bypass server-only `vast_srv` rules.
2. Do not broaden this step into general refactoring of the CST subsystem.
3. Do not continue to another logical repair batch without a commit for the previous batch.

## Acceptance Criteria

1. Tactical reporting identifies a concrete class of remaining micro-edit limitations.
2. At least one logical server-side repair batch is implemented and committed.
3. Tactical reporting verifies whether the targeted micro-edit classes needed by the current server-only workflow are now safe/practical, including tiny signature-adjustment cases if they are still known blockers.
4. The branch is not considered complete while a known current-workflow tiny-edit blocker remains unaddressed without an explicit global decision to defer it.
5. Any remaining gaps are reported explicitly only after exhausting the currently known practical blocker set for this workflow.
