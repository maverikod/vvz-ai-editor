# Step 34 - clear_trash PostgreSQL safety

Previous: [Step 33](step_33_safe_project_management_regression.md). Next: [Step 35](step_35_final_acceptance.md).

## Goal

Verify trash cleanup remains backend-aware and safe after schema, DB, project, trash, or cleanup changes.

## When this step is required

Run this step if any of these areas changed:

- project management commands;
- trash commands;
- schema/migration code;
- database cleanup code;
- storage-layer SQL helpers;
- project deletion/restore lifecycle code.

Run only on a safe temporary trash state. Never run destructive checks on `vast_srv`.

## Required implementation inspection

Inspect relevant implementation and confirm:

1. PostgreSQL mode does not use SQLite-only SQL such as `rowid` or `code_content_fts`.
2. SQLite-specific cleanup SQL is isolated to SQLite code paths.
3. PostgreSQL cleanup uses backend-aware SQL or storage-layer abstraction.
4. `clear_trash` does not bypass safety validation.

## Required target validation before destructive cleanup

Before any destructive cleanup command, record:

- `project_id`
- name
- path
- deleted flag
- files count if available
- chunks count if available
- explicit confirmation target is not `vast_srv`
- explicit confirmation trash contains only controlled test item(s), or that only controlled test item(s) will be affected

## Required MCP lifecycle checks

1. Prepare a safe temporary project/trash item if destructive verification is needed.
2. Run `list_trashed_projects` before cleanup.
3. Confirm trash contents are safe for this test.
4. Run `clear_trash` only after safety confirmation.
5. Run `list_trashed_projects` after cleanup.
6. Expected for a controlled test state: `count=0` or no remaining controlled test item.
7. Run `list_projects(include_deleted=true)`.
8. Explicitly document actual DB behavior:
   - deleted projects are permanently removed from DB; or
   - deleted projects remain with `deleted=true`; or
   - another observed backend-specific behavior, with evidence.

## Queue rule

If queue is involved, inspect and record:

- outer `status`
- outer `progress`
- inner `result.command.result.success`
- inner error details if inner success is false

Outer `status=completed` and `progress=100` are not sufficient.

## Forbidden

- Do not clear unrelated user trash without explicit target validation.
- Do not use SQLite-specific cleanup SQL in PostgreSQL mode.
- Do not run destructive checks on `vast_srv`.
- Do not report DB behavior from assumptions; record observed behavior after MCP read commands.

## Observation requirement

Record commands, expected results, actual results, verification commands, verification results, queue inner success if applicable, and actual DB trash lifecycle behavior in [Step 28 observations](step_28_observations_document.md).
