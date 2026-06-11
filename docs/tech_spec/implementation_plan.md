<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Implementation Plan

## Overview

This plan restores reachability of `code-analysis-server` through `mcp-proxy`, where `mcp-proxy` itself runs over mTLS, and aligns the same network/mTLS model for dependent services such as the vectorizer and chunker before any further `vast_srv` work resumes.

## Global Steps

1. Determine the exact runtime, certificate, registration, and dependent-service connectivity path required to expose `code-analysis-server` through `mcp-proxy`, where `mcp-proxy` runs over mTLS, for the Docker network host context `smart-assistant`.
2. Apply the minimal configuration and startup changes needed to run and register `code-analysis-server` through `mcp-proxy`, and align any required vectorizer/chunker connectivity assumptions.
3. Verify proxy discovery, command reachability, and dependent-service connectivity, then declare the resume checkpoint for the `vast_srv` server-only workflow.
4. After live confirmation of `C0` in the current environment, begin `C1` for `vast_srv`: resolve project identity and confirm server-only access to the project through `code-analysis-server`, using `tester_ca` only for guarded paths.
5. After `C1` succeeds, perform the initial server-only analysis pass on `vast_srv` to build the first validated defect backlog: explicit errors, unfinished code, and logical duplicates.
6. Before opening the broad fix phase, investigate the `vast_srv` coverage gap and monitor analysis dynamics over time to determine whether skipped files are still being processed, intentionally filtered, or blocked by a server-side limitation or defect.
7. If Step 6 identifies a `code-analysis-server` analysis-path limitation or defect, repair that server-side issue first, then re-run `C0`, `C1`, and `C2` before reopening any broader `vast_srv` work.
8. If the repaired analysis path still reports implausible `comprehensive_analysis` coverage summary values, investigate and repair the server-side summary/counting logic before opening the broad `vast_srv` fix phase.
9. After coverage summary reliability is revalidated, begin the broad `vast_srv` fix phase under server-only execution, prioritizing explicit errors first, then unfinished code, then logical duplicates.
10. If the `vast_srv` fix phase encounters a server-side CST editing defect that blocks safe server-only fixes, repair that `code-analysis-server` editing defect first, then resume the interrupted `vast_srv` batch from the last successful checkpoint.
11. Improve precise server-side micro-edit semantics for `code-analysis-server` wherever `vast_srv` exposes remaining bounded edit limitations that block safe server-only fixes.
12. Investigate and simplify the `comprehensive_analysis` pipeline to improve runtime, reliability, and explainability, using `vast_srv` as a verification harness rather than the primary goal.
13. If `vast_srv` work is interrupted by server crash symptoms or restart/re-registration instability, determine the concrete root cause first before attempting another operational fix.
14. If Step 13 narrows the failure to the DB-driver or socket lifecycle around `cst_save_tree`, repair that minimal server-side lifecycle/contension path first, then revalidate the interrupted `vast_srv` batch.
15. Continue real server-only `vast_srv` usage while recording the exact last successful command and first failing command if `SERVER_NOT_FOUND` or related visibility loss recurs, so the failure can be tied to a concrete command boundary instead of only broad time windows.
16. If Step 15 captures `SERVER_NOT_FOUND` only after a concrete failing command, repair that immediate server-side failure path first, starting with the narrowest persist/logging/save-path defect before resuming broader `vast_srv` continuation.
17. If the first `cst_save_tree` succeeds but repeated guarded saves degrade into timeout or unavailability, investigate and repair that repeated-save availability path as a separate server-side issue before resuming broad `vast_srv` continuation.
18. If guarded work reproduces the exact transition `cst_modify_tree success -> cst_save_tree fail -> socket refused`, investigate and repair that transition as a dedicated server-side failure path before any further broad `vast_srv` continuation.
19. If repeated guarded saves become stable only after backoff or manual proxy refresh, investigate and repair the remaining proxy/transport availability path, including `mcp-proxy-adapter` or registration/reload behavior if implicated, before declaring repeated-save stability complete.
20. If Step 19 shows that the remaining blocker is primarily outside this repository, continue with a bounded adapter/proxy-layer repair or configuration step there, then revalidate guarded `vast_srv` behavior against the updated transport layer.
21. If the remaining blocker still reproduces under repeated guarded saves, add focused diagnostic logging in the implicated transport/proxy path, explicitly restart the server or reload the affected layer after the change, and then reproduce the failure with command tracing on the `vast_srv` harness.
22. If Step 21 proves that repeated-save failure is caused by interleaving writes on the serialized SQLite path, redesign the write queue so every write is scheduled as a logical operation batch, even when it contains a single SQL statement, and prevent other write jobs from interleaving between the begin/execute/commit phases of one logical save.
23. After Step 22 is functionally validated, obtain proof-level live logging that the logical-write path is active, then immediately resume server-only `vast_srv` remediation and continue fixing all discovered `vast_srv` errors until a concrete blocker is encountered.
24. If Step 23 is blocked because `mcp-proxy` lists `code-analysis-server` but cannot reach its registered `server_url`, repair that end-to-end MCP data-plane reachability first, revalidate `health` through the proxy, and then immediately resume the interrupted `vast_srv` remediation batch.

