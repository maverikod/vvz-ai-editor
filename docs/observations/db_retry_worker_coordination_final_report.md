# Final report — DB retry & worker coordination

**Observations:** `docs/observations/db_retry_worker_coordination.md`
**Date:** 2026-04-26 (matrix rows Worker-10 / MCP-2–5 refreshed against live MCP log slice + local pytest)

## 1. Summary

Implementation is covered by the pytest bundle in the repository. MCP smoke (Step 30), project-management dry-runs (Step 33), and clear_trash dry-run (Step 34) were exercised earlier via proxy. **2026-04-26:** `view_worker_logs` on `code-analysis-server` returned real `[WORKER_COORD]` lines from `file_watcher` and `indexing_worker` (Worker-10 / coordinator log criterion). `qa_mcp_plan_hooks` is present but returned `QA_MCP_HOOKS_DISABLED` without `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1`; `[DB_RETRY]` did not appear in the sampled tails of `mcp_server`, `indexing_worker`, or `file_watcher`, and `database_driver.log` is absent on this host. **Backend-2:** `CODE_ANALYSIS_POSTGRES_TEST_DSN` was unset here; the running server reports `database_driver: postgres` in `get_database_status`, but pytest PG parity was not re-run in this refresh.

## 2. Tests run (exact command)

```bash
cd /home/vasilyvz/projects/tools/code_analysis && source .venv/bin/activate && \
pytest tests/test_database_driver_transient_errors.py tests/test_postgres_driver_retry.py \
  tests/test_rpc_logical_write_retry.py tests/test_database_driver_config_validator_retry.py \
  tests/test_logical_write_program_metadata.py tests/test_worker_project_activity.py \
  tests/test_sqlite_retry_compatibility.py tests/test_watcher_indexer_project_coordination.py \
  tests/test_postgres_retry_contract_integration.py -q --tb=no
```

**Result:** `90 passed, 11 skipped in 1.62s` (skips = PG DSN + parametrized worker PG branch).

**Supplement (2026-04-26):** `pytest tests/test_qa_driver_db_retry_injection.py tests/test_qa_rpc_db_retry_hooks.py -q` → `3 passed` (QA RPC + driver `[DB_RETRY]` injection).

## 3. MCP commands (2026-04-25; log slice 2026-04-26)

- `health`, `list_watch_dirs`, `list_projects`, `list_projects(include_deleted)`, `list_trashed_projects`, `get_database_status`, `queue_list_jobs`, `list_project_files` (plan glob)
- **2026-04-26:** `view_worker_logs` (`log_id` `file_watcher` / `indexing_worker`, `search_pattern` `\[WORKER_COORD\]`, `tail` 3000, `limit` 50); `qa_mcp_plan_hooks` (returned `QA_MCP_HOOKS_DISABLED` without QA env)
- Step 33: `project_set_mark_del` dry_run+queue (`job_id=project_set_mark_del_46b4f2c1`); `delete_unwatched_projects` dry_run+queue (`job_id=delete_unwatched_projects_8047211b`); `set_project_processing_paused` true/false; `list_projects` verify
- Step 34: `clear_trash` dry_run+queue (`job_id=clear_trash_77a8169b`)

**Queue inner success:** all three jobs above reported `inner_success=true` in `queue_get_job_status` (see observations).

## 4. Step 35 acceptance matrix

