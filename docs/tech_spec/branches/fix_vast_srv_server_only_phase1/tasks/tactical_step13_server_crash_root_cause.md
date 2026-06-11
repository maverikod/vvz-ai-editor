<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Tactical Task: Step 13 — Server crash / de-registration root cause (diagnosis)

## Purpose

Record the outcome of implementation plan **step 13**: narrow the concrete cause of `cst_save_tree` **Connection refused**, post-restart **MCP catalog miss** for `code-analysis-server`, and related instability **before** any operational retry-only fix. This task is **diagnosis-first**; **log analysis and event-sequence reconstruction take priority** over static inference (user refinement). Repair batches are out of scope until log-backed classification is accepted or a **bounded** server-side fix is explicitly approved after evidence.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/implementation_plan.md` (step 13)
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Scope

- **Included:** **Log-backed** evidence-backed classification; timestamp-ordered event reconstruction (server, DB driver, proxy logs under `logs/`); correlation of command timing with DB/socket lifecycle and registration-related lines; narrowest blockers when logs are missing.
- **Excluded:** Broad `vast_srv` fixes; restart-only retry as solution; direct guarded-path execution (reserved for `tester_ca` when reproduction is required).

## Diagnosis outcome (synchronized with researcher_code evidence)

1. **`Connection refused` on `cst_save_tree`:** Maps to **Unix domain socket RPC** from the API/command path to the **database driver process** (`DatabaseClient` / `RPCClient`), not to the HTTP port used by MCP clients. **ECONNREFUSED** indicates nothing accepted the driver socket (driver down, restart race, or wrong path). **High confidence.**
2. **Health/read could still pass:** HTTP `/health` in `mcp_proxy_adapter` does not probe the DB driver socket; `RPCClient.health_check` may only check socket path existence, not a successful `connect()`. **High confidence** this is decoupled from `cst_save_tree` failure mode.
3. **`SERVER_NOT_FOUND` / `ServerNotFoundError`:** Raised in **`mcp_proxy_adapter`** orchestration when the **catalog** has no `ServerRecord` for `code-analysis-server` — registration/discovery/config issue, not `code_analysis` command code. **High confidence** on mechanism; **medium** on why catalog was empty without runtime logs.
4. **Coupled multi-factor:** Driver RPC failure and proxy catalog miss are **plausibly independent** unless one restart cleared both layers; **medium confidence** without timestamps/logs.

## Log-backed diagnosis (delegated `researcher_code`, 2026-04-04)

**Log sinks used:** `logs/mcp_proxy_adapter.log`, `logs/database_driver.log` / rotated `.1`–`.2`, `logs/mcp_server.log`, `config.json` (`server.log_dir`). **Gap:** `logs/code_analysis.log` is configured but **file absent** in workspace.

### Episode A (~09:44)

- MCP: `cst_save_tree` dispatched **09:44:01**; **no** matching “executed” line before subsequent events.
- Driver (`database_driver.log.2`): transaction with repeated **`FOREIGN KEY constraint failed`** on `execute_batch`; **~28 s gap** in log lines; then **`database is locked`** on `execute_batch`.
- MCP **09:44:43**: `health` **0.000s** (fast path).
- MCP **09:44:50–09:44:54**: **`cst_save_tree` → Connection refused** in `validate_params` → `get_project` → `rpc_client.call("select")`.
- Driver **09:44:58**: **`Database driver started`** (restart); socket path per logs under `/tmp/code_analysis_db_drivers/`.

### Episode B (~18:26–18:27)

- MCP: `cst_save_tree` **18:26:37**; driver **`handle_execute_batch n_ops=752`** in open transaction **18:26:50**.
- Driver: **`database is locked`** then **18:27:48** **`Database driver started`**.
- MCP **18:27:10–18:27:24**: **`cst_save_tree` → Connection refused** (same stack as Episode A).

### Cross-cutting

- Pervasive **`FOREIGN KEY constraint failed`** (driver + file watcher in `mcp_server.log`) — DB integrity stress.
- **Proxy heartbeats** to external proxy **acknowledged** during failures — **no `ServerNotFound` in repo logs**; registration miss **not reproduced** in this log set.
- **Root cause (log-backed):** **`ECONNREFUSED`** aligns with **driver restart / dead socket window** after **`database is locked`** and heavy/long **`execute_batch`** (752 ops) and FK-failure stress; **not** HTTP health path.

### Narrowest remaining gaps

- Driver **exit reason** (signal vs watchdog) not always in sampled lines; **`logs/code_analysis.log`** missing.
- **`SERVER_NOT_FOUND`**: capture **client-side or external MCP catalog** logs if issue recurs — not in repo `logs/*.log` for this analysis.

### Registration-delay hypothesis (log-backed timing, `researcher_code`)

**Question:** Is **`SERVER_NOT_FOUND`** plausibly **only** “not finished re-registering yet” (startup race)?

**Findings (workspace `logs/`, 2026-04-04):**

- **No** `SERVER_NOT_FOUND` / `ServerNotFound` strings in **`logs/**/*.log`**.
- **Latest restart cycle** (`mcp_server.log`, ~**20:02:35**): `Daemon main()` → Hypercorn **`Running on`** → **`POST .../register` HTTP 200** → **`Successfully registered with proxy`** → **heartbeat 200** — all **same second** as bind (**20:02:39**). Earlier same-day restarts (e.g. **05:12** after unregister) show the same pattern.
- **UUID warning:** `Invalid UUID format in registration.server_id: code-analysis-server` at startup — **registration still HTTP 200** in sampled lines.
- **Historical contrast:** `mcp_proxy_adapter_error.log` **2026-03-16** — re-registration failed when proxy reported backend URL **not available** (different failure mode than “delay”).

**Verdict:** **“Simply not yet registered” is neither supported nor contradicted** for the **user-observed `SERVER_NOT_FOUND`** (no log line). For **2026-04-04** successful cycles, logs **contradict** a **multi-second registration delay** — registration is **immediate** after listen in these traces. **Unproven** for the IDE symptom without **client or 172.28.0.2:3004 proxy** logs.

**Missing evidence:** Cursor MCP / external OpenAPI proxy access logs; optional **`logs/code_analysis.log`** (configured but absent).

### Post-success `SERVER_NOT_FOUND` / catalog inconsistency (refocus, `researcher_code`)

**Hypothesis:** After commands already succeeded, **`SERVER_NOT_FOUND`** likely means **proxy/catalog inconsistency** (e.g. 500), not benign delay; **reappearance** after “not found” would imply **bug/inconsistency**.

**Log findings (workspace `logs/`):**

- **No** literal **`SERVER_NOT_FOUND` / `ServerNotFound`**; **no** HTTP **non-2xx** on `register`/`heartbeat` in **`mcp_server.log`** samples; heartbeats **200** around examined windows.
- **Last success before failure (example ~03:20):** heartbeat **200** + **`select success`** RPC lines, then **`execute_batch` → FOREIGN KEY** / batch queue failed — **DB path**, not proxy unregister in logs.
- **Cannot** confirm **500** on proxy or “reappears after not found” from repo logs alone; **external proxy** (`172.28.0.2:3004`) and **Cursor MCP client** traces **missing**.

**Verdict:** **Bug/inconsistency for `SERVER_NOT_FOUND` after prior success — unproven** in repo logs (symptom not recorded). **Contradicted as sole explanation** for the **documented** 2026-04-04 failures: evidence points to **DB/FK** while **proxy heartbeats stay 200**.

## Dependencies

- none (preemptive investigation).

## Parallelization note

- N/A (single diagnosis stream).

## Expected outcome

- Concrete **root cause classification** with evidence **or** narrowest **blocker** for further disambiguation — satisfied by delegated `researcher_code` report consolidated upward.

## Correction items

- **Addressed (repair batch):** transient **RPC connect refused** retry added to **`BaseMCPCommand._validate_project_id_exists`** (same policy as `cst_save_tree` execute); **`RPCClient.health_check`** probes Unix socket **listen** accept, not only path existence. Tests added/updated. **Commit:** `9cd2fcd9b3f504637af87db3125d042d2f44ed3a` — `fix: retry transient RPC connect refused in project validation (cst_save_tree path)`.

## Questions / escalation rule

- **Global orchestrator:** If repair requires changing `mcp_proxy_adapter` distribution vs vendored copy, proxy registration contract, or `tech_spec` acceptance criteria — escalate.
- **Operational:** Live confirmation of driver PID, `*_driver.sock` listener, driver logs, and proxy registry snapshot — requires environment access or `tester_ca`-mediated checks when reproduction is needed.

## Repair batch and revalidation (completed)

- **Scope:** DB-driver / socket lifecycle around **`cst_save_tree`** pre-execute validation only; no driver queue or FK/schema rewrite in this batch.
- **Guarded `vast_srv` revalidation (`tester_ca`):** `project_id` `c86dded6-6f93-4fb0-be54-b6d7b739eeb9`; `cst_load_file` → `cst_save_tree` (`validate=true`) on `add_full_queue_support/__init__.py`; `format_code`, `lint_code` — **PASS**; **no** `Connection refused` / **SERVER_NOT_FOUND** in MCP responses.
- **Out of scope / follow-up if logs recur:** SQLite **`database is locked`** / **FOREIGN KEY** stress, driver **exit reason** — separate batch if needed.

## Next actions (remaining global backlog)

- Resume **`fix_vast_srv_server_only_phase1`** fix batches under server-only rules when the parent orchestrator schedules them; monitor logs for FK/lock if instability returns.
