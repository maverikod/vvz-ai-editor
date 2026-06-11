# Step 09 — Migration framework and integer-to-UUID mapping

## Goal
Design and implement the migration mechanism before changing live data. The migration must preserve every relationship from old integer IDs to new UUID IDs and be idempotent for both supported backends: PostgreSQL and SQLite.

## Architecture constraint
The migration must follow the project layering exactly:

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

Both PostgreSQL and SQLite are full targets. The universal driver layer receives backend-neutral requests from commands and adapts/translates them for the selected backend contract. The selected specific driver must then execute strictly according to its own DB syntax and behavior. PostgreSQL migration uses native UUID columns. SQLite migration/rebuild uses canonical UUID TEXT representation. Backend-specific SQL, DDL, placeholder syntax, casts, `RETURNING`, UPSERT, FTS, and rowid semantics must not enter command code as generic assumptions.

## Current code checked
`schema_creation_migrate.py` currently performs small incremental migrations with `ALTER TABLE ADD COLUMN`, index creation, and occasional column drops. It is not sufficient for primary-key type replacement across a FK graph.

`schema_sync_sql_postgres.py` currently maps schema types to PostgreSQL DDL. UUID support must be added there or in a PostgreSQL-specific migration layer before PostgreSQL UUID tables are created. The SQLite schema/migration branch must separately map the same logical UUID schema to canonical TEXT and SQLite-valid rebuild/swap operations.

The driver insert contract is a blocker: the universal contract and both backend driver branches must be UUID-safe before any PK is converted to UUID. A queue job showing `status=completed` is not enough; check nested command success when migration is executed through queue.

