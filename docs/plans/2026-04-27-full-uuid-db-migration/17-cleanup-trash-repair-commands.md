# Step 17 — Cleanup, trash, repair, and destructive commands after UUID migration

## Goal
Update project/file cleanup, trash lifecycle, repair commands, and destructive operations so they work with UUID identifiers and remain safe.

## Why this step exists
The project has strict trash/delete safety rules. UUID migration changes primary/foreign key types across files, chunks, entities, duplicates, snapshots, and analysis results. Cleanup paths must not rely on integer IDs, SQLite rowids, or path-only identity.

## Current code risks to verify
1. `clear_file_data(file_id)` currently deletes by file id and related entity ids. After migration all those IDs are UUID strings.
2. `code_content_fts` / `rowid` cleanup is SQLite-specific. PostgreSQL must not execute SQLite FTS rowid SQL.
3. Any cleanup query using integer assumptions must be updated.
4. Any cleanup query using path-only identity must be replaced by UUID/project-scoped identity.
5. Queue job `completed` is not enough; inner command success must be checked.

## Files to inspect/edit
- `code_analysis/core/database/files/crud.py`
- project trash/delete/restore command modules
- clear project/trash commands
- repair/maintenance commands
- database cleanup helpers
- tests for project deletion/trash lifecycle

## Required changes
1. Update all cleanup function signatures from integer IDs to UUID strings where DB identity is involved.
2. Update all delete queries to use UUID parameters with no casts in generic SQL.
3. Ensure project-level cleanup deletes by `project_id` UUID and file-level cleanup deletes by `file_id` UUID.
4. Ensure `clear_file_data` collects UUID entity ids from `classes`, `functions`, `methods` and uses them in dependent cleanup.
5. Ensure `vector_index` cleanup handles UUID `entity_id` but keeps integer `vector_id` unchanged.
6. Ensure PostgreSQL cleanup path does not use SQLite FTS `rowid`.
7. Keep trash lifecycle behavior exactly documented:
   - active project exists;
   - mark deleted;
   - appears in trash;
   - disappears from active list;
   - include_deleted reflects state;
   - restore/delete/clear are consistent.

## Layering requirements
- Command layer validates target project/file IDs and safety rules.
- Universal database cleanup helpers express deletion intent.
- PostgreSQL-specific FTS/DDL cleanup stays in the PostgreSQL-specific layer or is skipped if feature does not exist.
- SQLite FTS rowid logic belongs only to SQLite branch.
- Do not put PostgreSQL-specific cleanup SQL into generic command layer.

## Must not do
- Do not run destructive commands on real projects during tests unless explicitly approved.
- Do not use `vast_srv` for destructive testing.
- Do not use path matching as the primary cleanup key.
- Do not delete backup migration tables until post-migration verification is complete.
- Do not treat queue `completed` as success without checking inner command success.
- Do not convert `vector_id` to UUID.

## Tests required
1. File cleanup deletes UUID-backed AST/CST/entities/chunks/vector_index rows.
2. Project trash lifecycle still works with UUID file/entity/chunk IDs.
3. `clear_trash` is PostgreSQL-aware and does not run SQLite FTS rowid SQL.
4. Restore project from trash preserves UUID relationships.
5. Permanently delete project removes only that project's UUID-scoped rows.
6. Cleanup one project does not delete rows belonging to another project.
7. Queue job status verification checks inner success.

## Runtime verification
Use only test projects for destructive lifecycle checks.

Required commands after restart:

```text
list_projects
list_projects(include_deleted=true)
list_trashed_projects
project_set_mark_del(dry_run=true)
restore_project_from_trash
permanently_delete_from_trash
clear_trash
get_database_status
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- no cross-project deletes;
- no PostgreSQL errors from SQLite-only SQL;
- trash lifecycle remains consistent;
- migrated UUID relationships remain valid.

## References
- `10-data-migration-postgres-driver-branch.md`
- `12-file-crud-and-path-identity.md`
- `15-vector-index-and-faiss-mapping.md`
- `18-test-matrix-and-runtime-verification.md`
