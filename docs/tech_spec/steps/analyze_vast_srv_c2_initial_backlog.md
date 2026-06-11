<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Analyze vast_srv C2 Initial Backlog

## Goal

After successful completion of `C1`, perform the first server-only analysis pass on `vast_srv` and produce the first validated defect backlog grouped into explicit errors, unfinished code, and logical duplicates.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/begin_vast_srv_c1_identity_and_access.md`

## Output Artifacts

1. A tactical report confirming that `C1` is the current valid entry checkpoint.
2. A tactical report listing the first validated backlog for `vast_srv` under these categories:
   - explicit errors
   - unfinished code
   - logical duplicates
3. A tactical report stating whether deeper fix execution may begin and what the first fix priority order should be.

## Scope

1. Treat `C1` as the required entry checkpoint.
2. Use only server-mediated analysis on `vast_srv`.
3. Route all guarded-path `vast_srv` work only through `tester_ca`.
4. Build the first validated backlog from real server outputs, not guesswork.
5. Stop immediately if a `code-analysis-server` defect appears, repair it, and resume from the last successful checkpoint.

## Forbidden Approaches

1. Do not use direct file reads, direct edits, shell execution, or non-server analysis on `vast_srv`.
2. Do not let `coder_auto` or `tester_auto` touch `vast_srv`.
3. Do not start fixing `vast_srv` code in this step unless a server defect forces repair of `code-analysis-server` itself.

## Acceptance Criteria

1. Tactical reporting confirms entry from a valid `C1` checkpoint.
2. All `vast_srv` analysis in this step is performed only through `code-analysis-server`, using `tester_ca` where required.
3. The backlog contains concrete, evidence-based items in each applicable category, or explicitly states that a category currently has no validated items.
4. Tactical reporting identifies the first fix priority order without beginning unrestricted deeper execution.
5. Tactical reporting states whether the campaign may proceed to the fix phase.
