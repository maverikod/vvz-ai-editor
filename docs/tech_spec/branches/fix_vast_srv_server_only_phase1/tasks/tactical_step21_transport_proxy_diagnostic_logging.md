<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 21 — focused transport/proxy-path diagnostics + faithful reproduction.
-->

# Tactical Task: Step 21 — Diagnostic logging + `vast_srv` reproduction

## Purpose

Bounded in-repo save-path and transport-layer work (Steps 16–20) improved behavior but **did not eliminate repeated-save instability**. Step 21 adds **focused diagnostic logging** on the **narrowest implicated paths** (in-repo: **DB RPC client**, **driver RPC server**, **request queue**; proxy-layer visibility is **partially outside** this tree per `researcher_code`), then **restarts** `code-analysis-server`, and **reproduces** the repeated-save sequence on the guarded **`vast_srv`** harness with **full command trace** and new diagnostics.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/implementation_plan.md` (Step 21)
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/steps/instrument_transport_path_and_reproduce_save_failure.md` (active global step for this campaign)

## Scope

**Included:** Minimal **INFO-level** structured logs and **elapsed timings** in the narrow save→RPC/transport→queue→DB driver path (`rpc_client`, `rpc_server`, `request_queue` as needed), plus command-layer entry for **`cst_save_tree`** / persist hooks where the dispatcher hands off; **`list_projects`** timeout branch if still relevant; **`server_manager_cli` restart** after any server code change (no git commit unless user explicitly requests); **`tester_ca`** repeated **`cst_load_file` → `cst_save_tree`** on **`vast_srv`** with command trace; interpretation of **`logs/`** output.

**Excluded:** Broad transport refactors; direct **`vast_srv`** file access except via **`tester_ca`**; non-server proxy host changes unless escalated.

## Boundaries

- **`coder_auto` / `tester_auto`** must not touch guarded **`test_data/vast_srv`** code.
- After any **`code-analysis-server`** code change: **explicit restart** before revalidation.
- **`SERVER_UNAVAILABLE`** originating in **Cursor MCP Proxy / adapter HTTP path** may require **outside-repo** follow-up; in-repo logs still clarify **DB RPC vs command timeout**.

## Dependencies

- Step 20: bounded adapter bump + stress showed **`SERVER_UNAVAILABLE`** on saves **#4+** and proxy degradation.

## Parallelization note

**Serialized:** `researcher_code` (if new gaps) → `coder_auto` → explicit **`server_manager_cli` restart** (via `tester_auto` or `shell`) → `tester_ca` reproduction.

## Expected outcome

- Instrumentation batch on disk + restart evidence + **`tester_ca`** trace + **what new logs reveal** (pool, socket, queue, timeout classification). Git commit only if user requests.

## Correction items

- From specialist outputs.

## Questions/escalation rule

- Escalate if **end-to-end MCP request IDs** require **`mcp-proxy-adapter`** source changes or **Cursor** proxy config not in this repo.

## File inventory (Step 21 batch — from `researcher_code`)

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/core/database_client/rpc_client.py` | `_send_request` / `call` failure diagnostics (pool wait, errno, elapsed) |
| modify | `code_analysis/core/database_driver_pkg/rpc_server.py` | enqueue / handle path metrics or slow-path logging |
| modify | `code_analysis/core/database_driver_pkg/request_queue.py` | optional depth on enqueue/dequeue |
| modify | `code_analysis/commands/project_management_mcp_commands/list_projects.py` | log on `asyncio.TimeoutError` (15s) |

**`instrument_transport_path` addendum (2026-04-05):**

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/commands/cst_save_tree_command.py` | `[SAVE_PATH] cst_save_tree enter` |
| modify | `code_analysis/core/database/file_tree_sync.py` | `[SAVE_PATH] sync_file_to_db_atomic` enter/exit + timings |

## Specialist routing

- `researcher_code`: **DONE** — narrowest hooks and in-repo vs outside-repo split documented in branch chat.
- `coder_auto`: implement minimal logging + timing batch; satisfy **CR-007** on touched paths; **no git commit** unless user requests.
- `tester_auto` or **`shell`**: **`server_manager_cli --config config.json restart`** after code change; record PID/config path and exit code.
- `tester_ca`: guarded **`vast_srv`** repeated-save sequence + correlate with **new log lines**.

