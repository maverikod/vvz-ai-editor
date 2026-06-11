<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Repair comprehensive_analysis Summary Counting

## Goal

Repair the `code-analysis-server` logic behind `comprehensive_analysis` coverage summaries if the analysis path is operational but the reported `files_analyzed` / `files_skipped` values remain implausible, then revalidate summary reliability before broad `vast_srv` work resumes.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/repair_code_analysis_server_analysis_path.md`

## Output Artifacts

1. A tactical report identifying the concrete cause of the summary/counting anomaly or the narrowest remaining blocker.
2. A tactical report describing the repair applied to `code-analysis-server`, if any.
3. A tactical report confirming whether `comprehensive_analysis` summary values are reliable after repair.
4. A tactical report stating whether the broad `vast_srv` fix phase may resume.

## Scope

1. Treat the repaired analysis-path state as the entry condition.
2. Investigate only the server-side summary/counting anomaly needed to restore trust in coverage metrics.
3. Keep `vast_srv` itself out of direct fix scope except for revalidation runs after server repair.
4. Revalidate summary reliability using server-mediated evidence before reopening broad `vast_srv` work.

## Forbidden Approaches

1. Do not resume broad `vast_srv` fixes before summary reliability is revalidated.
2. Do not use direct file, shell, or non-server tooling on `vast_srv`.
3. Do not let `coder_auto` or `tester_auto` touch guarded `vast_srv` code.

## Acceptance Criteria

1. Tactical reporting identifies a concrete summary/counting cause or narrows the blocker to a minimal unresolved cause.
2. If code changes are required, they are applied only to the server side and then verified.
3. Revalidation shows whether `comprehensive_analysis` summary values are now trustworthy, or an exact blocker remains.
4. Tactical reporting clearly states whether the broad `vast_srv` phase remains blocked or may resume.
