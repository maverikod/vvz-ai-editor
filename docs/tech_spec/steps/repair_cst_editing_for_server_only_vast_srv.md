<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Repair CST Editing For Server Only vast_srv

## Goal

Repair the `code-analysis-server` CST editing behavior if it blocks safe server-only fixes on `vast_srv`, specifically where scoped replace or partial replace semantics can corrupt or over-replace function bodies, then revalidate the blocked `vast_srv` batch and resume it from the last successful checkpoint.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Output Artifacts

1. A tactical report identifying the concrete CST editing cause or the narrowest remaining blocker.
2. A tactical report describing the repair applied to `code-analysis-server`, if any.
3. A tactical report confirming whether the blocked server-only `vast_srv` edit path is now safe.
4. A tactical report stating whether the interrupted `vast_srv` batch may resume.

## Scope

1. Treat the blocked `vast_srv` Phase 1 batch as the entry condition.
2. Repair only the server-side CST editing issue needed to restore safe server-only fixes.
3. Keep `vast_srv` itself out of direct fix scope except for revalidation of the previously blocked edit path.
4. Revalidate the blocked edit path after repair and then resume the interrupted batch from the last successful checkpoint.

## Forbidden Approaches

1. Do not bypass the blocked edit path with direct file or shell edits on `vast_srv`.
2. Do not let `coder_auto` or `tester_auto` touch guarded `vast_srv` code.
3. Do not resume broad `vast_srv` work until the blocked server-only edit path is revalidated or an exact blocker remains.

## Acceptance Criteria

1. Tactical reporting identifies a concrete CST editing cause or narrows the blocker to a minimal unresolved cause.
2. If code changes are required, they are applied only to the server side and then verified.
3. Tactical reporting confirms whether the previously blocked `vast_srv` edit path is now safe under server-only execution.
4. Tactical reporting clearly states whether the interrupted `vast_srv` batch may resume.
