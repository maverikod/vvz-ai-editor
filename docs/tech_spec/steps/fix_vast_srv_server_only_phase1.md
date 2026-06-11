<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Fix vast_srv Server Only Phase 1

## Goal

Begin the broad `vast_srv` fix phase under strict server-only execution, addressing the validated backlog in priority order: explicit errors first, then unfinished code, then logical duplicates.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/analyze_vast_srv_c2_initial_backlog.md`
4. `docs/tech_spec/steps/repair_comprehensive_analysis_summary_counting.md`

## Output Artifacts

1. A tactical report confirming the valid entry condition from the repaired and revalidated analysis workflow.
2. A tactical report describing the first completed fix batch on `vast_srv`.
3. A tactical report stating what backlog items remain after that batch and what should be fixed next.
4. A tactical report confirming whether the server-only workflow remained intact throughout the batch.

## Scope

1. Enter only after coverage summary reliability has been revalidated.
2. Use only server-mediated access for `vast_srv`.
3. Route all guarded-path `vast_srv` work only through `tester_ca`.
4. Fix backlog items in this order:
   - explicit errors
   - unfinished code
   - logical duplicates
5. Prefer the first batch to reduce the highest-impact explicit errors without opening uncontrolled refactors.
6. If a `code-analysis-server` defect appears, stop the interrupted flow, repair it, and resume from the last successful checkpoint.

## Forbidden Approaches

1. Do not use direct file reads, direct edits, shell execution, or non-server analysis on `vast_srv`.
2. Do not let `coder_auto` or `tester_auto` touch `vast_srv`.
3. Do not jump ahead to unfinished code or duplicate cleanup if unresolved higher-priority explicit errors remain in the selected batch scope unless the tactical report justifies the dependency.

## Acceptance Criteria

1. Tactical reporting confirms that the repaired analysis workflow is a valid entry condition.
2. All `vast_srv` work in this step is executed only through `code-analysis-server`, using `tester_ca` where required.
3. At least one concrete fix batch is completed against the validated backlog.
4. Tactical reporting clearly distinguishes fixed items, remaining items, and next priority items.
5. Tactical reporting states whether the server-only workflow remained intact and whether the next fix batch may proceed.
