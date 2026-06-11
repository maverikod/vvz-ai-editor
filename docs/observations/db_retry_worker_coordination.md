# Observations — DB retry & worker coordination plan

**Plan:** `docs/plans/db_retry_worker_coordination_100_qwen/`  
**Final report (Step 36 matrix):** `docs/observations/db_retry_worker_coordination_final_report.md`  
**Evidence refresh:** 2026-04-25 (MCP / pytest); **2026-04-26** — Worker-10 / Step 32 log slice via `view_worker_logs` (see § below).

---

## Step 28 — Required templates

### Bug report

```text
Command:
Expected:
Actual:
Error:
Root cause:
Fix:
Post-fix verification:
Status:
```

### Non-bug verification

```text
Step:
Command:
Expected:
Actual:
Verification command:
Verification result:
Status:
```

### Skip

```text
Step:
Skipped item:
Reason:
Mandatory alternative evidence:
Status:
```

---

## Global pytest bundle (verification for implementation criteria)

**Command:**

```bash
cd /home/vasilyvz/projects/tools/code_analysis && source .venv/bin/activate && \
pytest tests/test_database_driver_transient_errors.py tests/test_postgres_driver_retry.py \
  tests/test_rpc_logical_write_retry.py tests/test_database_driver_config_validator_retry.py \
  tests/test_logical_write_program_metadata.py tests/test_worker_project_activity.py \
  tests/test_sqlite_retry_compatibility.py tests/test_watcher_indexer_project_coordination.py \
  tests/test_postgres_retry_contract_integration.py -q --tb=no
```

**Expected:** exit code 0; PostgreSQL-only rows skipped when `CODE_ANALYSIS_POSTGRES_TEST_DSN` unset (not counted as pass for PG behavior).

**Actual:** `90 passed, 11 skipped in 1.62s` (exit 0).

**Verification command:** same as above with `-v` on failure.

**Verification result:** green on this run.

**Status:** PASS (with explicit PG skips).

---

## 4. `code-analysis-server` project — `list_projects` vs `list_projects(include_deleted=true)`

### Non-bug verification

```text
Step: explain / list_projects semantics (2026-04-25)
Command: MCP call_server code-analysis-server list_projects {}
Expected: success=true; structured list of operational projects per server rules.
Actual: success=true; count=8; projects include vast_srv, repro_*, watcher_* etc.; NO row with name "code-analysis-server".
Verification command: MCP call_server list_projects {"include_deleted": true}
Verification result: success=true; count=10; ADDITIONAL rows: id a2c4c42a-342e-453f-8884-a1674bdaec2f name code-analysis-server root_path .../test_data/code-analysis-server deleted=false processing_paused=false; id 900fe94a-1d93-41be-bba1-0ebddbd1e5d1 name repro_file_mgmt_test (same flags).
Status: PASS — documented behavior: default list excludes some projects that still exist in DB with deleted=false; include_deleted=true widens the catalog (per command schema: includes rows such as projects that only have trashed file rows / full DB listing). Both named projects are NOT soft-deleted (deleted=false); they appear only in the wider query.
```

---

## 5. `repro_file_mgmt_test` — trash vs `include_deleted`

### Non-bug verification

```text
Step: repro_file_mgmt_test trash + DB row (2026-04-25)
Command: MCP list_trashed_projects {}
Expected: Structured trash list; interpret alongside list_projects.
Actual: count=2 items: (1) folder_name 900fe94a-1d93-41be-bba1-0ebddbd1e5d1 path .../data/trash/900fe94a-1d93-41be-bba1-0ebddbd1e5d1 deleted_at null; (2) repro_mini_restore_2_2026-04-24T16-02-43Z ...
Verification command: MCP list_projects {"include_deleted": true, "name_contains": "repro_file_mgmt_test"}
Verification result: Live project row present: id 900fe94a-1d93-41be-bba1-0ebddbd1e5d1 deleted=false processing_paused=false (after pause/unpause check below).
Status: PASS — Explanation: trash folder named by UUID is an on-disk snapshot under trash_dir; it can coexist with an active `projects` row for repro_file_mgmt_test. clear_trash dry_run reports it would remove both trash folders; live project remains until a real delete lifecycle is executed.
```

---

## Step 30 — MCP smoke regression (read-only + plan files)

**Transport:** `call_server(server_id="code-analysis-server", copy_number=1, ...)`.

