<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task for global step: confirm_logical_write_live_path_and_resume_vast_srv_all_errors.
-->

# Tactical Task: Confirm logical-write live path + resume vast_srv all-errors remediation

## Purpose

Close the **proof gap** that guarded saves on the live MCP path emit observable evidence of **`execute_logical_write_operation`** (or equivalent single logical-write unit), then **without pausing** resume the server-only **`vast_srv`** campaign: enumerate confirmed errors from analysis commands, fix them with **`code-analysis-server`** tools only, and record fixed vs remaining until a **concrete** server defect or project blocker stops progress.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/confirm_logical_write_live_path_and_resume_vast_srv_all_errors.md`
- `docs/tech_spec/implementation_plan.md`
- Prior logical-write implementation context: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`

## Scope

**Included:**

- Minimum **server-side** logging (if current code does not emit grep-visible proof in `logs/`) → **restart** → **tester_ca** guarded `cst_save_tree` → **tester_auto** log correlation with agreed token(s).
- **`tester_ca`** only for **`test_data/vast_srv`**: `list_projects`, `comprehensive_analysis`, `lint_code`, `type_check_code`, `format_code`, CST edit/save cycles as needed, `update_indexes`, etc., per server capabilities.
- **`coder_auto`** for in-repo logging or server fixes when **`tester_ca`** hits a **blocking** server bug; **`tester_auto`** for pytest/restart/log grep; **`researcher_code`** for trace confirmation when facts are unclear.

**Excluded:**

- Direct read/write/shell on **`test_data/vast_srv`** by non-**`tester_ca`** agents.
- Git commit unless user explicitly requests.
- Pausing solely because backlog is large (continue in batches until true blocker).

## Boundaries

- **`test_data/vast_srv`:** MCP → **`code-analysis-server`** only.
- After **any** server code change: **restart** before validation (**`tester_auto`**).

## Dependencies

- Logical-write batching already implemented (`rework_write_queue_to_logical_operation_batches` branch narrative).

## Parallelization note

Serialize: **researcher_code** (logging facts) → **coder_auto** (if needed) → **tester_auto** (restart + logs) → **tester_ca** (proof save + remediation). Re-loop **coder_auto** / **tester_auto** only on server defects.

## Expected outcome

1. **Proof:** grep-visible (or equivalent) line(s) in repo **`logs/`** tying a live **`cst_save_tree`** to **`execute_logical_write_operation`** / client logical-write call.
2. **Remediation:** list of **`vast_srv`** errors addressed in this tactical run with command evidence; list of **remaining** confirmed errors; **narrow blocker** if any.

## Correction items

- If live path uses **in-process** `CodeDatabase` without RPC, proof must still show **`execute_logical_write_operation`** (or documented equivalent) in the path exercised by MCP.

## Questions/escalation rule

- Escalate to global orchestrator if **`tech_spec`** or campaign boundaries must change, or if **`mcp-proxy`** registration is permanently unavailable in the agent environment.

---

## Running execution log

- **Initialized:** 2026-04-05 — tactical file created; awaiting specialist evidence.
- **`researcher_code`:** Logging already present at INFO: client `[CHAIN] client execute_logical_write_operation n_batches=…` (`client_operations`), `rpc_client method=execute_logical_write_operation`, handler `method=execute_logical_write_operation n_batches=…` (`rpc_handlers_schema`); **mcp_server.log** vs **database_driver.log** split is expected — no mandatory new token unless audit wants `LOGICAL_WRITE_LIVE_PATH`.
- **`tester_auto` (log proof):** **Proof gap closed.** Grep **`logs/mcp_server.log`** and **`logs/database_driver.log`** — recent lines show **`execute_logical_write_operation`** with **matching `request_id`** and **`n_batches=6`**; enqueue/dequeue/handler chain on driver; client `[CHAIN]` + `[SAVE_PATH] rpc_client` on MCP log. Timestamps **2026-04-05 ~01:38:38–01:38:43**.
- **`tester_ca` (batch 1):** Part A **`cst_save_tree`** on **`vast_srv`** **`_fix_ssl_type.py`** **success** (wall **2026-04-05T01:44:27+03:00**). Part B **`comprehensive_analysis`** failed server-side: **`AttributeError`**: `'JobProgressTracker' object has no attribute 'set_status'` — **stopped** vast_srv fixes per brief.
- **`coder_auto`:** Fix **`code_analysis/core/progress_tracker.py`**: **`_DelegatingProgressTracker`** + **`_wrap_progress_tracker_if_needed`** so MCP adapter’s job tracker gets **`set_status`** delegated to **`inner._job.set_status`**. Backup in **`old_code/`**. Pytest **`test_shared_database_spawn_init`**, **`test_comprehensive_analysis_batch_summary`** — **6 passed**. **No git commit.**
- **`tester_auto`:** **`server_manager_cli restart`** exit **0**, PID **1213010**; **status** running; same pytest subset **6 passed**.
- **`tester_ca` (resume batch):** **`SERVER_NOT_FOUND`** for **`code-analysis-server_1`** after **`reload_config`**; **`list_servers`** only **`embedding-service`**, **`svo-chunker-prod`** — **no** `code-analysis-server`. **0** vast_srv fixes; **comprehensive_analysis** not re-run.
- **Continuation 2026-04-05 — `tester_ca` (visibility + analysis):** **`list_servers`** → **`code-analysis-server_1`** **active** (118 cmds). **`comprehensive_analysis`** queued **`job_id`:** `comprehensive_analysis_23bc42e6` — polled to **`completed`**, **`result.success`:** **true**. Payload: **2** placeholders (`add_full_queue_support/queue_helpers.py`), **12** flake8 (2 files), **12** mypy (2 files), **139** long files, **592** skipped up-to-date; key files: **`queue_helpers.py`**, **`ai_admin/__init__.py`**, **`ai_admin/auth/git_auth_manager.py`**. Immediately after, MCP returned **`SERVER_UNAVAILABLE`** / disconnect — **no** CST fixes applied in that session.
- **Continuation — `tester_auto`:** **`server_manager_cli restart`** exit **0**, PID **1224286**; **status** running (post-disconnect recovery). *No server-side code change in this restart* (operational reconnect only).
- **Continuation — `tester_ca` (fixes batch):** **`call_server`** → **`SERVER_UNAVAILABLE`**: *"All connection attempts failed"* to proxy URL **`https://172.28.0.1:15000`**; **`network_check`** failed; host **no listener on 15000** observed from agent env. **0** file edits. **Blocker:** proxy registration points at **unreachable** host:port from MCP proxy process; local daemon PID **1224286** does not present **:15000** to this checker.
- **`researcher_code` (config map):** Align MCP **`server_url`** with **`config.json`** **`server.host`** / **`server.port`** (defaults **`0.0.0.0`:**`15000` via **`constants`**); env **`CODE_ANALYSIS_SERVER_HOST`** / **`CODE_ANALYSIS_SERVER_PORT`**; **`build_server_config`** in **`main_server_config.py`**. **Action for parent:** ensure bridge/routing so proxy can reach the process actually listening, or re-register proxy with reachable URL.

---

## Subordinate Agents State

| agent | status | scope | blocker |
|-------|--------|-------|---------|
| `researcher_code` | done | logging + bind config map | none |
| `coder_auto` | done | `progress_tracker` `set_status` | none |
| `tester_auto` | done | restart PID 1224286 | none |
| `tester_ca` | blocked | vast_srv CST fixes | **MCP proxy → `https://172.28.0.1:15000` unreachable** (`SERVER_UNAVAILABLE`); analysis already completed earlier when server was up |
