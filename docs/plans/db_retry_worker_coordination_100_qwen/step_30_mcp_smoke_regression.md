# Step 30 - MCP smoke regression

Previous: [Step 29](step_29_pre_mcp_source_verification.md). Next: [Step 31](step_31_mcp_retry_behavior.md).

## Goal

Prove the server remains operational after the DB retry block before deeper behavior tests.

## Required MCP commands

Run these commands through MCP and record all results:

1. `list_watch_dirs`
2. `list_projects`
3. `list_projects(include_deleted=true)`
4. `list_trashed_projects`
5. `get_database_status`
6. `queue_list_jobs(limit=5)` when available, or `queue_get_job_status` for a known safe job id when queue coverage is needed.
7. `list_project_files` for `docs/plans/db_retry_worker_coordination_100_qwen/*` to prove the server can still enumerate non-Python project files.

## Expected results

1. All read/status commands return `success=true`.
2. `list_projects` and `list_projects(include_deleted=true)` both return structured project lists.
3. `list_trashed_projects` returns structured trash state even when empty.
4. `get_database_status` returns structured DB status without fatal errors.
5. `list_project_files` returns `README.md`, `architecture_addendum.md`, and `step_*.md` files.
6. No command in this step mutates project data.

## Queue rule

Do not trust only `status=completed` or `progress=100`.

If a queued command is checked, inspect and record:

- outer `status`
- outer `progress`
- inner `result.command.result.success`
- inner error details when inner success is false

If inner success is false, the operation failed even when the outer queue status is completed.

## Forbidden

- Do not run destructive project commands in this smoke step.
- Do not use `vast_srv` for destructive checks.
- Do not start watcher/indexer mutation scenarios in this smoke step; those belong to Step 32.

## Observation requirement

Record each command, expected result, actual result, verification command if any, verification result, and status in [Step 28](step_28_observations_document.md).

## Completion criteria

All listed read/status commands return successfully, `list_project_files` proves plan files are visible through MCP, and no new fatal server errors appear in immediately relevant logs.
