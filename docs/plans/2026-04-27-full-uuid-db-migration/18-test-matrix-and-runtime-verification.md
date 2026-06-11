# Step 18 — Test matrix and runtime verification

## Goal
Define the complete test and MCP verification matrix for full UUID database migration on both supported backends: PostgreSQL and SQLite.

## Why this step exists
This migration changes database identity types across many tables. A weak model must not consider the work complete after schema edits only. The migration is complete only when schema, data migration, CRUD, indexing, chunking, vectorization, search, MCP API, and destructive lifecycle commands are all verified through actual behavior on the selected backend. PostgreSQL and SQLite must both have full backend-specific verification paths.

## Architecture constraint
All tests must preserve this layering:

```text
command/application code
-> universal DB/driver contract and selected-backend adaptation layer
-> PostgreSQL-specific driver/schema/migration
-> PostgreSQL DB

command/application code
-> universal DB/driver contract and selected-backend adaptation layer
-> SQLite-specific driver/schema/migration
-> SQLite DB
```

Commands emit backend-neutral logical requests. The universal driver/adaptation layer selects the configured backend and adapts the request. The selected backend driver must emit and execute syntax valid for that DB only.

## Test layers

### Layer 1 — Driver contract and adaptation tests
Required assertions:
- universal driver insert contract does not return integer-only type;
- universal adaptation routes the same logical command request to PostgreSQL-valid behavior when PostgreSQL is selected;
- universal adaptation routes the same logical command request to SQLite-valid behavior when SQLite is selected;
- PostgreSQL insert returns UUID string for UUID primary key and never returns `0` for non-integer returned id;
- SQLite insert returns explicit UUID string or typed identity result for UUID/TEXT primary key tables;
- queued execution checks nested `result.command.result.success`, not only job status.

### Layer 2 — Schema definition tests
Required assertions:
- targeted PK columns are logical UUID, not INTEGER autoincrement;
- targeted FK columns are logical UUID;
- PostgreSQL branch maps logical UUID to native PostgreSQL UUID;
- SQLite branch maps logical UUID to canonical UUID TEXT;
- `watch_dirs.id`, `projects.id`, `project_id`, and `watch_dir_id` values are valid canonical UUIDs in both backends;
- `vector_id`, line numbers, counters, stats, and ordinals remain integer where they are not DB identity;
- `code_chunks.chunk_uuid` remains a separate unique string/UUID business key.

### Layer 3 — Backend DDL tests
PostgreSQL required assertions:
- UUID columns generate valid PostgreSQL UUID DDL;
- boolean partial indexes are PostgreSQL-compatible;
- no SQLite FTS5 or `rowid` DDL is emitted for PostgreSQL;
- FK constraints point to UUID columns;
- uniqueness constraints are preserved.

SQLite required assertions:
- logical UUID columns generate valid SQLite canonical TEXT DDL;
- SQLite table rebuild strategy is used where SQLite cannot alter PK/FK types directly;
- SQLite FTS5/rowid behavior is rebuilt or explicitly adapted;
- FK/index/unique behavior is preserved according to SQLite capabilities;
- no PostgreSQL UUID/cast/RETURNING-only assumptions leak into SQLite.

### Layer 4 — Migration tests
Use small PostgreSQL and SQLite test DBs with rows in every relevant table.

Required assertions for both backends:
- mapping tables are populated idempotently;
- full mapping-table coverage exists for every mandatory mapping table from Step 09;
- each mapping table has row-count parity with its source table;
- row counts match after copy/rebuild;
- FK rewrites are correct;
- polymorphic references are rewritten according to the chosen design;
- `vector_index.vector_id` remains integer and is not UUID-converted;
- `code_chunks.chunk_uuid` follows the selected preservation/versioning strategy;
- old/backup data is preserved until verification;
- rerun behavior is safe.

### Layer 5 — CRUD tests
Required assertions on both backends:
- `add_file` returns UUID string;
- `get_file_id` returns UUID string;
- `get_file_by_id` accepts UUID string;
- update/delete/clear work by UUID;
- same relative path across projects remains safe;
- same absolute path conflict behavior remains explicit and tested;
- `project_id` and `watch_dir_id` validation rejects invalid UUID strings clearly.

### Layer 6 — Indexing / AST / CST / entity tests
Required assertions on both backends:
- indexing creates UUID rows in `files`, `ast_trees`, `cst_trees`, `classes`, `functions`, `methods`;
- indexing creates UUID rows in `imports`, `issues`, `usages`, `code_content`, and `entity_cross_ref`;
- methods reference UUID class IDs;
- entity cross refs use UUID IDs and UUID caller/callee references;
- `code_content.entity_id` follows the selected polymorphic UUID design;
- reindex clears and recreates rows without FK errors.

### Layer 7 — Chunking / vectorization / search tests
Required assertions on both backends where the feature is enabled:
- `code_chunks.id` is UUID-shaped;
- `code_chunks.file_id` is UUID-shaped;
- `code_chunks.project_id` is UUID-shaped and matches the owning project;
- `chunk_uuid` follows the selected migration/versioning strategy;
- `vector_id` remains integer FAISS id;
- semantic search resolves UUID chunk/file IDs;
- no code path casts UUID DB IDs to int;
- `CODE_CHUNK_UPSERT_PARAM_ORDER`, backend adapter normalization/translation tests, and backend run expectations match actual params/placeholders.

