# Parallelization waves 7-8

Previous: [Waves 4-6](PARALLELIZATION_WAVES_4_6.md). Next: [Assignment matrix](PARALLELIZATION_ASSIGNMENT_MATRIX.md).

## Wave 7: integration and full tests

### Agent M: PostgreSQL integration contract

Starts after Agents A, C, and D are merged.

Owns:
- Step 27 PostgreSQL integration contract tests.

Files:
- `tests/test_postgres_retry_contract_integration.py`

Waits for:
- Agent A PostgreSQL classification.
- Agent C PostgreSQL driver retry.
- Agent D RPC retry and structured errors.

Can run in parallel with:
- Agent N full test orchestration, after implementation merge.

Deliverable:
- PostgreSQL integration test passes when environment is available.
- If PostgreSQL is unavailable, test is skipped with explicit reason.
- SQLSTATE is proven to reach structured RPC details.

### Agent N: full test orchestration

Starts after implementation agents are merged.

Owns:
- Running Step 20 through Step 27 test files.
- Recording all test commands and results in Step 28 observations.

Waits for:
- Agents A through M source/test files.

Blocks:
- MCP verification agents.

Deliverable:
- Full relevant test list with pass/fail/skip evidence.
- Confirmation no `.venv`, `venv`, `site-packages`, or installed package files were edited.

## Wave 8: MCP verification and reporting

These steps are mostly sequential because MCP checks depend on the server seeing the merged source.

### Agent O: MCP source and smoke checks

Starts after merge and server reload/restart if needed.

Owns:
- Step 29 pre-MCP source verification.
- Step 30 MCP smoke regression.

Waits for:
- Implementation merged.
- Test pass or accepted skip evidence from Agent N.

Blocks:
- Agent P.

Deliverable:
- MCP read/query commands prove running server sees changed source markers.
- MCP smoke commands pass.

### Agent P: MCP behavior checks

Starts after Agent O.

Owns:
- Step 31 MCP retry behavior.
- Step 32 MCP worker coordination.

Waits for:
- Agent O source verification and smoke success.

Blocks:
- Agent R final acceptance.

Deliverable:
- `[DB_RETRY]` is visible in controlled retry scenario.
- `[WORKER_COORD] watcher skip ...` and `[WORKER_COORD] indexer skip ...` are visible in logs.
- Structured failure or success-after-retry is proven through MCP behavior.

### Agent Q: safe lifecycle checks

Starts after Agent O smoke success.

Owns:
- Step 33 safe project-management regression.
- Step 34 clear_trash safety when applicable.

Waits for:
- Agent O MCP smoke success.

Can run in parallel with:
- Agent P, if using separate safe targets and coordination is clear.

Deliverable:
- Safe project-management commands still work.
- Any destructive check uses only validated safe targets.
- No destructive operation uses `vast_srv`.
- Queue checks include inner command success fields.

### Agent R: final acceptance and report

Starts after Agents N, P, and Q complete.

Owns:
- Step 35 final acceptance criteria.
- Step 36 final report.

Waits for:
- Agent N test evidence.
- Agent P MCP behavior evidence.
- Agent Q lifecycle evidence or explicit not-applicable note.
- Agent Lead observations file.

Deliverable:
- Final report maps every acceptance criterion to evidence.
- Failed, skipped, and not-applicable items are not hidden.

## Wave 7-8 merge and execution rule

Do not run MCP behavior checks until MCP source verification proves the server sees merged source. Do not write final acceptance until tests, MCP behavior, and safety checks have evidence in the observations file.
