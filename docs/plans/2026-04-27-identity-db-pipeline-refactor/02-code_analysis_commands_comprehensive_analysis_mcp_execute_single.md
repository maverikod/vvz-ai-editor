# Step 02 — `code_analysis/commands/comprehensive_analysis_mcp/execute_single.py`

## Goal
Remove or strictly constrain destructive path-only cleanup in comprehensive analysis single-file execution.

## Why this step exists
Current code was checked against the repository. `execute_single.py` contains a global absolute-path lookup:

```python
result = db.execute(
    "SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1",
    (abs_path,),
)
```

If it finds the path under another project, it currently calls `db.clear_file_data(wrong_file_id)` and then marks that other row deleted. This is not just a diagnostic lookup; it is destructive cross-project cleanup from an analysis command.

This must be fixed or explicitly justified with tests. Normal analysis must not silently delete or clear another project's data.

## Exact file to edit
`code_analysis/commands/comprehensive_analysis_mcp/execute_single.py`

## Required investigation
1. Find the global `files WHERE path = ? LIMIT 1` query.
2. Confirm the caller has `proj_id` available.
3. Identify all side effects after `file_in_wrong_project` is found:
   - `db.clear_file_data(wrong_file_id)`;
   - `UPDATE files SET deleted = 1`;
   - re-addition through `db.add_file(...)`.
4. Check whether this code path is normal comprehensive analysis or an explicit repair command.
5. Check nested project root behavior: same absolute path may be visible under two project roots.

## Required outcome
Replace destructive behavior with safe reporting unless there is a separate explicit repair command.

Preferred safe behavior:
1. If the file is not found under `proj_id`, do not search globally unless needed for diagnostics.
2. If a global diagnostic lookup finds the same absolute path under another project:
   - log a warning or return diagnostic data;
   - do **not** call `clear_file_data`;
   - do **not** mark the other project's row deleted;
   - do **not** reassign ownership from this command.
3. If repair behavior is required, move it behind an explicit repair command/flag, not normal analysis.

## Acceptable SQL after fix
For normal analysis:

```sql
WHERE path = ? AND project_id = ?
```

For diagnostic-only lookup:

```sql
SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1
```

but the diagnostic-only path must not mutate data.

## Must not do
- Do not change `files.crud.add_file` here; that is Step 01.
- Do not use `relative_path` across projects.
- Do not introduce PostgreSQL-specific SQL in command code.
- Do not keep destructive cleanup in normal comprehensive analysis.

## Tests to add/update
Create or update tests for comprehensive analysis single-file execution:
1. Same absolute path known in DB under the requested project → resolves normally.
2. Same absolute path known under another project → diagnostic warning/result only; no `clear_file_data`; no `UPDATE deleted`.
3. Same `relative_path` in another project must not affect this command.
4. Missing file under project DB but present on disk → command may analyze as unindexed, but must not steal ownership from another project.

## Verification commands
After restart:

```text
comprehensive_analysis(project_id=<test project>, file_path=<file>, ...)
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
get_database_status
```

Expected:
- no accidental cross-project file ownership changes;
- no path-only destructive cleanup;
- deleted count does not increase from comprehensive analysis.

## References
- Previous step: `01-code_analysis_core_database_files_crud.md`
- Identity helper: `03-code_analysis_core_file_identity.md`
- Schema step: `05-code_analysis_core_database_schema_identity.md`
