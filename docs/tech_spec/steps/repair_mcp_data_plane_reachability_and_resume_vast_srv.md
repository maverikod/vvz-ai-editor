<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Repair MCP Data Plane Reachability And Resume Vast Srv

## Goal

Repair the concrete blocker where `mcp-proxy` lists `code-analysis-server` but cannot reach its registered `server_url`, then immediately resume the interrupted server-only `vast_srv` remediation flow.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`
3. `docs/tech_spec/steps/confirm_logical_write_live_path_and_resume_vast_srv_all_errors.md`

## Output Artifacts

1. A tactical report identifying the exact host/port/registration mismatch or reachability failure on the MCP data plane.
2. A tactical repair batch restoring `health` and command reachability through `mcp-proxy`.
3. A tactical report confirming resumed `vast_srv` remediation after the reachability fix.

## Scope

1. Investigate the actual listener address and the registered `server_url`.
2. Repair the smallest correct host/port/registration/runtime mismatch causing the proxy to fail its data-plane connection.
3. Revalidate `health` through `mcp-proxy`.
4. Resume the interrupted `vast_srv` remediation batch immediately after recovery.
5. Explicitly restart the server after any server-side code change before revalidation.

## Forbidden Approaches

1. Do not bypass the proxy with direct local-only checks as a substitute for MCP reachability.
2. Do not reopen unrelated save-path or analysis-path work if the current blocker is data-plane reachability.
3. Do not pause after restoring reachability; return directly to `vast_srv` remediation unless a new blocker appears.

## Acceptance Criteria

1. Tactical execution identifies why the proxy cannot reach the registered `server_url`.
2. Tactical execution restores proxy-mediated `health` successfully.
3. The interrupted `vast_srv` remediation flow resumes after the reachability fix.
4. Any remaining blocker is narrower than the original MCP data-plane failure.
