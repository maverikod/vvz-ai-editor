# Step 11 — SQLite full backend-specific migration branch

## Goal
Define the SQLite branch as a full supported backend-specific implementation of the same logical UUID identity migration. SQLite must be handled separately from PostgreSQL and must strictly follow SQLite syntax, storage rules, table-rebuild constraints, FTS behavior, rowid semantics, and driver behavior.

## Architecture constraint
The required layering is:

```text
command/application code
-> universal DB/driver contract and selected-backend adaptation layer
-> SQLite-specific driver/schema/migration
-> SQLite DB
```

Commands emit backend-neutral logical requests. The universal driver/adaptation layer selects SQLite when SQLite is configured and adapts those logical requests to the SQLite backend contract. The SQLite-specific driver/schema/migration branch must then execute SQLite-valid SQL only. PostgreSQL `UUID`, casts, `RETURNING` assumptions, and PostgreSQL DDL must not leak into SQLite.

## Backend policy
Both PostgreSQL and SQLite are full supported backends for the UUID migration plan.

```text
PostgreSQL branch: logical UUID -> native PostgreSQL UUID.
SQLite branch: logical UUID -> canonical UUID TEXT.
```

SQLite is not optional, deprecated, or test-only in this plan. If a specific SQLite operation cannot be implemented in place because of SQLite limitations, the SQLite branch must provide a safe SQLite-native rebuild/reindex path with explicit behavior and tests.

## Files to inspect/edit
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_run.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_schema.py`
- SQLite migration/rebuild tests
- SQLite driver insert/CRUD/indexing/chunk/search tests

## Required investigation
1. Verify generic schema definitions can express logical UUID and SQLite maps it to canonical TEXT.
2. Verify SQLite insert contract can return explicit UUID string IDs for UUID/TEXT PK tables.
3. Verify SQLite table rebuild is used where SQLite cannot alter PK/FK types in place.
4. Verify SQLite FTS5 `code_content_fts` and rowid behavior are handled explicitly after `code_content.id` becomes UUID/TEXT.
5. Verify SQLite indexes, constraints, unique keys, and FK behavior match the logical schema as closely as SQLite permits.
6. Verify SQLite runtime paths do not depend on integer `lastrowid` for migrated UUID tables.

## Required migration/rebuild strategy
SQLite may use a backend-native rebuild strategy where PostgreSQL uses in-place mapped migration. This is acceptable only if it preserves logical behavior and is fully tested.

Required behavior:

```text
old integer ids -> explicit mapping tables -> canonical UUID TEXT ids
old tables -> backup/rebuild tables -> canonical tables
FKs rewritten through mapping tables
polymorphic references rewritten according to the shared design
FTS/rowid behavior rebuilt or explicitly adapted
```

The mapping-table coverage must match Step 09. SQLite uses canonical UUID TEXT for `new_id`, not PostgreSQL UUID type.

## Required changes
1. Map logical UUID type to SQLite TEXT.
2. Ensure explicit UUID `id` insert works for all migrated tables.
3. Ensure SQLite driver insert returns explicit UUID string for UUID/TEXT PK inserts or a typed result that exposes it.
4. Replace integer-identity `lastrowid` assumptions for migrated UUID tables.
5. Rebuild tables where SQLite cannot alter PK/FK types directly.
6. Rebuild or adapt SQLite FTS5 structures that depend on integer rowid behavior.
7. Validate `projects.id` and `watch_dirs.id` as canonical UUID TEXT.
8. Keep PostgreSQL-specific DDL and casts out of the SQLite branch.

## Layering requirements
- SQLite-specific behavior belongs in SQLite driver/schema/migration branch.
- Universal layer adapts logical requests to the selected SQLite backend contract.
- Generic application code should work with UUID strings on both backends.
- PostgreSQL migration must not contain SQLite fallbacks.
- SQLite migration must not contain PostgreSQL syntax.

## Must not do
- Do not run PostgreSQL migration SQL on SQLite.
- Do not preserve integer DB identities in generic code just for SQLite.
- Do not pretend PostgreSQL and SQLite FTS are equivalent.
- Do not silently ignore unsupported SQLite rebuild/migration steps.
- Do not describe SQLite as optional, partial, deprecated, or test-only.
- Do not let SQLite rowid behavior leak into the universal driver contract.

## Tests required
1. Fresh SQLite schema creates UUID-as-TEXT IDs for every migrated identity table.
2. SQLite migration/rebuild maps every mandatory mapping table from Step 09.
3. Insert/read works for files/classes/functions/methods/imports/issues/usages/code_content/AST/CST/chunks/duplicates/snapshots with UUID string IDs.
4. SQLite driver insert returns UUID string or typed identity result for explicit UUID/TEXT PK insert.
5. SQLite driver still returns integer only for tables that genuinely remain integer identities.
6. SQLite FTS either works with the new UUID/TEXT design or is rebuilt through a documented SQLite-native design.
7. SQLite runtime verification covers create project, index small project, chunking, vectorization/search where supported, and MCP API output ID types.

## Runtime verification
For SQLite backend:

```text
create fresh SQLite test DB
create project
index small test project
run get_database_status
run list_project_files
run semantic_search where vector/search is enabled
run representative AST/CST/entity queries
```

Expected:
- UUID string IDs work in SQLite backend;
- migrated DB identities are not exposed as integers;
- SQLite-specific FTS/rowid behavior is correct or explicitly rebuilt;
- no PostgreSQL syntax appears in SQLite execution logs/errors.

## References
- `02-uuid-generation-and-type-policy.md`
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `09-migration-framework-and-id-map.md`
- `10-data-migration-postgres-driver-branch.md`
- `18-test-matrix-and-runtime-verification.md`