### Layer 8 — MCP API tests
Required assertions on both backends:
- help/schema output documents UUID string IDs;
- command outputs use UUID strings for migrated DB identities;
- commands accepting IDs validate UUIDs;
- `project_id` and `watch_dir_id` are UUID-shaped in public responses;
- PostgreSQL status/diagnostics distinguish native UUID storage;
- SQLite status/diagnostics distinguish canonical TEXT UUID storage;
- `vector_id` remains integer;
- legacy integer compatibility, if any, is explicit;
- status/diagnostic commands do not claim migrated DB identities are integers.

### Layer 9 — Trash / cleanup / destructive lifecycle tests
Required assertions:
- project trash lifecycle works on both backends where destructive lifecycle is supported;
- destructive commands are project-scoped;
- cleanup does not use SQLite FTS rowid on PostgreSQL;
- SQLite cleanup uses SQLite-valid FTS/rowid behavior only inside SQLite branch;
- cleanup one project does not delete another project's rows;
- queue status checks inner command success;
- destructive tests do not target `vast_srv`.

## Mandatory mapping-table coverage test
Implement a test or diagnostic that verifies all required tables from Step 09 exist and are complete on each backend:

```text
uuid_migration_files
uuid_migration_classes
uuid_migration_methods
uuid_migration_functions
uuid_migration_entity_cross_ref
uuid_migration_imports
uuid_migration_issues
uuid_migration_usages
uuid_migration_code_content
uuid_migration_ast_trees
uuid_migration_cst_trees
uuid_migration_vector_index
uuid_migration_code_chunks
uuid_migration_code_duplicates
uuid_migration_duplicate_occurrences
uuid_migration_comprehensive_analysis_results
uuid_migration_file_tree_snapshots
uuid_migration_file_tree_snapshot_nodes
```

For each mapping table:
- table exists;
- `old_id` is unique;
- `new_id` is unique;
- source row count equals mapping row count;
- every copied FK can be joined through the mapping table.

## Required MCP runtime verification after migration
Run after migration and server restart on each backend:

```text
health
get_database_status
list_projects
list_projects(include_deleted=true)
list_project_files(project_id=<code_analysis>, limit=20)
get_worker_status(worker_type="file_watcher")
get_worker_status(worker_type="indexing")
get_worker_status(worker_type="vectorization")
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Then run representative feature checks:

```text
get_ast(project_id=<project>, file_path=<known_python_file>)
query_cst(project_id=<project>, file_path=<known_python_file>, ...)
semantic_search(project_id=<project>, query=<known_term>)
list_code_entities(project_id=<project>)
get_imports(project_id=<project>)
find_usages(project_id=<project>, target_name=<known_symbol>)
```

Expected:
- IDs in responses are UUID strings where DB identity was migrated;
- `project_id` and `watch_dir_id` values are valid UUID strings;
- status/diagnostic samples do not claim integer ID types for migrated identities;
- diagnostics correctly identify backend storage: PostgreSQL UUID or SQLite canonical TEXT;
- indexing remains 100% or progresses normally;
- chunks and vectorized chunks remain available or are rebuilt intentionally;
- no UUID/int type errors in logs.

## Required migration invariants
Run or implement diagnostics for both backends, adapting SQL syntax only in backend-specific code:

```sql
SELECT COUNT(*) FROM code_chunks cc JOIN files f ON f.id = cc.file_id WHERE cc.project_id != f.project_id;
```

```sql
SELECT COUNT(*) FROM code_chunks cc LEFT JOIN files f ON f.id = cc.file_id WHERE f.id IS NULL;
```

```sql
SELECT COUNT(*) FROM ast_trees a LEFT JOIN files f ON f.id = a.file_id WHERE f.id IS NULL;
SELECT COUNT(*) FROM cst_trees c LEFT JOIN files f ON f.id = c.file_id WHERE f.id IS NULL;
```

```sql
SELECT path, COUNT(DISTINCT project_id)
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY path
HAVING COUNT(DISTINCT project_id) > 1;
```

PostgreSQL UUID cast validation:

```sql
SELECT id::uuid FROM projects;
SELECT id::uuid FROM watch_dirs;
```

SQLite UUID validation must use SQLite-safe validation logic against canonical UUID TEXT, not PostgreSQL casts.

## Must not do
- Do not mark migration successful based only on tests passing without MCP runtime verification.
- Do not ignore worker logs.
- Do not use queue `completed` as success without checking inner command result.
- Do not run destructive tests on `vast_srv`.
- Do not skip semantic search/FAISS verification.
- Do not skip full mapping-table coverage.
- Do not skip status/diagnostic sample ID type checks.
- Do not skip SQLite full backend verification.
- Do not put backend-specific SQL in command/application tests as a workaround.

## Definition of done
The migration block is done only when:
- PostgreSQL schema and migrated data pass invariant checks;
- SQLite schema/rebuild and migrated data pass invariant checks;
- every mandatory mapping table has coverage and row-count parity on both backends;
- `project_id` and `watch_dir_id` validate as canonical UUIDs on both backends;
- CRUD/indexing/chunking/vectorization/search work through MCP on both backends where the feature is supported;
- API schemas and responses expose UUID strings consistently;
- diagnostic/status outputs do not contradict selected backend storage;
- cleanup/trash lifecycle remains safe;
- logs show no UUID/int conversion errors;
- rollback/backup state is documented.

## References
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `09-migration-framework-and-id-map.md`
- `10-data-migration-postgres-driver-branch.md`
- `11-data-migration-sqlite-driver-branch.md`
- `15-vector-index-and-faiss-mapping.md`
- `16-mcp-api-compatibility.md`
- `17-cleanup-trash-repair-commands.md`
