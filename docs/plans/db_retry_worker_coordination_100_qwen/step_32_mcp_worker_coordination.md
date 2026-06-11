# Step 32 - MCP worker coordination check

Previous: [Step 31](step_31_mcp_retry_behavior.md). Next: [Step 33](step_33_safe_project_management_regression.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md), [Step 13](step_13_worker_activity_coordinator.md), [Step 14](step_14_watcher_coordination.md), [Step 15](step_15_ignore_purge_metadata.md), and [Step 16](step_16_indexer_coordination.md).

## Goal

Verify project-scoped worker coordination through real MCP commands and logs. Unit tests alone are not sufficient.

## Safety

Do not run destructive checks on `vast_srv`.

Use `repro_file_mgmt_test` or a temporary project under `test_data` for mutation checks. Before any mutating command, record target validation: `project_id`, name, root path, deleted flag, files count if available, chunks count if available, and confirmation that target is not `vast_srv`.

## Required scenario A - same-project contention

1. Select safe project `A`.
2. Acquire a real project activity lease for project `A` as one owner through the implemented MCP path or a dedicated test hook command.
3. Run a second MCP command path that attempts to mutate the same project `A` as a different owner.
4. Expected result: the second owner skips or defers project `A`.
5. Verify with a separate read/query command that file rows, chunks, index state, and indexing flags for project `A` were not mutated by the skipped owner.
6. Verify logs contain `[WORKER_COORD]` acquire, busy/skip, and release records for project `A`.

## Required scenario B - different projects are not globally blocked

1. Select safe projects `A` and `B`.
2. Hold a project activity lease for project `A`.
3. Run watcher or indexer mutation path for project `B`.
4. Expected result: project `B` proceeds.
5. Verify with a separate read/query command that only project `B` changed and project `A` remained protected.
6. Verify logs show activity for project `B` and no global server-wide block.

## Required scenario C - watcher write ordering

Run a safe watcher cycle or dedicated MCP test command on a test project with one new file, one changed file, one deleted/absent file, one ignored path, and one ignore-exception path.

Expected result:

1. Staged candidate set is built from filesystem scan results for the target `project_id`.
2. Ignore patterns are applied before mutation.
3. Ignore exceptions are applied after ignore patterns and re-include the expected file.
4. New file rows are inserted before changed/deleted rows are processed.
5. Changed rows are updated only for changed files.
6. Deleted/absent rows are marked/deleted only after staging exists.
7. Chunks are invalidated/deleted only for changed/deleted rows.

Use separate read/query commands to verify DB state after the watcher path.

## Required scenario D - auto-created project indexing path

1. Trigger or inspect watcher auto-create path for a safe temporary project.
2. Verify watcher does not start a separate uncoordinated indexing path.
3. Verify the auto-created project is marked or queued for the normal indexer path.
4. Verify the normal indexer path acquires `owner_type=indexer` and `activity=indexer_processing` before mutating files/chunks/index state.
5. Verify no production mutation log uses `owner_type=auto_indexing`.

## Required read/log verification

After every scenario, run separate read/log commands. Do not rely on the command that performed the mutation as its own verification.

Required log checks:

1. `[WORKER_COORD]` acquire record exists.
2. `[WORKER_COORD]` busy/skip record exists for same-project contention.
3. `[WORKER_COORD]` heartbeat record exists for long-running phases if the scenario runs long enough to heartbeat.
4. `[WORKER_COORD]` release record exists.
5. Logs include `project_id`, `owner_type`, `owner_id`, `activity`, and `result`.
6. Same-project skip log includes blocking owner type/activity when available.

Use `view_worker_logs`, `list_worker_logs`, or the current log-viewer MCP commands available in this server.

## Required queue rule

If any MCP command is run through queue, `queue_get_job_status` with `status=completed` and `progress=100` is not sufficient. Inspect `result.command.result.success`. If that field is false, the command failed.

## Acceptance for this step

1. Same project cannot be mutated by watcher and indexer concurrently.
2. Different projects are not globally blocked.
3. Watcher new-file insert happens before changed/deleted mutation.
4. Ignore exceptions are honored.
5. Watcher uncoordinated auto-indexing is removed from active mutation path.
6. Auto-created projects are processed through the normal indexer path.
7. MCP logs prove acquire/busy-or-skip/heartbeat-if-applicable/release behavior.
8. Every scenario has a separate read/log verification command.

## Observation entry

Record command, expected result, actual result, verification command, verification result, and status in [Step 28 observations](step_28_observations_document.md).
