<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Step: Restore Code Analysis Server Registration

## Goal

Restore a working `code-analysis-server` process and MCP proxy registration through `mcp-proxy`, where `mcp-proxy` itself operates over mTLS, bound or advertised correctly for the Docker network host context `smart-assistant`, with the same network and mTLS assumptions aligned for dependent services including the vectorizer and chunker, so the `vast_srv` campaign can resume from checkpoint `C0`.

## Input Artifacts

1. `docs/tech_spec/tech_spec.md`
2. `docs/tech_spec/implementation_plan.md`

## Output Artifacts

1. Any minimal runtime/config changes required to start and register `code-analysis-server`.
2. A tactical verification report proving proxy discovery and basic proxy-mediated command success.
3. A tactical verification report section confirming vectorizer and chunker compatibility with the same host/mTLS model, or naming exact blockers.

## Scope

1. Discover the exact startup, certificate, and registration mechanism currently used by this repository for `mcp-proxy`, which operates over mTLS.
2. Determine what host/address value must be used for the Docker network host context `smart-assistant`.
3. Determine how `mtls_certificates/` must be incorporated into proxy registration or runtime configuration.
4. Determine how the same host, certificate, and network assumptions affect dependent services including the vectorizer and chunker.
5. Apply the minimal fix set needed to make `code-analysis-server` run and register through `mcp-proxy`.
6. Verify that `mcp-proxy` can list and call `code-analysis-server` while operating in its mTLS configuration.
7. Verify whether required vectorizer and chunker connectivity is valid under the same model, or report exact blockers.
8. Report the resume checkpoint for the paused `vast_srv` server-only workflow.

## Forbidden Approaches

1. Do not perform any direct work on `vast_srv`.
2. Do not treat local-only process startup as sufficient without `mcp-proxy` registration proof.
3. Do not bypass tactical orchestration.

## Acceptance Criteria

1. `code-analysis-server` is started successfully.
2. Registration path to `mcp-proxy` is functioning for `smart-assistant`.
3. Proxy listing shows `code-analysis-server`.
4. Proxy command invocation succeeds against `code-analysis-server` through `mcp-proxy`.
5. Tactical reporting identifies the cert/config usage tied to `mtls_certificates/`.
6. Tactical reporting confirms whether vectorizer and chunker dependencies fit the same host/mTLS model, or names the exact blockers.
7. Tactical reporting states whether the global workflow may resume at `C0` completion and proceed to `C1`.
