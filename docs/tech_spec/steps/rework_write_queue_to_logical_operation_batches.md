<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Rework Write Queue To Logical Operation Batches

## Goal

Eliminate repeated-save degradation caused by write-operation interleaving on the serialized SQLite path by changing the unit of scheduling from individual write RPC requests to full logical write operations, where even a single write statement is treated as a batch/job.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/instrument_transport_path_and_reproduce_save_failure.md`
4. `docs/tech_spec/steps/investigate_foreign_key_errors_around_save_timeout.md`

## Output Artifacts

1. A tactical design/repair report describing the current write-scheduling model and the target logical-operation batching model.
2. A tactical implementation batch that prevents other writes from interleaving inside one guarded logical save operation.
3. Tactical validation proving whether repeated guarded saves remain stable under background worker activity after the redesign.

## Scope

1. Treat each write operation as a scheduled batch/job even when it contains only one SQL statement.
2. Preserve the serialized SQLite execution model, but change the queueing boundary from individual write RPC calls to full logical write operations.
3. Keep background worker writes from interleaving with the begin/execute/commit sequence of a guarded save.
4. Restart the server after any server-side code change before revalidation.

## Forbidden Approaches

1. Do not solve this step primarily with priority heuristics if the root issue is queue unit mismatch.
2. Do not broaden into unrelated database or worker refactors.
3. Do not resume broad `vast_srv` continuation until the repeated guarded save path is revalidated.

## Acceptance Criteria

1. Tactical reporting explains the current interleaving defect in terms of queue unit mismatch.
2. The repair changes the effective unit of write scheduling to logical write operations/batches.
3. Validation shows that guarded repeated saves no longer fail because another write interleaves before commit.
4. Tactical reporting states any remaining residual blocker separately from the original interleaving defect.
