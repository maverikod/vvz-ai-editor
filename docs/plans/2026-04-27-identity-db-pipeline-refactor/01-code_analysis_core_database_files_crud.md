# Step 01 — `code_analysis/core/database/files/crud.py`

## Goal
Make file identity project-scoped and prevent destructive cross-project cleanup caused by matching `relative_path` across different projects.

## Why this step exists
Runtime logs showed false `Data inconsistency detected` errors for allowlisted `.venv/site-packages` files. Schema audit showed that the DB uniqueness is already scoped by `UNIQUE(project_id, path)`, but `add_file` previously used cross-project matching by `relative_path OR path`.

## Current code checked before this step
`code_analysis/core/database/files/crud.py` currently has the hotfix in `add_file`: the cross-project query uses only `path = ? AND project_id != ?`. Same-project lookup still uses `(relative_path = ? OR path = ?)`, which is correct inside one project.

## Current required state
The current hotfix must remain present:

```sql
WHERE path = ?
AND project_id != ?
AND <active-file predicate>
```

The cross-project query must not use `relative_path`.

## Exact file to edit
`code_analysis/core/database/files/crud.py`

## Exact functions to inspect
- `add_file`
- `get_file_by_path`
- `get_file_id`
- `clear_file_data`
- `_clear_file_vectors`

## Required changes
1. Keep cross-project conflict detection limited to the same absolute `path` only.
2. Keep same-project update lookup by `(relative_path = ? OR path = ?)` because `relative_path` is meaningful inside one `project_id`.
3. Ensure log text says `same absolute path` / `relocation/conflict`, not generic `Data inconsistency detected` caused by relative path.
4. Do not change schema in this step.
5. Do not migrate `files.id` from integer to UUID in this step.

## Important non-goal found during code check
`clear_file_data` currently contains SQLite/FTS-specific cleanup such as `code_content_fts` / `rowid`. Do **not** fix that in this step. That is a separate backend-aware cleanup task. This step owns identity/conflict behavior only.

## Must not do
- Do not globally ignore all `.venv` files.
- Do not remove allowlisted dependency handling.
- Do not call `clear_file_data` for another project when only `relative_path` matches.
- Do not change `execute_single.py` in this step; see Step 02.
- Do not fix `code_content_fts` / `rowid` cleanup here.

## Tests to run or create
Primary test file:
`tests/test_add_file_cross_project_path.py`

Required cases:
1. Same `relative_path`, different absolute paths, different projects → both active, no cleanup.
2. Same project + same absolute path → one row updated.
3. Chunk rows for project A survive when adding same relative path to project B.
4. Same absolute path under nested roots → current relocation/conflict behavior is documented by test.

## Verification commands
After server restart:

```text
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
get_database_status
```

Expected:
- no false cross-project relative path conflict logs;
- deleted count does not grow due to allowlisted venv collisions;
- indexing/chunking/vectorization continue.

## References
- Next step: `02-code_analysis_commands_comprehensive_analysis_mcp_execute_single.md`
- Related schema plan: `05-code_analysis_core_database_schema_identity.md`
- Status consistency: `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`
