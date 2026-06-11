# Step 36 - Final report

Previous: [Step 35](step_35_final_acceptance.md). Next: [README](README.md).

## Goal

Produce the final execution report after all implementation, tests, and MCP verification steps are complete.

File to create after execution:

`docs/observations/db_retry_worker_coordination_final_report.md`

## Required report sections

1. Summary of completed scope.
2. Changed files grouped by area:
   - DB exceptions/types;
   - PostgreSQL driver/RPC;
   - config validation;
   - schema/migrations;
   - worker coordination;
   - watcher staging/ignore handling;
   - indexer coordination;
   - SQLite compatibility;
   - tests;
   - documentation/observations.
3. Tests run with exact commands and results.
4. MCP commands run with exact commands and results.
5. Queue checks, including outer queue status/progress and inner `result.command.result.success` when queue was used.
6. Logs checked:
   - `file_watcher`;
   - `indexing_worker`;
   - database/RPC logs if available;
   - queue logs if queue was used.
7. Evidence that `[DB_RETRY]` appears in the controlled retry scenario.
8. Evidence that `[WORKER_COORD]` appears for acquire, busy/skip, heartbeat when applicable, and release scenarios.
9. Evidence that same-project watcher/indexer contention is blocked or deferred.
10. Evidence that different projects are not globally blocked.
11. Evidence that watcher write ordering is preserved: staging, insert new files, update changed files, mark/delete absent files, then chunk invalidation only for changed/deleted rows.
12. Evidence that ignore exceptions are honored after ignore patterns.
13. Evidence that watcher daemon auto-indexing is removed from the active mutation path and auto-created projects go through the normal indexer path.
14. `clear_trash` behavior if Step 34 was applicable:
   - whether deleted projects are permanently removed from DB;
   - or remain with `deleted=true`;
   - or another observed backend-specific behavior with evidence.
15. Safety confirmations:
   - no `.venv`, `venv`, `site-packages`, or installed packages edited;
   - no destructive operations run on `vast_srv`;
   - destructive operations, if any, used only validated safe targets.
16. Remaining risks or skipped tests with explicit reasons.
17. Final status for each criterion in [Step 35](step_35_final_acceptance.md): `passed`, `failed`, `skipped`, or `not applicable`.

## Required acceptance matrix

The final report must include a matrix with columns:

```text
Criterion:
Status:
Evidence command:
Evidence result:
Verification command:
Verification result:
Notes:
```

Every numbered criterion from [Step 35](step_35_final_acceptance.md) must appear in this matrix.

## Required skipped-test handling

For every skipped item, include:

- skipped item name;
- reason;
- whether the item was optional or environment-dependent;
- mandatory alternative evidence, if required by the plan;
- final status.

Skipped PostgreSQL integration tests must not be reported as passed.

## Forbidden

- Do not claim success without evidence from tests and MCP behavior checks.
- Do not hide failed or skipped tests.
- Do not describe a queue job as successful unless the inner command result is successful.
- Do not mark the plan complete when any Step 35 criterion lacks evidence or an explicit allowed skipped/not-applicable reason.
- Do not use code inspection alone as final evidence for behavior criteria.

## Completion criteria

The final report exists, references the observations file from [Step 28](step_28_observations_document.md), and explicitly maps every acceptance criterion from [Step 35](step_35_final_acceptance.md) to command evidence and separate verification evidence.
