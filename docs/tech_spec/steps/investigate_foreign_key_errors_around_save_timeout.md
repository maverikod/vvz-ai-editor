<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Investigate Foreign Key Errors Around Save Timeout

## Goal

Determine what `FOREIGN KEY constraint failed` errors are occurring around the guarded save path, which requests produce them, whether they are causally related to `cst_save_tree` timeout / degradation, and what the narrowest repair target is.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/instrument_transport_path_and_reproduce_save_failure.md`

## Output Artifacts

1. A tactical report mapping the observed `FOREIGN KEY` log lines to specific request types and code paths.
2. A tactical report stating whether those errors are concurrent background noise or part of the failing guarded save sequence.
3. A tactical report identifying the narrowest next repair target if the `FOREIGN KEY` errors materially contribute to timeout or instability.

## Scope

1. Inspect logs around the timeout window and correlate `FOREIGN KEY` failures with request IDs, methods, and higher-level commands.
2. Inspect the relevant code paths that can emit these failures.
3. Distinguish direct causal relation from merely concurrent activity.
4. If a narrow, clearly proven server-side defect is exposed and is in scope, repair it and restart the server before revalidation.

## Forbidden Approaches

1. Do not assume causality from timestamp proximity alone.
2. Do not broaden into unrelated database refactors.
3. Do not skip server restart after any server-side code change.

## Acceptance Criteria

1. The concrete failing request type(s) behind the observed `FOREIGN KEY` errors are identified.
2. The report clearly states whether they are part of the `cst_save_tree` failure path or concurrent background work.
3. The next repair target is narrowed to a specific command/path/constraint problem, or the remaining missing signal is stated precisely.