| Criterion | Status | Evidence command | Evidence result | Verification command | Verification result | Notes |
|-----------|--------|--------------------|-----------------|----------------------|---------------------|-------|
| Retry-1 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | PG transient classified by SQLSTATE not string parsing |
| Retry-2 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | SQLSTATE policy 40P01 40001 55P03 57014 timeout-only |
| Retry-3 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Driver retry only self-managed no external transaction_id |
| Retry-4 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Driver rollback before each retry |
| Retry-5 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | No driver retry when commit_outcome_unknown |
| Retry-6 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | RPC logical write retries whole transaction from begin |
| Retry-7 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Unknown commit not retried; structured retryable=false |
| Retry-8 | passed | §Global pytest 2026-04-25 (see observations.md) | 9+7+7 tests green in bundle | §Global pytest 2026-04-25 (see observations.md) | same | DB_RETRY logs backend layer operation attempt sqlstate kind |
| Config-1 | passed | §Global pytest 2026-04-25 (see observations.md) | validator + metadata tests | §Global pytest 2026-04-25 (see observations.md) | same | Canonical write_retry_* and lock/statement timeout fields |
| Config-2 | passed | §Global pytest 2026-04-25 (see observations.md) | validator + metadata tests | §Global pytest 2026-04-25 (see observations.md) | same | Config path code_analysis.database.driver.config |
| Config-3 | passed | §Global pytest 2026-04-25 (see observations.md) | validator + metadata tests | §Global pytest 2026-04-25 (see observations.md) | same | Aliases retry_attempts retry_delay_seconds rejected |
| Config-4 | passed | §Global pytest 2026-04-25 (see observations.md) | validator + metadata tests | §Global pytest 2026-04-25 (see observations.md) | same | Invalid config rejected by validator tests |
| Worker-1 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | Coordination scoped by project_id not global server |
| Worker-2 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | One mutating pipeline per project at a time |
| Worker-3 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | Different projects not unnecessarily blocked |
| Worker-4 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | Watcher LockManager remains process guard |
| Worker-5 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | owner_type only watcher indexer command |
| Worker-6 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | No production auto_indexing owner |
| Worker-7 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | Lease API used watcher indexer mutating commands |
| Worker-8 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | No direct project_activity_locks manipulation outside c |
| Worker-9 | passed | §Global pytest 2026-04-25 (see observations.md) | worker_project_activity + watcher_coord tests | §Global pytest 2026-04-25 (see observations.md) | same | Coordinator only mutates project_activity_locks |
| Worker-10 | passed | MCP `view_worker_logs` code-analysis-server 2026-04-26 (observations.md § Step 32) | `log_id=file_watcher` + `indexing_worker`, `search_pattern=\\[WORKER_COORD\\]`, tail 3k, limit 50 each → 50 lines/file_watcher sample; indexer lines show try_acquire/heartbeat/release, `owner_type=indexer`, `activity=indexer_processing` | same MCP commands | fields include project_id owner_type owner_id activity result | Live coordinator logs; not every op type (e.g. busy) in tail |
| Watcher-1 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | No whole watch-dir scan under one lease |
| Watcher-2 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | FS scan read-only w.r.t. per-project DB mutation |
| Watcher-3 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Per-project phases acquire lease for current project_id |
| Watcher-4 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Busy project skipped without blocking others |
| Watcher-5 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Staged candidate set one project at a time |
| Watcher-6 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | POSIX relative paths |
| Watcher-7 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Paths outside root rejected |
| Watcher-8 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Ignore before mutation |
| Watcher-9 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Ignore-exception after ignore |
| Watcher-10 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Insert new before update changed before absent |
| Watcher-11 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Changed/deleted only affected rows |
| Watcher-12 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Chunks only for confirmed changed/deleted |
| Watcher-13 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | Watcher logical write idempotent after retry |
| Watcher-14 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | PG watcher SQL no raw julianday on PG path |
| Watcher-15 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + scanner tests in bundle | §Global pytest 2026-04-25 (see observations.md) | same | No uncoordinated daemon auto-indexing thread |
| Indexer-1 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | Indexer acquires lease before mutating files chunks vec |
| Indexer-2 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | owner_type indexer activity indexer_processing |
| Indexer-3 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | Indexer skips when other owner holds project |
| Indexer-4 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | Indexer narrow file/chunk writes |
| Indexer-5 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | Auto-created projects normal indexer path |
| Indexer-6 | passed | §Global pytest 2026-04-25 (see observations.md) | watcher_coord + indexing worker unit path | §Global pytest 2026-04-25 (see observations.md) | same | No auto_indexing indexing mutations |
| Backend-1 | passed | §Global pytest 2026-04-25 (see observations.md) | bundle | §Global pytest 2026-04-25 (see observations.md) | same | SQLite tests pass retry locks staging lifecycle |
| Backend-2 | skipped | `echo $CODE_ANALYSIS_POSTGRES_TEST_DSN` empty 2026-04-26; `pytest … -k postgres` → skips | no DSN in this workspace | MCP `get_database_status` 2026-04-26 | `database_driver=postgres` on server | Run `scripts/run_pg_integration_parity.sh` when DSN exported |
| Backend-3 | passed | §Global pytest 2026-04-25 (see observations.md) | skips explicit in pytest output | §Global pytest 2026-04-25 (see observations.md) | same | PG-only tests skipped not passed without DSN |
| Backend-4 | passed | §Global pytest 2026-04-25 (see observations.md) | bundle | §Global pytest 2026-04-25 (see observations.md) | same | Backend SQL isolated helpers/branches |
| Backend-5 | passed | §Global pytest 2026-04-25 (see observations.md) | bundle | §Global pytest 2026-04-25 (see observations.md) | same | PG mode no SQLite-only constructs |
| Backend-6 | passed | §Global pytest 2026-04-25 (see observations.md) | bundle | §Global pytest 2026-04-25 (see observations.md) | same | SQLite no PG-only syntax unless isolated |
| MCP-1 | passed | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | Step 30 table all PASS | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | health ok | Smoke |
| MCP-2 | partial | MCP `qa_mcp_plan_hooks` 2026-04-26 | `QA_MCP_HOOKS_DISABLED` without env; no `[DB_RETRY]` in `view_worker_logs` tails (mcp_server, indexing_worker, file_watcher); no `database_driver.log` file | `pytest tests/test_qa_driver_db_retry_injection.py tests/test_qa_rpc_db_retry_hooks.py -q` | 3 passed | Step 31: enable QA env + driver log capture to close MCP-only gap |
| MCP-3 | partial | MCP `view_worker_logs` 2026-04-26 | Scenario A: no `result='busy'` / `watcher skip` / `indexer skip` in searched tails | `pytest tests/test_watcher_indexer_project_coordination.py -q` | coordination tests green | Same-project exclusion: pytest + optional `qa_mcp_plan_hooks` with QA env |
| MCP-4 | passed | MCP `view_worker_logs` `file_watcher` `[WORKER_COORD]` 2026-04-26 (observations.md) | Same tail shows sequential acquire/release across **different** `project_id` values in one watcher cycle | same | multi-project staging, not one global lock | Step 32 scenario B (log-level) |
| MCP-5 | partial | MCP logs 2026-04-26 | No MCP-only proof of insert-before-update ordering or ignore-exception layout | §Global pytest bundle | `test_watcher_indexer_project_coordination` | Step 32 scenario C/D: still pytest / controlled FS |
| MCP-6 | passed | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | Step 33 dry_run + pause inner_success | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | list_projects verify pause | Safe mgmt |
| MCP-7 | passed | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | clear_trash dry_run inner_success | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | Would remove 2 (dry) | No live clear |
| MCP-8 | passed | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | queue_get_job_status inner_success true | MCP call_server code-analysis-server (2026-04-25 evidence in observations.md) | same for 3 jobs | Queue rule |
| Doc-1 | passed | Write | this observations file refreshed | Read | templates + steps 30-34 | Per-step: major steps documented |
| Doc-2 | passed | n/a | no bugs filed this refresh | n/a | n/a | N/A |
| Doc-3 | passed | Write | this final report | Read | matrix present |  |
| Doc-4 | passed | Write | 61 rows | python assert | len=61 | Doc-4 self |