| # | Command | Params | Expected | Actual | Status |
|---|---------|--------|----------|--------|--------|
| 1 | `health` | `{}` | success | `status=ok`, `proxy_registration.registered=true`, queue_ready | PASS |
| 2 | `list_watch_dirs` | `{}` | success | 1 watch dir `test_data` | PASS |
| 3 | `list_projects` | `{}` | success | 8 projects | PASS |
| 4 | `list_projects` | `{"include_deleted": true}` | success | 10 projects | PASS |
| 5 | `list_trashed_projects` | `{}` | success | 2 items | PASS |
| 6 | `get_database_status` | `{}` | success | postgres driver, totals, samples | PASS |
| 7 | `queue_list_jobs` | `{"limit": 5}` | success | jobs=[], total_count=0 | PASS |
| 8 | `list_project_files` | project `a2c4c42a-342e-453f-8884-a1674bdaec2f`, pattern `docs/plans/db_retry_worker_coordination_100_qwen/*` | README + architecture_addendum + step_*.md visible | count=46 total=46 offset=0 includes README.md, architecture_addendum.md, step_01…step_36 | PASS |

**Queue rule (Step 30):** N/A for rows 1–8 (no queued mutation in smoke). Completed jobs in Step 33/34 checked with `inner_success` / `command_success` below.

---

## Step 32 — MCP worker coordination

```text
Step: 32
Status (2026-04-26): **PARTIAL** — live `[WORKER_COORD]` lines captured via MCP (Worker-10 satisfied); full scenarios A–D per plan (same-project *busy* from two owners, watcher ordering layout, auto-create path) still rely on pytest / optional `qa_mcp_plan_hooks` with QA env.
```

### Live MCP log verification — `[WORKER_COORD]` (2026-04-26)

**Commands** (proxy `call_server` → `code-analysis-server`, `copy_number=1`):

1. `view_worker_logs` — `{"log_id": "file_watcher", "search_pattern": "\\\\[WORKER_COORD\\\\]", "tail": 3000, "limit": 50}`  
   - **Result:** `success=true`, `filtered_lines=50`; sample lines include `op=try_acquire` / `op=release`, `owner_type='watcher'`, `activity='watcher_staging'`, `result='acquired'` / `result='ok'`, multiple distinct `project_id` values in one tail window (e.g. `c86dded6-6f93-4fb0-be54-b6d7b739eeb9`, `5afbe22d-e0df-4f71-a6a4-58a48b93675f`, `22619777-74a9-4d0e-a49b-af0fabd8ab1f`, …).

2. `view_worker_logs` — `{"log_id": "indexing_worker", "search_pattern": "\\\\[WORKER_COORD\\\\]", "tail": 3000, "limit": 50}`  
   - **Result:** `success=true`; lines include `owner_type='indexer'`, `activity='indexer_processing'`, `op=try_acquire` / `op=heartbeat` / `op=release`, `result='acquired'` / `result='ok'`.

**Scenario mapping (Step 32 plan vs this slice):**

| Plan scenario | MCP / log evidence (2026-04-26) |
|---------------|----------------------------------|
| **A** Same-project contention (second owner skips) | Not observed in tail: no `result='busy'`, no `watcher skip` / `indexer skip` in last 8k–25k lines of `file_watcher` / `indexing_worker`. Use `qa_mcp_plan_hooks` with `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1` for deterministic `try_acquire` busy, or wait for live contention. |
| **B** Different projects not globally blocked | **Supported by logs:** same watcher cycle shows sequential `try_acquire`/`release` across different `project_id` values (not a single global lock). |
| **C** Watcher write ordering + ignore / ignore-exception | **Not** proven by this log-only pass; continue to use `tests/test_watcher_indexer_project_coordination.py` and controlled FS layouts. |
| **D** Auto-created project → normal indexer path | **Not** proven by dedicated MCP run; indexer logs show normal `indexer_processing` lease pattern for `vast_srv` sample. |

### Step 31 — MCP retry (`[DB_RETRY]`)

| Check | Command | Result |
|-------|---------|--------|
| Deterministic hook present | `qa_mcp_plan_hooks` `{"scenario":"both","inject_remaining":1,"project_id":"<existing>","trigger_touch_project_row":true}` | `success=false`, `code=QA_MCP_HOOKS_DISABLED` — server process did **not** have `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1`. |
| `[DB_RETRY]` in server log files | `view_worker_logs` `worker_type=database_driver` / `mcp_server` / `indexing_worker` with `search_pattern=\\\\[DB_RETRY\\\\]`, `tail` 8k–20k | **No matches** in available tails; `database_driver.log` path **missing** on this deployment (in-process / PG driver may not write that file). |
| Repo tests | `pytest tests/test_qa_driver_db_retry_injection.py tests/test_qa_rpc_db_retry_hooks.py -q` | Driver + RPC QA path green locally. |

---

## Step 33 — Safe project-management regression

**Target validation (before mutating checks):** `repro_file_mgmt_test` — `project_id=900fe94a-1d93-41be-bba1-0ebddbd1e5d1`, `root_path=/home/vasilyvz/projects/tools/code_analysis/test_data/repro_file_mgmt_test`, **not** `vast_srv`. From `project_set_mark_del` dry_run job: `files_count=4`, `chunks_count=0`, `deleted=false` prior to pause experiment.

