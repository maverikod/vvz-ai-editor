# Compact assignment matrix

Previous: [Waves 7-8](PARALLELIZATION_WAVES_7_8.md). Next: [Parallelization index](PARALLELIZATION.md).

## Matrix

| Agent | Steps | Start condition | Main files |
|---|---:|---|---|
| Lead | 28, coordination | now | `docs/observations/db_retry_worker_coordination.md` |
| A | 01, 02, 20 | now | `exceptions.py`, `postgres_run.py`, transient tests |
| B | 03, 04 | now | `postgres_transactions.py`, `retry_policy.py` |
| E | 08, 09, 23 | now | `logical_write_program.py`, `client_operations.py`, metadata tests |
| F | 10, 22 | after canonical names confirmed | config validator and tests |
| G | 11, 12 | now | schema definition and migrations |
| C | 05 | after A+B | `postgres.py` |
| D | 06, 07, 21 | after A+B, preferably C | RPC handlers and logical write retry tests |
| H | 17, 18, 19, 26 | after A+B | SQLite, base driver, client transient fallback, SQLite tests |
| I | 13, 24 | after G | worker coordinator and tests |
| J | 14, 15 | after D+E+I | watcher scan and ignore purge |
| K | 16 | after I | indexer processing |
| L | 25 | draft after I, final after J+K | watcher/indexer coordination tests |
| M | 27 | after A+C+D | PostgreSQL integration tests |
| N | 20-27 run | after implementation merge | test orchestration and observations |
| O | 29, 30 | after merge/reload | MCP source and smoke checks |
| P | 31, 32 | after O | MCP retry and worker coordination behavior |
| Q | 33, 34 | after O | safe lifecycle and clear_trash checks |
| R | 35, 36 | after N+P+Q | final acceptance and report |

## Immediate distribution

Give these agents work first:

1. Agent A: Steps 01, 02, 20.
2. Agent B: Steps 03, 04.
3. Agent E: Steps 08, 09, 23.
4. Agent F: Steps 10, 22.
5. Agent G: Steps 11, 12.

These five blocks can run in parallel with low file-conflict risk.

## Second distribution

Start these after first dependencies are ready:

1. Agent C after A+B.
2. Agent H after A+B.
3. Agent I after G.
4. Agent D after A+B, preferably after C.

## Third distribution

Start these after coordinator and RPC/client dependencies are ready:

1. Agent J after D+E+I.
2. Agent K after I.
3. Agent L after I for drafting, final after J+K.
4. Agent M after A+C+D.

## Final distribution

Start only after implementation merge and local tests:

1. Agent N runs and records tests.
2. Agent O verifies MCP source visibility and smoke commands.
3. Agent P verifies retry and worker coordination behavior through MCP.
4. Agent Q performs safe lifecycle checks if applicable.
5. Agent R writes final acceptance and report.

## Conflict avoidance

- Only Agent A edits `exceptions.py` and `postgres_run.py`.
- Only Agent B edits `retry_policy.py` and `postgres_transactions.py`.
- Only Agent C edits `postgres.py`.
- Only Agent D edits RPC handlers.
- Only Agent E edits logical-write client/type files.
- Only Agent G edits schema/migrations.
- Only Agent I edits `worker_project_activity.py`.
- Only Agent J edits watcher files.
- Only Agent K edits indexer processing.

## Safety reminders

- Do not edit `.venv`, `venv`, `site-packages`, or installed packages.
- Do not run destructive operations on `vast_srv`.
- For queue checks, inspect inner command success, not just outer queue status.
- Every completed block must have verification evidence in Step 28 observations.