## Branch execution log (Step 21)

- **`researcher_code`:** Narrowest in-repo hooks: **`RPCClient._send_request` / `call`**, **`RPCServer`** enqueue/wait, **`RequestQueue`** depth, **`list_projects`** timeout; HTTP/MCP routing in **`mcp-proxy-adapter`** (PyPI, not vendored). Full proxy **`SERVER_UNAVAILABLE`** may need **outside-repo** instrumentation; in-repo logs clarify **DB RPC vs pool vs queue vs command timeout**.
- **`coder_auto`:** Commit **`1a711f0eb2b00a49a4d5c8cc828de8019204bb8a`** — `feat(logging): Step 21 RPC/queue diagnostics for repeated-save instability`. Modified: `rpc_client.py`, `rpc_server.py`, `request_queue.py` (DEBUG enqueue/dequeue), `list_projects.py` (timeout INFO). Backups under `old_code/`.
- **`tester_auto`:** `git` confirms commit; **`server_manager_cli --config config.json restart`** exit **0**, PID **`1103484`**, stderr empty; config **`/home/vasilyvz/projects/tools/code_analysis/config.json`**.
- **`tester_ca`:** **`vast_srv`** `project_id` **`c86dded6-6f93-4fb0-be54-b6d7b739eeb9`**, file **`add_fallback_logic.py`**. **`cst_save_tree` #1** OK (~8.4s `save_sync_file_to_db` in timings). **`cst_save_tree` #2** → MCP **`SERVER_UNAVAILABLE`**. Logs: **`Command timed out after 30.00s`** for second `cst_save_tree` (`InternalError` / `CancelledError` path). After: **`health`** OK; **`list_projects`** → **`LIST_PROJECTS_ERROR`**, **`Connection refused`** on DB socket. Grep: heavy **`[CHAIN] rpc_client`** in `mcp_server.log`; **Step 21 `request_queue` / `rpc_server` tagged lines not observed** in that file for that run (DEBUG queue lines may require log level / different tail).

### Branch execution log (`instrument_transport_path_and_reproduce_save_failure`, 2026-04-05)

- **`researcher_code`:** Hop chain: `CSTSaveTreeCommand.execute` → `save_tree_to_file` → `sync_file_to_db_atomic` → `RPCClient` → `rpc_server` / `RequestQueue`. Gaps addressed: persist bracketing, RPC success `elapsed_ms`, dequeue visibility at INFO.
- **`coder_auto`:** **`[SAVE_PATH]`** INFO: `cst_save_tree enter`; `sync_file_to_db_atomic` enter/exit + `elapsed_ms`; `rpc_client` success timing; `rpc_server dequeue` + `wait_ms`. Files: `code_analysis/commands/cst_save_tree_command.py`, `code_analysis/core/database/file_tree_sync.py`, `code_analysis/core/database_client/rpc_client.py`, `code_analysis/core/database_driver_pkg/rpc_server.py`. No git commit.
- **`shell`:** `server_manager_cli --config config.json restart` → exit **0**, **`started pid=1140944`**, stderr empty.
- **`tester_ca`:** **`health` / `list_projects`** → **`SERVER_NOT_FOUND`** (`code-analysis-server_1 not found`). **`list_servers`:** only **`embedding-service`**, **`svo-chunker-prod`** — **`code-analysis-server` not registered** on this MCP Proxy. **`cst_load_file` / `cst_save_tree` not reached.** Repeated-save failure **not reproduced**; blocker = **proxy registration**, not server instrumentation.
- **Next:** Register **`code-analysis-server`** in MCP Proxy (or reload config), then rerun **`tester_ca`** harness and correlate **`logs/`** **`[SAVE_PATH]`** lines with command index.

### Branch execution log (`instrument_transport_path` resume, 2026-04-05 — proxy visibility + harness + logs)

