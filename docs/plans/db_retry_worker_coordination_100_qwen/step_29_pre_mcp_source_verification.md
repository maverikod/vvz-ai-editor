# Step 29 - Pre-MCP source verification

Previous: [Step 28](step_28_observations_document.md). Next: [Step 30](step_30_mcp_smoke_regression.md).

## Goal

Prove the MCP server is using the modified source tree before behavior checks start.

## Required MCP commands

1. Run `health` or `config` and record server/source information if available.
2. Run `list_project_files` for each changed implementation/test area using narrow patterns.
3. Run `read_project_text_file`, CST query, or search commands to confirm implementation markers exist in the actual project source seen by MCP.
4. If MCP sees old code, use the supported reload/restart path, then repeat this verification from step 1.

## Required source markers

Confirm all markers that apply to completed implementation steps:

- `TransientDatabaseError`
- `classify_postgres_error`
- `write_retry_attempts`
- `lock_timeout_seconds`
- `statement_timeout_seconds`
- `project_activity_locks`
- `worker_project_activity`
- `[DB_RETRY]`
- `[WORKER_COORD]`
- `owner_type="indexer"` or equivalent indexer owner constant
- absence of production `owner_type="auto_indexing"` mutation path

## Required list_project_files verification

Use `list_project_files` to prove the command can see changed non-Python plan files and source files.

Required checks:

1. `file_pattern="docs/plans/db_retry_worker_coordination_100_qwen/*"` returns `README.md`, `architecture_addendum.md`, and `step_*.md` files.
2. A source-code pattern around changed Python files returns implementation files.
3. `count`, `total`, and `offset` are recorded.

## Forbidden

- Do not continue to behavior verification if MCP is still using old installed code.
- Do not assume source state from local inspection only.
- Do not treat a local file read outside MCP as sufficient evidence.

## Observation requirement

Record every command and result in [Step 28](step_28_observations_document.md). Include exact source path/version evidence found.

## Completion criteria

MCP read/query commands show the new implementation markers from the actual `code-analysis-server` project source, and `list_project_files` proves the changed plan/source files are visible to MCP.
