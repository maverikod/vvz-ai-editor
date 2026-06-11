<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Repair code_analysis_server Analysis Path

## Goal

Repair the `code-analysis-server` analysis path if the coverage-dynamics investigation indicates server-side limitation, instability, or defect in `comprehensive_analysis`, `update_indexes`, queue progression, or internal socket connectivity, then re-establish the checkpoints needed to safely resume `vast_srv`.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/investigate_vast_srv_coverage_dynamics.md`

## Output Artifacts

1. A tactical report identifying the concrete server-side cause or the narrowest remaining blocker.
2. A tactical report describing the repair applied to `code-analysis-server`, if any.
3. A tactical report confirming revalidation status for `C0`, `C1`, and `C2` after repair.
4. A tactical report stating whether broader `vast_srv` work may resume.

## Scope

1. Treat the coverage-dynamics findings as the entry condition for this step.
2. Repair only the server-side issue needed to restore reliable analysis-path behavior.
3. Keep `vast_srv` itself out of direct fix scope except for revalidation checkpoints after server repair.
4. Re-run `C0`, `C1`, and `C2` after repair to confirm recovery.

## Forbidden Approaches

1. Do not resume broad `vast_srv` fixes before repaired-server revalidation is complete.
2. Do not use direct file, shell, or non-server tooling on `vast_srv`.
3. Do not let `coder_auto` or `tester_auto` touch guarded `vast_srv` code.

## Acceptance Criteria

1. Tactical reporting identifies a concrete server-side cause or narrows the blocker to a minimal unresolved cause.
2. If code changes are required, they are applied only to the server side and then verified.
3. `C0`, `C1`, and `C2` are re-run after the repair, or an exact blocker prevents revalidation.
4. Tactical reporting clearly states whether the broad `vast_srv` phase remains blocked or may resume.
