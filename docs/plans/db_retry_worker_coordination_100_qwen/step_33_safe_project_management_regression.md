# Step 33 - Safe project-management regression

Previous: [Step 32](step_32_mcp_worker_coordination.md). Next: [Step 34](step_34_clear_trash_safety.md).

## Goal

Verify project-management commands remain safe and consistent after DB/schema/coordination changes.

## Safe targets

- Preferred target: `repro_file_mgmt_test`.
- Alternative target: a newly created temporary project inside `test_data`.
- Forbidden destructive target: `vast_srv`.

## Required target validation

Before any command that can change project state, record:

- `project_id`
- name
- path
- deleted flag
- processing paused flag if available
- files count if available
- chunks count if available
- explicit confirmation target is not `vast_srv`

## Required non-destructive MCP checks

Run and record:

1. `project_set_mark_del(dry_run=true)` on the safe target.
2. `delete_unwatched_projects(dry_run=true)`.
3. `set_project_processing_paused(true)` on the safe target.
4. Verify pause state with `list_projects(include_deleted=true)`.
5. `set_project_processing_paused(false)` on the safe target.
6. Verify unpause state with `list_projects(include_deleted=true)`.

## Required lifecycle checks when destructive validation is explicitly executed

Destructive lifecycle checks are not mandatory in this smoke regression. If executed, use only a temporary project created for this step or `repro_file_mgmt_test` when explicitly approved for lifecycle testing.

For every destructive lifecycle command, verify after the operation with all of these commands:

1. `list_projects`
2. `list_projects(include_deleted=true)`
3. `list_trashed_projects`
4. queue job status internals if queue is used

Required lifecycle sequence when executed:

1. active project exists before deletion;
2. project is marked deleted;
3. project appears in trash;
4. project disappears from active list;
5. `include_deleted=true` reflects correct state;
6. restore or permanent delete produces consistent state;
7. final state is recorded.

## Queue rule

Outer `status=completed` and `progress=100` are not enough. Check and record `result.command.result.success`.

If inner success is false, the operation failed even when the queue job completed.

## Coordination rule

Project-management commands that mutate `projects`, `files`, `chunks`, or project processing flags must either:

1. acquire Step 13 project activity lease with `owner_type=command` and `activity=command_mutation`; or
2. be documented as safe because they cannot overlap watcher/indexer mutation for the same project.

The verification must record which rule applies to each mutating command.

## Forbidden

- Do not run destructive operations on `vast_srv`.
- Do not run `delete_from_disk=true` except on a temporary project created for this step.
- Do not accept queue completion without inner command success.
- Do not omit target validation.

## Observation requirement

Record all commands, expected results, actual results, verification commands, verification results, queue inner success when applicable, and status in [Step 28](step_28_observations_document.md).
