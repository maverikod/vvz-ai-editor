# Step 02 — UUID generation and type policy

## Goal
Define one logical UUID policy with two full backend-specific implementations: PostgreSQL and SQLite.

## Direction
Both PostgreSQL and SQLite must be fully supported. The universal layer must express a backend-neutral logical UUID contract, and each backend-specific branch must implement that contract according to its DB capabilities. The required layering is:

```text
command/application code -> universal DB/driver contract -> PostgreSQL-specific driver -> PostgreSQL DB
command/application code -> universal DB/driver contract -> SQLite-specific driver -> SQLite DB
```

PostgreSQL-specific choices must not leak into the universal layer. SQLite-specific storage/workaround choices must not weaken the PostgreSQL branch. PostgreSQL and SQLite must be tested as separate complete backend implementations, not as one backend plus a partial compatibility fallback.

## Current state
`watch_dirs.id` and `projects.id` are already TEXT UUID-like primary keys. Remaining internal identity columns are mostly `INTEGER autoincrement`.

## Files to inspect
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_schema.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_schema.py`
- `code_analysis/core/database/schema_creation_migrate.py`

## Required policy decisions

### Universal logical schema
The universal layer should describe logical intent, not backend syntax.

Required logical type:

```text
UUID
```

The generic schema definition may use this logical type once both backend-specific DDL generators know how to map it. This makes both backends first-class implementations of the same logical schema, not equal SQL dialects in the universal layer.

### PostgreSQL branch
PostgreSQL-specific DDL must map logical `UUID` to native PostgreSQL `UUID` columns.

Allowed in PostgreSQL-specific driver/migration code only:

```sql
UUID
DEFAULT gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto
```

But application inserts should preferably generate UUID4 in Python unless a PostgreSQL-only migration/default explicitly owns generation.

### SQLite branch
SQLite-specific DDL must map logical `UUID` to a SQLite-supported representation, normally canonical UUID `TEXT`.

SQLite stores UUID values as canonical UUID strings. SQLite support must live in the SQLite driver/schema/migration branch, not in generic worker/command code. SQLite must pass its own full schema, migration/rebuild, CRUD, indexing, chunking, search, and MCP API tests.

### UUID generation
Default policy:
- Generate UUID4 in Python at application/migration boundaries unless a backend-specific branch explicitly owns generation.
- Validate canonical UUID string format at MCP/API boundaries where needed.
- Do not generate primary keys from paths.
- Do not use deterministic UUID5 for primary keys.

### ID naming
Full replacement target:
- primary key column remains `id`;
- type changes from integer/autoincrement to logical UUID;
- backend-specific DDL maps it to PostgreSQL UUID or SQLite TEXT.

During migration:
- mapping tables/temporary columns must use explicit names: `old_int_id`, `new_uuid_id`.
- no ambiguous string-cast of old integer IDs.

## Required output
Update:

```text
docs/plans/2026-04-27-full-uuid-db-migration/schema_inventory.md
```

with a policy section covering:
- logical UUID type;
- PostgreSQL native UUID mapping;
- SQLite canonical TEXT UUID mapping;
- UUID generation;
- API representation.

## Must not do
- Do not put PostgreSQL `UUID` syntax in generic worker code.
- Do not put SQLite `TEXT` workaround into PostgreSQL DDL.
- Do not silently coerce integer IDs to strings without a migration map.
- Do not make chunks infer ownership by path.
- Do not describe SQLite as optional or partial. It must be a full backend-specific implementation.
- Do not make either backend's SQL dialect leak into the universal layer.

## Tests required later
1. PostgreSQL DDL maps logical UUID to native `UUID`.
2. SQLite DDL maps logical UUID to canonical UUID `TEXT`.
3. Python insert paths generate valid UUID4 where application-owned.
4. Existing UUID-like project/watch_dir IDs remain valid.
5. Generic schema definition contains no backend-specific SQL fragments.
6. PostgreSQL backend passes full migration/runtime tests.
7. SQLite backend passes full migration/rebuild/runtime tests.

## References
- `03-driver-layer-boundaries.md`
- `09-migration-framework-and-id-map.md`
- `10-data-migration-postgres-driver-branch.md`
- `11-data-migration-sqlite-driver-branch.md`
