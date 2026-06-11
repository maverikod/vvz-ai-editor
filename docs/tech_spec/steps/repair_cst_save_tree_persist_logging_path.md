<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Repair cst_save_tree Persist Logging Path

## Goal

Repair the first failing `cst_save_tree` persist/logging path if it destabilizes server-only `vast_srv` work, and add focused diagnostic logging in that path so the next failure can be traced without ambiguity.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Output Artifacts

1. A tactical report identifying the concrete persist/logging cause or the narrowest remaining blocker.
2. A tactical report describing the repair applied to the `code-analysis-server`, if any.
3. A tactical report confirming the diagnostic logging added to the failing path.
4. A tactical report confirming whether the interrupted `vast_srv` save path is revalidated after the repair.

## Scope

1. Treat the first failing `cst_save_tree` path as the primary repair target.
2. Keep the repair narrowly focused on save/persist/logging behavior around that path.
3. Add focused logging in the problematic method/path so future failures capture enough context for diagnosis.
4. Revalidate the blocked guarded `vast_srv` save path after the repair.

## Forbidden Approaches

1. Do not bypass guarded `vast_srv` rules.
2. Do not broaden this step into unrelated infrastructure refactors.
3. Do not treat later `SERVER_NOT_FOUND` as the primary issue until this first failing path is addressed.

## Acceptance Criteria

1. Tactical reporting identifies a concrete persist/logging cause or narrows the blocker to a minimal unresolved cause.
2. If code changes are required, they are applied only to the server side and then verified.
3. Focused logging is added in the failing method/path and described in the report.
4. Tactical reporting confirms whether the blocked `cst_save_tree` path is revalidated after the repair.
