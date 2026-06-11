# Step 05 — Database schema identity map

## Goal
Document and harden the current schema identity model before any UUID migration.

## Why this step exists
The current runtime bug was not caused by DB uniqueness. The schema already has `UNIQUE(project_id, path)` for files. The dangerous behavior was in application-level conflict logic. Before changing IDs, weak models must understand the existing schema graph.

## Files to inspect
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py`
- `code_analysis/core/database/sqlite_to_postgres.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`

## Required investigation
Create or update schema documentation covering:

### `watch_dirs`
- primary key type;
- whether UUID is app-supplied or DB-generated;
- where path is stored;
- FK relationships.

### `watch_dir_paths`
- primary key;
- FK to `watch_dirs`;
- `absolute_path` semantics.

### `projects`
- `id` type;
- `watch_dir_id` FK;
- `root_path` uniqueness;
- deleted/paused fields.

### `files`
- current `id` type;
- `project_id` FK;
- `watch_dir_id` FK;
- `path` and `relative_path` semantics;
- `UNIQUE(project_id, path)`;
- indexes.

### `code_chunks`
- integer row id;
- `chunk_uuid` uniqueness;
- `file_id` FK;
- `project_id` FK;
- whether DB enforces `code_chunks.project_id == files.project_id`.

### AST/CST/entities
- all tables referencing `file_id`;
- all tables referencing `project_id`;
- unique constraints involving `file_id`.

## Required output
Create/update this markdown file:

`docs/plans/2026-04-27-identity-db-pipeline-refactor/schema_identity_map.md`

It must include:
1. Current schema graph.
2. Table-by-table PK/FK/unique/index summary.
3. Known gaps versus target model.
4. Risk list for UUID migration.
5. Recommendation: keep integer FK internals for now, add UUID business columns later if needed.
6. Diagnostic query designs for ownership invariants.

## Required diagnostics to document
At minimum include these diagnostics in `schema_identity_map.md`:

```sql
-- Chunks whose denormalized project_id does not match files.project_id
SELECT cc.id, cc.file_id, cc.project_id AS chunk_project_id, f.project_id AS file_project_id
FROM code_chunks cc
JOIN files f ON f.id = cc.file_id
WHERE cc.project_id != f.project_id;
```

```sql
-- Active same absolute path in multiple projects
SELECT path, COUNT(DISTINCT project_id) AS projects_count
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY path
HAVING COUNT(DISTINCT project_id) > 1;
```

```sql
-- Same relative path in multiple projects: diagnostic only, not automatically an error
SELECT relative_path, COUNT(DISTINCT project_id) AS projects_count
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY relative_path
HAVING COUNT(DISTINCT project_id) > 1;
```

## Must not do
- Do not change schema in this step.
- Do not add migrations in this step.
- Do not change IDs to UUID here.
- Do not modify live data.
- Do not treat duplicate `relative_path` across projects as an error.

## Tests to add later
This step is documentation/investigation. It should propose tests, not necessarily implement them:
1. schema creation tests for SQLite;
2. schema creation tests for PostgreSQL;
3. FK integrity tests;
4. `code_chunks.project_id` consistency diagnostic;
5. duplicate relative path diagnostic that does not fail as error.

## References
- File CRUD step: `01-code_analysis_core_database_files_crud.md`
- UUID transition plan: `12-uuid_business_identity_transition.md`
- Status consistency: `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`
