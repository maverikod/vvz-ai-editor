# Step 35 - Final acceptance criteria

Previous: [Step 34](step_34_clear_trash_safety.md). Next: [Step 36](step_36_final_report.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md).

## Goal

Define the final acceptance gate for DB retry, logical-write retry, config validation, SQLite/PostgreSQL compatibility, and project-scoped worker coordination.

A criterion is accepted only when there is command evidence and separate read/log verification recorded in [Step 28](step_28_observations_document.md).

## Retry acceptance

1. PostgreSQL transient failures are classified by SQLSTATE and structured error details, not by upper-layer string parsing.
2. Retryable SQLSTATE policy is implemented exactly:
   - `40P01` deadlock;
   - `40001` serialization failure;
   - `55P03` lock not available;
   - `57014` query canceled only when caused by configured timeout, not manual/external cancel.
3. Driver-level retry happens only for self-managed operations without external `transaction_id`.
4. Driver-level retry attempts rollback/cleanup before every retry.
5. Driver-level retry does not retry when `commit_outcome_unknown=true`.
6. Logical-write RPC retry repeats the whole transaction from `begin_transaction()`, not one statement or one batch inside a failed transaction.
7. Unknown commit outcome is never retried blindly and returns structured error with `commit_outcome_unknown=true` and `retryable=false`.
8. Retry logs include `[DB_RETRY]` records with backend, layer, operation, attempt, SQLSTATE, and error kind.

## Config acceptance

1. Only canonical config fields are used:
   - `write_retry_attempts`
   - `write_retry_delay_seconds`
   - `write_retry_backoff_multiplier`
   - `write_retry_jitter_seconds`
   - `lock_timeout_seconds`
   - `statement_timeout_seconds`
2. Config path is exactly `code_analysis.database.driver.config.<field>`.
3. Deprecated aliases `retry_attempts` and `retry_delay_seconds` are rejected with a clear suggestion.
4. Invalid config is rejected by validator tests.

## Worker coordination acceptance

1. Coordination is scoped by `project_id`; the implementation does not globally serialize the whole server.
2. At any moment, only one worker pipeline may mutate one project.
3. Different projects are not unnecessarily blocked by the project-level lease.
4. Existing watcher `LockManager` remains as a watch-dir process guard.
5. Allowed production `owner_type` values are exactly `watcher`, `indexer`, and `command`.
6. `owner_type=auto_indexing` is not used by any production mutation path.
7. Project activity lease API is used by watcher, indexer, and mutating command paths that can overlap watcher/indexer state.
8. No production code outside the coordinator directly manipulates `project_activity_locks`.
9. Coordinator acquire/heartbeat/release changes only `project_activity_locks`.
10. `[WORKER_COORD]` logs prove acquire, busy/skip, heartbeat when applicable, and release behavior.

## Watcher acceptance

1. Watcher does not wrap a whole shared watch-dir scan in one project lease.
2. Project discovery and filesystem scanning are read-only with respect to per-project DB mutation state.
3. Per-project DB mutation phases acquire a project activity lease only for the currently mutated `project_id`.
4. A busy project is skipped for the current cycle without blocking unrelated projects.
5. Watcher builds a staged candidate set from filesystem results for one project at a time.
6. Candidate paths are normalized to project-relative POSIX paths.
7. Paths outside the target project root are rejected before staging.
8. Ignore patterns are applied before DB mutation.
9. Ignore-exception patterns are applied after ignore patterns and can re-include paths.
10. New file rows are inserted before changed rows are updated and before absent rows are marked/deleted.
11. Changed/deleted operations mutate only affected file rows.
12. Chunks are invalidated/deleted only for rows confirmed changed or deleted.
13. Re-running the same watcher logical write after a retry is idempotent.
14. PostgreSQL compatibility of watcher SQL is verified; SQLite-only constructs such as `julianday('now')` are removed from PostgreSQL paths or hidden behind backend-aware helpers.
15. Watcher no longer starts an uncoordinated daemon indexing thread.

## Indexer acceptance

1. Indexer acquires project activity lease before mutating files, chunks, vectors, indexes, or indexing flags.
2. Indexer uses `owner_type=indexer` and `activity=indexer_processing`.
3. Indexer skips/defers when another owner holds the same project.
4. Indexer mutates only selected file rows and dependent chunks/vector state.
5. Auto-created projects from watcher are marked or queued for the normal indexer path.
6. No production indexing mutation path uses `owner_type=auto_indexing`.

## Backend compatibility acceptance

1. SQLite tests pass for retry, activity locks, staging, insert/update/delete, and project-management regressions.
2. PostgreSQL tests pass for retry, activity locks, staging, insert/update/delete, and project-management regressions when PostgreSQL test configuration is available.
3. If PostgreSQL test configuration is unavailable, PostgreSQL-only tests are explicitly skipped with a reason; they are not reported as passed.
4. Backend-specific SQL is isolated in storage helpers or explicit backend branches.
5. PostgreSQL mode does not use SQLite-only tables or SQL constructs.
6. SQLite mode does not use PostgreSQL-only syntax unless isolated behind backend-specific helpers.

## MCP acceptance

1. MCP smoke regression passes.
2. MCP retry behavior check proves structured transient handling.
3. MCP worker coordination check proves same-project exclusion and different-project non-blocking behavior.
4. MCP worker coordination check proves watcher write ordering and ignore-exception behavior.
5. MCP worker coordination check proves watcher uncoordinated auto-indexing is removed from the active mutation path.
6. Safe project-management regression passes.
7. `clear_trash` PostgreSQL safety is verified when project/trash/schema/cleanup code changed.
8. Queue results are not accepted by job status alone; nested `result.command.result.success` is inspected when queue is used.
9. **Deterministic MCP QA alternative:** When live watcher/indexer contention cannot be reproduced through MCP alone, items 2–3 may be satisfied by running `qa_mcp_plan_hooks` with `CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1` on the server, then verifying `[DB_RETRY]` and `[WORKER_COORD]` in driver or worker logs (for example via `view_worker_logs`). This supplements but does not replace smoke regression (item 1) or safe project-management checks (items 6–8).

## Documentation acceptance

1. Observations document contains command, expected result, actual result, verification command, verification result, and status for each step.
2. Bugs are documented with:
   - Command
   - Expected
   - Actual
   - Error
   - Root cause
   - Fix
   - Post-fix verification
   - Status
3. Final report summarizes implemented behavior, skipped items, remaining risk, and exact MCP/test commands used.
4. Final report maps every criterion in this step to evidence or an explicit skipped/not-applicable reason.

## Final status rule

The plan is complete only when all acceptance sections above are satisfied and verified through actual commands, separate read/log checks, and recorded observations.

Do not mark the plan complete if any acceptance item is only supported by code inspection without behavior verification.