## Dependency Order

Step 1 blocks Step 2. Step 2 blocks Step 3.
Step 3 blocks Step 4.
Step 4 blocks Step 5.
Step 5 blocks Step 6.
Step 6 blocks Step 7 when a server-side issue is identified.
Step 7 blocks Step 8 when post-repair coverage summaries remain unreliable.
Step 8 blocks Step 9 until coverage summary reliability is revalidated.
Step 9 blocks Step 10 when a server-side CST editing defect blocks safe continuation.
Steps 11 and 12 may run in parallel when they do not depend on the same server-side files or rollout sequence.
Step 13 preempts renewed operational retries when crash symptoms recur and blocks further restart-only attempts until a concrete cause investigation is performed.
Step 13 blocks Step 14 until the root cause is narrowed enough to justify a minimal targeted repair.
Step 15 may proceed after Step 14 revalidation when the goal is empirical reproduction under real usage, but it must stop immediately when the first exact command-boundary failure is captured.
Step 15 blocks Step 16 once the first exact failing command boundary is captured.
Step 16 blocks Step 17 when the original persist/logging defect is repaired but a repeated-save availability failure remains.
Step 17 blocks Step 18 when the narrower failing transition is reproduced and identified.
Step 17 or 18 blocks Step 19 when the remaining instability is narrowed to intermittent proxy/transport availability rather than the original in-process save defect.
Step 19 blocks Step 20 when the narrowest exact blocker lies primarily in `mcp-proxy-adapter` or external proxy-layer behavior.
Step 20 blocks Step 21 when a bounded adapter/proxy batch still leaves an unexplained repeated-save failure and deeper instrumentation is required.
Step 21 blocks Step 22 when instrumentation proves that the remaining failure is caused by write-operation interleaving on the serialized SQLite path.
Step 22 blocks Step 23 once repeated guarded saves are functionally stable and the next need is proof-level live confirmation plus renewed `vast_srv` remediation.
Step 23 blocks Step 24 when the next exact blocker is MCP reachability to the registered `code-analysis-server` URL rather than a defect inside the validated save path itself.

## Resume Rule

If Step 2, Step 3, Step 4, Step 5, or Step 6 reveals a defect in `code-analysis-server`, stop, fix the defect, re-verify server registration and current project access, and resume from the last successful global checkpoint.
If Step 7 is opened, no broader `vast_srv` fix work may proceed until the repaired server re-passes `C0`, `C1`, and `C2`.
If Step 8 is opened, no broader `vast_srv` fix work may proceed until coverage summary reliability is revalidated.
Step 9 must continue to use server-only `vast_srv` access, with guarded-path execution only through `tester_ca`.
If Step 10 is opened, the interrupted `vast_srv` batch may resume only after the server-side editing defect is repaired and the relevant server-only fix path is revalidated.
When executing Steps 11 and 12, each logical repair batch must be committed before the next batch begins, so rollback remains available at every stage.
If Step 13 is opened, no new retry cycle on the interrupted `vast_srv` batch may be treated as a solution until the server-side cause of the crash or de-registration event is narrowed and reported.
If Step 14 is opened, the repair must stay narrowly focused on the DB-driver / socket lifecycle path implicated by `cst_save_tree`, and the interrupted `vast_srv` batch may resume only after that path is revalidated.
If Step 15 captures a new exact command-boundary failure, further broad `vast_srv` continuation pauses again until that failure is analyzed.
If Step 16 is opened, the repair must target the first failing command path before treating any later `SERVER_NOT_FOUND` as the primary issue.
If Step 17 is opened, the repair must target repeat-save timeout / availability behavior specifically, and broad `vast_srv` continuation remains paused until repeated guarded saves are revalidated.
If Step 18 is opened, the repair must target the exact post-`cst_modify_tree` persist transition and the subsequent socket refusal path before broader continuation resumes.
After any server-side code change to `code-analysis-server`, an explicit server restart is mandatory before any revalidation or continued guarded `vast_srv` work.
If Step 19 is opened and points outside this repo (for example to `mcp-proxy-adapter`), the same batch discipline still applies: narrow repair, commit, restart/reload where relevant, then guarded revalidation.
If Step 20 is opened, the parent priority remains the same: repair the transport layer only as much as needed to unblock guarded `vast_srv` verification, not as a broad unrelated adapter refactor.
If Step 21 is opened, the primary objective is observability plus faithful reproduction: add focused logging, restart/reload the changed layer before testing, then capture the repeated-save failure sequence with the new diagnostics.
If Step 22 is opened, the repair must stay focused on the write-scheduling model itself: preserve serialization, but raise the unit of scheduling from individual RPC writes to full logical write operations so background worker writes cannot interleave with guarded save transactions.
If Step 23 is opened, tactical execution must first close the proof gap on the live logical-write path and then continue `vast_srv` remediation without unnecessary pauses, while still stopping immediately for any new blocking `code-analysis-server` defect.
If Step 24 is opened, the repair must stay focused on the MCP data plane: make the registered `server_url` actually reachable from the proxy, revalidate `health` through the proxy, and then return immediately to the interrupted `vast_srv` remediation flow.
