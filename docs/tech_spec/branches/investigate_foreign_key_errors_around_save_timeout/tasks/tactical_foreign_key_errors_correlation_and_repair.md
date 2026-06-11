<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task for global step: investigate_foreign_key_errors_around_save_timeout.md
-->

# Tactical Task: FOREIGN KEY errors — correlation, path classification, narrow repair

## Purpose

Produce **evidence-backed** answers for what `FOREIGN KEY constraint failed` (SQLite) errors mean in this codebase, **which workloads** emit them (guarded `cst_save_tree` / `sync_file_to_db_atomic` vs file watcher vs other RPC batches), whether they **plausibly contribute** to `cst_save_tree` timeout or adapter **30s** cancellation **beyond mere timestamp proximity**, and the **narrowest** in-repo repair target **or** a precise “missing signal” statement. This task **does not** treat correlation-by-time as causation.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/implementation_plan.md` (context: `vast_srv` server-only campaign; related steps 13–21)
- `docs/tech_spec/steps/investigate_foreign_key_errors_around_save_timeout.md` (parent global step)
- Prior related notes: `docs/tech_spec/branches/fix_vast_srv_server_only_phase1/tasks/tactical_step21_transport_proxy_diagnostic_logging.md` (execution log: FK on **other** batch paths during save timeout window)

## Scope

**Included:**

- Parse **`logs/`** (at minimum `database_driver.log`, `mcp_server.log`; rotated `*.log.*` if needed) for **`FOREIGN KEY`**, **`execute_batch`**, **`[SAVE_PATH]`**, request/command markers, and **timestamps** overlapping known **`cst_save_tree`** timeout windows.
- Map each distinct **error signature** (message fragment, table/constraint if logged) to **Python modules/functions** and **SQL operation kind** (insert/update batch, which entity sync).
- Classify each occurrence as **(A)** same RPC batch / same logical operation as guarded save, **(B)** concurrent **file watcher** or **index** sync, **(C)** other RPC client, or **(D)** indeterminate — with **quoted log lines** as proof.
- Assess **mechanistic** plausibility of FK noise amplifying timeout: e.g. lock hold time, transaction retries, queue depth, driver contention — **only** with code-backed reasoning, not proximity alone.
- If a **minimal, proven** server defect is identified (e.g. wrong insert order, missing parent row for a specific sync path), **`coder_auto`** implements fix; **`tester_auto`** restarts server (`server_manager_cli --config config.json restart`) and runs targeted checks; **`tester_ca`** only if **`test_data/vast_srv`** revalidation is required.

**Excluded:**

- Broad schema refactors or unrelated DB design changes.
- Direct file access to **`test_data/vast_srv`** except via **`tester_ca`** (not required for primary logs+code mission).
- Git commit unless user explicitly requests.

## Boundaries

- No change to **`mcp-proxy-adapter`** or Cursor config unless escalated to global orchestrator.
- After **any** `code-analysis-server` code change: **mandatory restart** before validation.

## Dependencies

- **none** (may consume prior branch notes from `fix_vast_srv_server_only_phase1` as **hypotheses only** until confirmed in logs/code).

## Parallelization note

- **`researcher_code`** first (logs + code mapping). **`coder_auto`** only after a **proven** narrow defect. **`tester_auto`** for restart + non-`test_data` tests. **`tester_ca`** optional for guarded harness revalidation.

## Expected outcome

1. Table of **FK error signatures** → **source path** (module/function) → **log proof**.
2. Explicit statement: **on** vs **off** guarded `cst_save_tree` persist path.
3. **Causality assessment** (concurrent noise vs plausible contributor) with **mechanism**, not timestamps alone.
4. Either **minimal patch summary + restart confirmation** or **narrowest next repair target** with proof.

## Correction items

- Replace any prior branch **hypothesis** (e.g. “FK on other paths”) with **verified** line-level evidence from current logs and code.

## Questions/escalation rule

- Escalate to global orchestrator if the fix requires **global timeout policy**, **schema migration**, or **proxy** contract changes.

## File inventory (candidates — verify/modify only after `researcher_code` confirmation)

| action | path | purpose |
|--------|------|---------|
| verify | `logs/database_driver.log` | FK + `execute_batch` interleaving |
| verify | `logs/mcp_server.log` | Command / `[SAVE_PATH]` correlation |
| verify | `code_analysis/core/database_driver_pkg/rpc_server.py` | `execute_batch` error surface |
| verify | `code_analysis/core/database_client/rpc_client.py` | batch RPC caller |
| verify | `code_analysis/core/database/file_tree_sync.py` | `sync_file_to_db_atomic` |
| verify | `code_analysis/commands/cst_save_tree_command.py` | `cst_save_tree` command |
| TBD | `code_analysis/core/database/file_tree_sync.py` or related | only if defect proven |

## Class/function inventory

- **Filled by `researcher_code`** with exact dotted paths, signatures, and which emit or handle FK errors.

## Data structures

- SQLite schema / FK names as discovered in code or migrations — **from `researcher_code`**.

## Import map

- **Per file** after research narrows edit set.

## Error handling map

- **`execute_batch`** / sqlite3: where **`FOREIGN KEY constraint failed`** is logged and propagated — **from `researcher_code`**.

## Config dependency

- `config.json` database path, RPC timeouts — only if implicated by evidence.

## Test plan

- **`tester_auto`:** run **targeted** pytest modules touching DB sync if **`coder_auto`** changes code; record command and pass/fail.
- **`tester_ca`:** optional **`vast_srv`** guarded save sequence after fix — only if user/orchestrator requires harness proof.

## Concrete examples

- **From `researcher_code`:** one **log excerpt** → **call path** → **SQL shape** (no fabricated examples).

## Algorithm/logic description

- **Log correlation procedure** (numbered): (1) extract FK lines with timestamps; (2) find nearest `[SAVE_PATH]` / `cst_save_tree` / watcher markers; (3) classify path; (4) cross-check code for that batch’s inserts.

## Forbidden approaches

1. Infer causality from **timestamp proximity alone**.
2. Expand scope to full DB redesign.
3. Skip server restart after server code change.

## Specialist routing

| Agent | Role |
|-------|------|
| `researcher_code` | Logs + code: FK signatures, paths, mechanism analysis |
| `coder_auto` | Minimal server fix **only** if proven |
| `tester_auto` | Restart server; pytest if code changed |
| `tester_ca` | Optional `vast_srv` revalidation |

## Branch execution log

### `researcher_code` (2026-04-05) — evidence package

**FK signature (logs):** `sqlite3.IntegrityError: FOREIGN KEY constraint failed` → wrapped as `execute_batch failed: FOREIGN KEY constraint failed` in `run_execute_batch` / `handle_execute_batch` (`database_driver.log*`, `mcp_server.log`, `file_watcher.log`). SQLite does **not** name the failing table/constraint in the message.

**Proven producer (logs + stack):** File watcher **`ProcessorQueueOps._queue_project_delta`** → `_db_execute_batch(insert_ops)` with `INSERT OR REPLACE INTO files (path, lines, last_modified, has_docstring, project_id, ...)`. Example: `mcp_server.log` ~1678–1712 — `[NEW FILE]` / `[CHANGED FILE]` for `test_data/vast_srv/...`, then `[CHAIN] client execute_batch n_ops=22`, then FK + `Batch queue failed for project ...` with traceback through `processor_queue.py:237`.

**Guarded `cst_save_tree` path:** Code chain `save_tree_to_file` → `sync_file_to_db_atomic` → `execute_batch` / `update_file_data_atomic_batch` (`file_tree_sync.py`, `file_data_batch.py`). **No log sample** in this pass where **`FOREIGN KEY`** text appears on the same failure as **`cst_save_tree`** / **`sync_file_to_db_atomic` exit** failure; save-related errors observed elsewhere include **socket / transaction-not-found**, not FK.

**Classification:** Watcher-driven batches → **(B)** concurrent background. Driver-only `execute_batch` FK lines → **(D)** indeterminate client without per-request tag in driver log. Indexing worker slice: **no** FK in grep slice used.

**Timeout / degradation:** FK fails a **single batch** and rolls back (fast). **Not** sufficient evidence that FK **causes** the **30s** `cst_save_tree` timeout; shared RPC **contention** could add latency **independently**. Prior Step 21 note (bounded stress): FK interleaved during save window still consistent with **concurrent** watcher work, not same batch as save line item.

**Minimal proven defect for immediate code fix:** **Not established** — need failing SQL + params or stmt index on reproduce.

**Narrowest next repair / investigation target:** (1) Gated log of **failing statement / params** on `IntegrityError` in `sqlite_run.run_execute_batch` or `handle_execute_batch`; (2) on reproduce, verify `projects` row exists for watcher `project_id`; (3) optional: correlate `request_id` / command name with `execute_batch` in RPC logs.

### `coder_auto` / `tester_auto` / `tester_ca`

- **2026-04-05 (agreed next step):** Add **minimal diagnostic logging** on `sqlite3.IntegrityError` (incl. `FOREIGN KEY constraint failed`) inside **`run_execute_batch`** (`code_analysis/core/database_driver_pkg/drivers/sqlite_run.py`): SQL preview (truncated), failing **expanded-batch** operation index (aligned with post-`expand_operations` / `runs` enumeration), `transaction_id`, compact params preview (truncated; emphasize tuple elements that look like ids/paths). **No** full dumps. Preserve existing `DriverOperationError` wrapping. After patch: **`tester_auto`** — black/flake8/mypy on touched file(s), targeted pytest if any; **restart** `server_manager_cli --config config.json restart`; optional **`tester_ca`** stress on `test_data/vast_srv` to exercise path; inspect **`logs/`** for new lines. **No git commit** unless user requests.

### `coder_auto` (2026-04-05) — instrumentation landed

- **File:** `code_analysis/core/database_driver_pkg/drivers/sqlite_run.py` — helpers `_sql_preview_for_log`, `_params_preview_compact`, `_probe_executemany_failing_row`, `_log_batch_integrity_error`; `run_execute_batch` catches `sqlite3.IntegrityError` on single-`execute` and `executemany` paths, logs **`[BATCH_INTEGRITY] sqlite execute_batch IntegrityError`** with `tid`, `run_idx`, `row_in_group`, optional `many_rows`, `sql_preview`, `params_preview`, `err`; then re-raises `DriverOperationError` as before. **`executemany`:** uses `SAVEPOINT` + row probe to refine `run_idx` / `row_in_group` when possible.
- **Validation (coder):** `black` / `flake8` / `mypy --follow-imports=skip` on touched file — OK.

### `tester_auto` (2026-04-05)

- **Restart:** `python -m code_analysis.cli.server_manager_cli --config config.json restart` — **exit 0** (new pid).
- **Pytest:** targeted batch/driver tests — **53 passed** when excluding `tests/test_file_data_batch_integration.py`; **full set** hits **1 error** in `test_update_file_data_atomic_batch_writes_expected_db_contents` — **`sync_schema` / migration**: `no such table: main.indexing_errors` before index creation (pre-existing; not caused by `sqlite_run` edit).
- **`logs/` grep `BATCH_INTEGRITY`:** **no matches** after restart (no `IntegrityError` on `run_execute_batch` path in that window).

### `tester_ca` (2026-04-05)

- **Blocked:** MCP Proxy `list_servers` shows **no** registered `code-analysis-server` — `call_server(..., "list_projects")` → `SERVER_NOT_FOUND`. No `vast_srv` exercise via server in this session.

### Continuation (2026-04-05) — MCP visibility + `[BATCH_INTEGRITY]` exercise

- **`tester_ca`:** `list_servers` still **`total_servers`: 2** — only `embedding-service`, `svo-chunker-prod`. **`reload_config`** with repo **`config.json`** returned “Configuration reload requested …”; **second** `list_servers` unchanged — **`code-analysis-server` still absent.** `call_server(code-analysis-server, list_projects)` → **`SERVER_NOT_FOUND`** (verbatim JSON in agent report). No FK text from server (no route to analysis server).
- **`tester_auto`:** **`grep` / recursive search on `logs/`** — **no `[BATCH_INTEGRITY]`** anywhere (including rotated logs). **Many** historical `FOREIGN KEY constraint failed` / `execute_batch failed` / `[CHAIN]` lines (e.g. `database_driver.log` ~`2026-04-05 00:37:33`, `tid=None`, `handle_execute_batch n_ops=3`, FK error) — **none** include the new diagnostic prefix; timestamps **end ~00:37:36** (shutdown), no newer driver activity proving post-instrumentation FK.
- **`researcher_code`:** MCP proxy **does not** populate `code-analysis-server` from repo **`config.json`** — that file drives **code-analysis-server** runtime **`registration.*`** (POST to OpenAPI proxy `/register`). **`reload_config`** on repo JSON is the **wrong artifact** for the proxy catalog and can leave only static entries (`embedding-service`, `svo-chunker-prod`) until **`code-analysis-server`** re-registers via startup registration or MCP **`register_server`**. Checklist: running analysis server + `registration.enabled` + reachable `register_url` / mTLS, then **`list_servers`** or manual **`register_server`**.

**Diagnosis from evidence this round:** Cannot classify **stale `project_id` vs ordering vs other invariant** from **`[BATCH_INTEGRITY]`** — **no such lines** in `logs/`. Historical FK lines lack SQL/params (pre-instrumentation or server build without logger path). **Narrowest unblocker:** restore proxy registration for `code-analysis-server`, run a workload that hits `run_execute_batch` **IntegrityError** on a build that includes `[BATCH_INTEGRITY]`, then re-grep `database_driver.log`; optional: **`tester_auto`** unit test that forces `IntegrityError` in batch path (no `test_data` direct access).

### Retry (2026-04-05) — post-restart `pid=1175691`

- **`tester_ca`:** `list_servers` (`page_size=50`) — **`code-analysis-server` still absent**; only `embedding-service`, `svo-chunker-prod`. **No** `call_server` workload (blocked until registered).
- **`tester_auto`:** **`grep '[BATCH_INTEGRITY]' logs/`** — **no matches** workspace-wide. **`mcp_server.log`** shows **`pid=1175691`** at **2026-04-05 01:00:39** / Hypercorn **01:00:42**; post-restart **`[CHAIN]`** / **`[SAVE_PATH]`** ~**01:00:49–01:00:56**; **no** `[BATCH_INTEGRITY]`, **no** FK/`execute_batch` in last-80 tails of `database_driver.log` / `mcp_server.log` (older FK batch lines remain ~**00:37:33**, pre-restart).

---

## Subordinate agents state (checkpoint)

| Agent | Status | Scope / last update |
|-------|--------|---------------------|
| `researcher_code` | **done** | Logs + code mapping + `run_execute_batch` + proxy registration checklist, 2026-04-05 |
| `coder_auto` | **done** | `[BATCH_INTEGRITY]` logging in `sqlite_run.run_execute_batch`, 2026-04-05 |
| `tester_auto` | **done** | Log grep: no `BATCH_INTEGRITY`; FK/`[CHAIN]` samples ~00:37:33, 2026-04-05 |
| `tester_ca` | **blocked** | Post-restart (`pid=1175691`): MCP `list_servers` still no `code-analysis-server`; no guarded workload |
| `planner_auto` | **idle** | Atomic steps not used for this minimal instrumentation |
