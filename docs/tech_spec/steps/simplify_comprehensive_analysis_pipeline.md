<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Simplify comprehensive_analysis Pipeline

## Goal

Investigate and simplify the `comprehensive_analysis` pipeline so quality analysis becomes faster, more reliable, and easier to explain, while preserving server-managed outputs and using `vast_srv` as a verification harness.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/repair_comprehensive_analysis_summary_counting.md`

## Output Artifacts

1. A tactical report identifying the dominant complexity or latency sources in the current pipeline.
2. A tactical report describing the server-side simplification or acceleration batch or batches applied.
3. A tactical report comparing pre/post behavior in terms of runtime, reliability, or explainability.
4. A tactical report listing any remaining exact performance or architectural blockers.

## Scope

1. Focus on the server-side `comprehensive_analysis` pipeline, not on broad `vast_srv` product fixes.
2. Prefer simpler execution architecture where quality tools can be run and aggregated more transparently.
3. Use `vast_srv` only as a verification harness where needed.
4. Commit every logical repair batch before continuing to the next one.

## Forbidden Approaches

1. Do not bypass server-only `vast_srv` rules.
2. Do not turn this step into an uncontrolled rewrite of unrelated server subsystems.
3. Do not continue to another logical repair batch without a commit for the previous batch.

## Acceptance Criteria

1. Tactical reporting identifies a concrete complexity or latency source in `comprehensive_analysis`.
2. At least one logical server-side simplification batch is implemented and committed.
3. Tactical reporting verifies whether the pipeline is now faster, more reliable, or more explainable in the targeted area.
4. Any remaining blockers are reported explicitly.