## 5. Roll-up

- **Step 35 (Worker coordination logs — criterion Worker-10):** Met with MCP evidence (`view_worker_logs`, 2026-04-26) as documented in observations.
- **Step 35 (MCP acceptance rows):** MCP-1 and MCP-4–8 have MCP command evidence as listed in the matrix. **MCP-2, MCP-3, and MCP-5 are partial** for the reasons in the Notes column (no `[DB_RETRY]` in sampled server log files without QA injection; no `result='busy'` in sampled tails; watcher ordering / auto-create path not isolated to a single MCP scenario). **Backend-2** remains skipped in this workspace until `CODE_ANALYSIS_POSTGRES_TEST_DSN` is set and `scripts/run_pg_integration_parity.sh` (or equivalent) is run.
- **Risks:** MCP catalog project `code-analysis-server` may lag the open editor tree; use `scripts/sync_mcp_registered_project_mirror.sh` when file-level parity matters.

## 6. Safety

- No commands targeted `vast_srv` for mutation.
- `.venv` not modified by this documentation refresh.

## 7. Files by area (summary)

- **DB exceptions / PG driver / RPC:** `code_analysis/core/database_driver_pkg/` (exceptions, postgres_*, rpc_handlers_*), `code_analysis/core/retry_policy.py`
- **Client / logical write metadata:** `code_analysis/core/database_client/client_operations.py`, `code_analysis/core/database/logical_write_program.py`
- **Config validator:** `code_analysis/core/config_validator/section_database_driver.py`
- **Activity locks / coordinator:** `code_analysis/core/database/schema_definition*.py`, migrations, `code_analysis/core/worker_project_activity.py`
- **Watcher / indexer:** `code_analysis/core/file_watcher_pkg/`, `code_analysis/core/indexing_worker_pkg/processing.py`
- **Tests:** `tests/test_*transient*`, `tests/test_postgres_driver_retry.py`, `tests/test_rpc_logical_write_retry.py`, `tests/test_worker_project_activity.py`, `tests/test_watcher_indexer_project_coordination.py`, `tests/test_sqlite_retry_compatibility.py`, etc.
- **Docs / evidence:** this report + `docs/observations/db_retry_worker_coordination.md`