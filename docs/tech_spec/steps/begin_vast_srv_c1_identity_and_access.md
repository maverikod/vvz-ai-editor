<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Begin vast_srv C1 Identity And Access

## Goal

After live confirmation of `C0`, begin checkpoint `C1` for `vast_srv` by resolving the exact project identity and proving server-only access to the project through `code-analysis-server`, with all guarded-path work executed only through `tester_ca`.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/restore_code_analysis_server_registration.md`

## Output Artifacts

1. A tactical report confirming whether `C0` was revalidated successfully in the current environment.
2. A tactical report identifying `vast_srv` project identity, watch context, and server-visible access path, or naming the exact blocker.
3. A tactical report confirming whether the campaign may advance from `C1` to deeper `vast_srv` analysis.

## Scope

1. Revalidate `C0` in the current environment through `mcp-proxy`.
2. If `C0` fails, stop and repair the blocking defect before any `vast_srv` work continues.
3. If `C0` passes, use only server-mediated access for `vast_srv`.
4. Resolve the exact `vast_srv` project identity and its server-visible context.
5. Prove minimal read/access capability for `vast_srv` through `code-analysis-server`.
6. Report whether deeper `vast_srv` analysis may begin.

## Forbidden Approaches

1. Do not use any direct file, shell, or non-server tooling to work with `vast_srv`.
2. Do not let `coder_auto` or `tester_auto` touch `vast_srv`.
3. Do not proceed past `C1` if `C0` is not revalidated in the current environment.

## Acceptance Criteria

1. Tactical verification re-confirms `C0` through live `mcp-proxy` evidence in the current environment, or reports the exact blocker.
2. Any `vast_srv` access is handled only through `tester_ca` and `code-analysis-server`.
3. Tactical reporting identifies the exact `vast_srv` project identity or names the exact blocker preventing identity resolution.
4. Tactical reporting proves at least one minimal server-only access path into `vast_srv`, or names the exact blocker.
5. Tactical reporting states whether the global workflow may proceed beyond `C1`.