## Files to inspect/edit
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/database/schema_sync.py`
- `code_analysis/core/database/schema_sync_models.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_run.py`
- new PostgreSQL migration module, for example `code_analysis/core/database/migrations/uuid_identity_migration_postgres.py`
- new SQLite migration/rebuild module, for example `code_analysis/core/database/migrations/uuid_identity_migration_sqlite.py`
- migration tests for both backends

## Required migration strategy
Use explicit mapping tables during migration. Do not cast integers to strings and call them UUIDs.

Create mapping tables for every migrated integer PK, not only for tables referenced by another table. This avoids partial migration when a table later becomes referenced or is exposed through API/diagnostics.

## Mandatory mapping tables
The implementation must create and validate all of the following mapping tables for currently integer primary keys. PostgreSQL uses UUID-typed `new_id`; SQLite uses canonical UUID TEXT for `new_id`.

```sql
uuid_migration_files(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_classes(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_methods(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_functions(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_entity_cross_ref(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_imports(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_issues(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_usages(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_code_content(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_ast_trees(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_cst_trees(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_vector_index(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_code_chunks(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_code_duplicates(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_duplicate_occurrences(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_comprehensive_analysis_results(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_file_tree_snapshots(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
uuid_migration_file_tree_snapshot_nodes(old_id INTEGER PRIMARY KEY, new_id UUID_OR_TEXT NOT NULL UNIQUE)
```

Do not let an executor infer this list from short examples. This list is the minimum required coverage for both backends.

## Special case: file_tree_snapshot_roots
`file_tree_snapshot_roots` must receive an explicit design decision before implementation. It does not follow the same autoincrement `id` pattern; its `snapshot_id` behaves as both a root identity reference and a FK to `file_tree_snapshots.id`.

Required decision:

```text
Option A: keep no separate UUID mapping table for file_tree_snapshot_roots and rewrite snapshot_id through uuid_migration_file_tree_snapshots.
Option B: introduce an explicit root UUID identity only if code/schema proves it is a distinct entity, then document the new PK/FK shape before migration.
```

Default unless proven otherwise: Option A.

## Required phases

### Phase 1 — Preflight
1. Detect backend and select the matching backend-specific branch.
2. Refuse to run if driver insert contract is not UUID-safe for the selected backend.
3. Refuse to run if universal layer still promises `insert(...) -> int` for rows whose PK is UUID.
4. Stop workers or enter maintenance mode.
5. Verify no mutation jobs are active.
6. Verify no orphan FK references exist.
7. Verify ownership invariants, including `code_chunks.project_id = files.project_id`.
8. Verify `projects.id` and `watch_dirs.id` values are valid canonical UUIDs before backend type normalization.

### Phase 2 — Build mappings
1. For each table in the mandatory mapping list, generate UUID4 for every row.
2. Store old-to-new mapping using the selected backend representation.
3. If mapping exists, reuse it. Mapping phase must be idempotent.
4. Validate coverage: each source table row count equals its mapping table row count.
5. Validate uniqueness: each mapping table has unique `old_id` and unique `new_id`.

### Phase 3 — Create new UUID tables
1. Create new tables with logical UUID PK/FK schema.
2. PostgreSQL branch maps logical UUID to native UUID.
3. SQLite branch maps logical UUID to canonical TEXT.
4. Do not drop old tables.
5. Use backend-supported transactions where possible.
6. Keep backend-specific DDL in the matching backend branch; do not put backend SQL into universal command code.

### Phase 4 — Copy data
1. Insert rows into new tables using mapping joins.
2. Rewrite all FK columns through mapping tables.
3. Rewrite polymorphic columns such as `vector_index.entity_id` and `code_content.entity_id` based on `entity_type`.
4. Keep project/watch_dir UUIDs unchanged except type normalization/validation.
5. Do not translate `vector_index.vector_id`; it is a FAISS/vector id, not a DB identity.
6. Preserve `code_chunks.chunk_uuid` as a stable business key distinct from `code_chunks.id`.

### Phase 5 — Validate new tables
1. Row counts match for every migrated table.
2. Mapping-table coverage is complete for every table in the mandatory list.
3. FK integrity holds.
4. Unique constraints hold.
5. Runtime invariant queries return zero bad rows.
6. Polymorphic reference rewrite is validated for every supported `entity_type`.

### Phase 6 — Swap tables
1. Rename old tables to backup names or use the backend-approved rebuild/swap mechanism.
2. Rename new tables to canonical names where supported.
3. Recreate indexes and constraints.
4. Keep old/backup data until runtime verification completes.
5. Runtime write paths must remain stopped during swap.

### Phase 7 — Post-migration verification
1. Run MCP read-only commands.
2. Restart workers.
3. Verify indexing/chunking/vectorization/search.
4. Verify status/diagnostic commands report UUID-shaped IDs and do not claim integer identities.
5. Only then schedule cleanup of backup tables.

## Layering requirements
- Migration orchestration lives in migration module/command.
- Universal schema metadata describes target logical schema.
- Universal driver/adaptation layer maps command-level logical operations to the selected backend contract.
- PostgreSQL table creation/swap SQL belongs in PostgreSQL migration branch.
- SQLite table creation/rebuild SQL belongs in SQLite migration branch.
- Application commands must not contain backend-specific migration SQL.
- Specific drivers must strictly follow the syntax and semantics of their selected DB.

## Must not do
- Do not update PK types in place without a mapping plan.
- Do not drop old tables before verification.
- Do not run while workers are active.
- Do not use file paths as migration keys.
- Do not migrate only `files.id` and leave dependent FKs integer.
- Do not create mapping tables only for examples; use the full mandatory list.
- Do not describe SQLite as optional or partial.
- Do not let SQLite constraints weaken PostgreSQL native UUID implementation.
- Do not let PostgreSQL-only syntax leak into SQLite or universal code.

## Tests required
1. PostgreSQL dry-run migration test on a small DB.
2. SQLite migration/rebuild test on a small DB.
3. Idempotency test: running mapping phase twice reuses UUIDs on both backends.
4. Full mapping-table coverage test: every mandatory mapping table exists and has row-count parity with its source table on both backends.
5. FK rewrite test for files/classes/functions/methods/imports/issues/usages/code_content/AST/CST/chunks/duplicates/snapshots.
6. Polymorphic rewrite test for `vector_index.entity_id` and `code_content.entity_id`.
7. `vector_index.vector_id` preservation test: value remains the FAISS/vector id and is not UUID-converted.
8. `code_chunks.chunk_uuid` preservation/regeneration decision test according to Step 14.
9. Rollback/swap safety test: old/backup data remains available until verification.
10. Queue execution test, if migration is queued: assert `result.command.result.success == true`, not only job `status=completed`.
11. Universal-adaptation tests: same logical command request routes to valid PostgreSQL SQL on PostgreSQL and valid SQLite SQL on SQLite.

## References
- `10-data-migration-postgres-driver-branch.md`
- `11-data-migration-sqlite-driver-branch.md`
- `15-vector-index-and-faiss-mapping.md`
- `18-test-matrix-and-runtime-verification.md`