- **`researcher_code`:** In-repo: `config.json` **`registration.*`** → `https://172.28.0.2:3004/register`; server bind **`https://172.28.0.1:15000`**; MCP tools **`list_servers`**, **`register_server`**, **`reload_config`** (proxy descriptors). No in-repo script named `register*.py`; catalog is **proxy + running server** (`docs/REGISTRATION_AND_MTLS.md`).
- **Proxy visibility:** **`list_servers`** now returns **3** servers: **`embedding-service`**, **`svo-chunker-prod`**, **`code-analysis-server`**. **`health`:** `proxy_registration.registered: true`, **`server_url`** `https://172.28.0.1:15000`, PID **1140944**. **No repo code change** and **no commit** — visibility restored without a workspace patch (transient/operational).
- **`tester_ca`:** **`vast_srv`** `project_id` **`c86dded6-6f93-4fb0-be54-b6d7b739eeb9`**, **`add_fallback_logic.py`**, `tree_id` **`045fe8ab-aae3-4d2a-9146-53d50c130be5`**. **`cst_save_tree` #1** and **#2** both **OK** (distinct `backup_uuid`). **First failing command:** **none** this run.
- **`tester_auto` (logs):** **`[SAVE_PATH]`** present in **`logs/mcp_server.log`** and **`logs/database_driver.log`**. Save #1: **`sync_file_to_db_atomic` exit** `elapsed_ms≈8922.5`, command wall **~17.7s**. Save #2: **`sync_file_to_db_atomic` exit** `elapsed_ms≈8842.4`, **`[TIMING] command=cst_save_tree total_elapsed_sec≈16.48`**, command executed **~17.5s**. **`rpc_server dequeue`** **`wait_ms`** ~80–100ms for `begin_transaction` / `commit_transaction`. Queue wait is **not** the dominant cost; **DB sync + RPC** (~8.9s persist) dominates.
- **Failure reproduction:** Intermittent **`SERVER_UNAVAILABLE`** / second-save failure **not reproduced** in this session; **`[SAVE_PATH]`** proves **end-to-end path** for both saves when proxy is healthy.
- **Next if instability returns:** Stress **more consecutive** `cst_save_tree` or **heavier file**; on failure, compare **`[SAVE_PATH]`** stop point vs prior **`[CHAIN]`** timeout lines; check **`database_driver.log`** dequeue gaps.

### Branch execution log (bounded stress + interleave attempt, 2026-04-05)

- **`tester_ca`:** Target **10 sequential** `cst_save_tree` after `cst_load_file` (`add_fallback_logic.py`, new `tree_id` **`1d728128-5d1e-45c9-9727-585ac5a6e1b6`**). **`health`** / **`list_projects`** / **`cst_load_file`** **OK**. **First `cst_save_tree` (#1)** → MCP **`SERVER_UNAVAILABLE`** (empty message after colon). **Phases B–C** (interleaved **`list_projects`**, optional DB status) **not run** — blocked at first save.
- **`tester_auto` (logs, same failure):** **`[SAVE_PATH] cst_save_tree enter`** present (`mcp_server.log` ~430467); **`Executing command: cst_save_tree`** ~430460. Progress through **`resolve_path`**, backup, atomic replace, **`[SAVE_PATH] sync_file_to_db_atomic enter`**, **`[SAVE_PATH] rpc_client`** `begin_transaction` / `execute_batch` (~1s each). **~30s later** (`00:17:56` → `00:18:26`): **`CancelledError`**, **`TimeoutError`**, **`InternalError: Command timed out after 30.00s`** at **`cst_save_tree_command.py:172`** — **no** successful **`[TIMING] command=cst_save_tree total_elapsed_sec`** / **`sync_file_to_db_atomic exit`** for this attempt. **`database_driver.log`** same window: **`[SAVE_PATH] rpc_server dequeue`** with **`wait_ms`** still **sub‑100ms**; interleaved **`execute_batch` ERROR: FOREIGN KEY constraint failed** on **other** batch/file-watcher paths (not the save line item).
- **Proves:** Intermittent symptom is **not** “failure before command layer” — **`[SAVE_PATH]`** proves entry and mid-save RPC. **Proxy `SERVER_UNAVAILABLE`** correlates with **adapter 30s command timeout** + **`CancelledError`** while save still inside **`asyncio.to_thread`** / DB sync. **Does not prove** queue saturation (**`wait_ms`** not growing here); **persist/RPC work did not finish** within **30s** budget on this attempt.
- **Narrowest next step (in scope):** Align **`DEFAULT_REQUEST_TIMEOUT`** / **`cst_save_tree`** budget with measured **`sync_file_to_db_atomic`** duration under load **or** reduce concurrent DB batch contention / FK failures during save (escalate if global timeout policy change); optional rerun **10-save** + interleave after recovery.
