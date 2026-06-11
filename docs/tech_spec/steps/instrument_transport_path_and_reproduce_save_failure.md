<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Instrument Transport Path And Reproduce Save Failure

## Goal

Instrument the database / RPC / queue / transport path around guarded save operations so the next repeated-save failure can be reproduced with precise logging and timings, allowing the system to distinguish where delay or blockage occurs before or during the write path.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Output Artifacts

1. A tactical report describing the code-level instrumentation points added.
2. A tactical report describing the timing/logging fields added for diagnosis.
3. A tactical report reproducing the guarded repeated-save failure sequence with the new diagnostics, or confirming that it no longer reproduces.
4. A tactical report identifying the narrowest next repair target from the new evidence.

## Scope

1. Investigate the code-level transport/write architecture first.
2. Add focused diagnostic logging and timings in the narrowest relevant path.
3. After any server-side code change, explicitly restart the server before revalidation.
4. Reproduce repeated guarded saves on the `vast_srv` harness with strict command tracing.
5. Use the resulting diagnostics to narrow the next fix target.

## Forbidden Approaches

1. Do not broaden this step into unrelated refactors.
2. Do not treat `vast_srv` as the object of repair; it remains a harness.
3. Do not skip restart after server-side code changes.

## Acceptance Criteria

1. Tactical reporting identifies the exact code locations instrumented.
2. Added diagnostics include timing information sufficient to show where delays accumulate.
3. The guarded repeated-save path is re-run after restart with the new diagnostics.
4. Tactical reporting clearly states whether the failure reproduced and what the diagnostics imply about the next narrow repair target.
