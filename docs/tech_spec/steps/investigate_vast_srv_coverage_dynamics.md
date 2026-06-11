<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Investigate vast_srv Coverage Dynamics

## Goal

Determine why the first server-only `vast_srv` analysis pass covered only a small subset of files, and distinguish between delayed catch-up, intentional filtering, and a `code-analysis-server` limitation or defect before the broad fix phase begins.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/analyze_vast_srv_c2_initial_backlog.md`

## Output Artifacts

1. A tactical report confirming entry from the valid `C2` checkpoint.
2. A tactical report describing observed analysis dynamics over time for `vast_srv`.
3. A tactical report classifying the low coverage cause as one of:
   - delayed catch-up still in progress
   - intentional filtering / expected scope limitation
   - server-side limitation
   - server-side defect
4. A tactical report stating whether the campaign may safely open the broad fix phase.

## Scope

1. Treat `C2` as the required entry checkpoint.
2. Continue to use only server-mediated work on `vast_srv`.
3. Route all guarded-path `vast_srv` work only through `tester_ca`.
4. Observe coverage dynamics over time rather than relying on a single snapshot.
5. If a `code-analysis-server` defect is discovered, stop the interrupted flow, repair it, and resume from the last successful checkpoint.

## Forbidden Approaches

1. Do not use direct file reads, direct edits, shell execution, or non-server analysis on `vast_srv`.
2. Do not let `coder_auto` or `tester_auto` touch `vast_srv`.
3. Do not open the broad `vast_srv` fix phase in this step.

## Acceptance Criteria

1. Tactical reporting confirms entry from a valid `C2` checkpoint.
2. Coverage dynamics are observed through repeated server-side evidence, not inference alone.
3. Tactical reporting clearly classifies the cause of low coverage, or narrows it to a small set of exact blockers.
4. If the cause is a `code-analysis-server` defect, the report says so explicitly and the branch stops for repair.
5. Tactical reporting states whether broad `vast_srv` fixes may begin or must remain blocked.
