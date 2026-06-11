<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Confirm Logical Write Live Path And Resume Vast Srv All Errors

## Goal

First, obtain proof-level live logging that guarded saves now pass through the redesigned logical-write batching path. Then immediately resume the server-only `vast_srv` campaign and continue fixing all discovered project errors using only `code-analysis-server` tooling on `vast_srv`.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
4. `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Output Artifacts

1. A tactical report proving the live guarded save path uses the logical-write batching redesign.
2. A tactical report continuing the `vast_srv` defect-remediation backlog under server-only execution.
3. A tactical report enumerating fixed `vast_srv` errors, remaining confirmed errors, and the next narrow blocker if one appears.

## Scope

1. Use proof-oriented logging and live guarded save reproduction to confirm the logical-write path is active.
2. Resume `vast_srv` work immediately after that confirmation.
3. Fix discovered `vast_srv` errors using only `code-analysis-server` tools for `vast_srv`.
4. If a new `code-analysis-server` defect blocks continuation, stop `vast_srv` work, fix the server defect first, restart the server, and resume from the last successful checkpoint.

## Forbidden Approaches

1. Do not use direct file or shell access on `test_data/vast_srv`.
2. Do not stop only because more work remains if no real blocker or uncertainty exists.
3. Do not treat an unproven suspicion as a blocker; keep moving until a concrete defect or ambiguity is encountered.

## Acceptance Criteria

1. Tactical execution proves the live save path uses the logical-write batching model.
2. Tactical execution continues server-only `vast_srv` remediation after that proof.
3. Confirmed `vast_srv` errors are fixed or classified with a concrete blocker.
4. Any new blocker is reported as a narrow server-side defect or a concrete unresolved project issue, not as a vague pause.