| Check | Command | Queue job_id | Outer status | Inner success | Result summary |
|-------|---------|--------------|--------------|---------------|----------------|
| mark_del dry_run | `project_set_mark_del` + `use_queue` | `project_set_mark_del_46b4f2c1` | completed 100% | `inner_success=true`, `command_success=true` | Would soft-delete repro (dry_run) |
| delete_unwatched dry_run | `delete_unwatched_projects` + `use_queue` | `delete_unwatched_projects_8047211b` | completed | `inner_success=true` | deleted_count=0, kept_count=10 |
| pause | `set_project_processing_paused` | — | sync | `success=true` | First attempt: param `paused` → MCP error *required parameter 'processing_paused' is missing*; **retry** with `processing_paused=true` → success |
| verify pause | `list_projects` | — | — | — | `processing_paused=true` |
| unpause | `set_project_processing_paused` `processing_paused=false` | — | sync | success | resumed |
| verify unpause | `list_projects` | — | — | — | `processing_paused=false` |

**Coordination rule note:** Step 33 commands above are dry_run or processing flags; lease rule (13) not asserted via MCP here — see final report Worker-7/8 notes.

---

## Step 34 — clear_trash PostgreSQL safety

| Check | Command | Queue job_id | Inner success | Notes |
|-------|---------|--------------|---------------|-------|
| clear_trash dry_run | `clear_trash` `{"dry_run":true}` + `use_queue` | `clear_trash_77a8169b` | `inner_success=true` | `Would remove 2 item(s)` — trash snapshots only; **no** `dry_run=false` executed (trash contained 2 unrelated snapshots). |

**Post-check:** `list_trashed_projects` not re-run in this session after dry_run (dry_run does not remove). Implementation inspection for PG/SQLite isolation: recorded as **code review / prior plan work** — see final report Backend/MCP notes.

---

## Queue evidence detail (Step 33 / 34 jobs)

Recorded **job_id** values for reproduction:

- `project_set_mark_del_46b4f2c1`
- `delete_unwatched_projects_8047211b`
- `clear_trash_77a8169b`

**`project_set_mark_del_46b4f2c1`:** outer `status=completed`, `progress=100`; `inner_success=true`, `command_success=true`; nested command result `success=true`, `dry_run=true`, `project_id=900fe94a-1d93-41be-bba1-0ebddbd1e5d1`, `files_count=4`, `chunks_count=0`.

**`delete_unwatched_projects_8047211b`:** `inner_success=true`, `deleted_count=0`, `kept_count=10`.

**`clear_trash_77a8169b`:** `inner_success=true`, `dry_run=true`, `removed_count=2`, message `Would remove 2 item(s)` (trash snapshots: UUID folder + `repro_mini_restore_2_2026-04-24T16-02-43Z`).

---

## MCP proxy registration (context)

`health` → `proxy_registration.registered=true`, `proxy_url=https://127.0.0.1:3004`, `server_url=https://172.18.0.1:15000`.

---

## MCP QA hooks & registered-project mirror (Steps 31–32 supplement)

**Env / config:** `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1` **or** top-level **`"enable_qa_mcp_hooks": true`** in `config.json` (server sets the env during `apply_global_config` before workers start). Перезапустите процесс сервера из корня репозитория после смены флага.

| Mechanism | Purpose |
|-----------|---------|
| RPC `qa_set_db_retry_injections` | Arms SQLite/Postgres driver to raise one synthetic transient per configured count on the next self-managed writes → `[DB_RETRY]` in driver logs after a touch write. |
| MCP `qa_mcp_plan_hooks` | Calls the RPC arm + optional `UPDATE projects SET name = name WHERE id = ?`, then runs two `try_acquire_project_activity` calls with different `owner_id` → `[WORKER_COORD]` acquire/busy/release lines. |
| `scripts/sync_mcp_registered_project_mirror.sh` | Rsync primary repo into `test_data/code-analysis-server` (override dest with `CODE_ANALYSIS_MCP_MIRROR_ROOT`) so MCP `list_project_files` matches the editor tree. |
| `scripts/run_pg_integration_parity.sh` | Runs selected parity tests when `CODE_ANALYSIS_POSTGRES_TEST_DSN` is set. |

---

## Outstanding / honest gaps

- Step 31 **MCP-visible `[DB_RETRY]`:** enable `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1`, re-run `qa_mcp_plan_hooks`, then search logs (or configure `database_driver.log` if driver runs out-of-process).
- Step 32 **A / C / D** as scripted MCP-only proofs: still open; **B** partially covered by multi-project `[WORKER_COORD]` sequence (2026-04-26).
- **Backend-2 (pytest PG parity):** `CODE_ANALYSIS_POSTGRES_TEST_DSN` unset in this workspace — run `./scripts/run_pg_integration_parity.sh` when DSN is available (server already uses `database_driver: postgres` per `get_database_status`).
