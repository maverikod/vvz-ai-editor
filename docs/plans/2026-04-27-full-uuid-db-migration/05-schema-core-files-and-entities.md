# Step 05 — Core schema: files, classes, functions, methods, entity_cross_ref

## Goal
Convert the core identity graph from integer PK/FK columns to PostgreSQL-first UUID columns after the driver insert contract is fixed.

## Current code checked
`schema_definition_tables_core.py` currently defines:

```text
files.id INTEGER autoincrement PK
classes.id INTEGER autoincrement PK
classes.file_id INTEGER FK -> files.id
functions.id INTEGER autoincrement PK
functions.file_id INTEGER FK -> files.id
methods.id INTEGER autoincrement PK
methods.class_id INTEGER FK -> classes.id
entity_cross_ref.id INTEGER autoincrement PK
entity_cross_ref.file_id INTEGER FK -> files.id
entity_cross_ref.caller_class_id / callee_class_id INTEGER FK -> classes.id
entity_cross_ref.caller_method_id / callee_method_id INTEGER FK -> methods.id
entity_cross_ref.caller_function_id / callee_function_id INTEGER FK -> functions.id
```

`projects.id` and `watch_dirs.id` are already UUID-like TEXT and should be migrated/validated as PostgreSQL UUID separately, not regenerated.

## Prerequisites
Complete first:
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`

Do not change core schema to UUID while driver insert contract still returns `int` or returns `0` for non-integer PostgreSQL IDs.

## Files to edit in this step
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py` only if logical UUID type mapping is missing
- tests for schema definitions / PostgreSQL DDL

## Target schema
PostgreSQL-first target:

```text
files.id UUID PRIMARY KEY
files.project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE
files.watch_dir_id UUID NULL REFERENCES watch_dirs(id) ON DELETE SET NULL
classes.id UUID PRIMARY KEY
classes.file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE
functions.id UUID PRIMARY KEY
functions.file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE
methods.id UUID PRIMARY KEY
methods.class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE
entity_cross_ref.id UUID PRIMARY KEY
entity_cross_ref.file_id UUID NULL REFERENCES files(id) ON DELETE SET NULL
entity_cross_ref.*_class_id UUID NULL REFERENCES classes(id) ON DELETE CASCADE
entity_cross_ref.*_method_id UUID NULL REFERENCES methods(id) ON DELETE CASCADE
entity_cross_ref.*_function_id UUID NULL REFERENCES functions(id) ON DELETE CASCADE
```

## Required design decision
Keep existing uniqueness semantics but update column types:

```text
files UNIQUE(project_id, path)
classes UNIQUE(file_id, name, line)
functions UNIQUE(file_id, name, line)
methods UNIQUE(class_id, name, line)
```

Do not introduce path-based identity.

## Required code changes
1. Add or use a logical UUID type in schema definitions.
2. PostgreSQL DDL must emit `UUID`, not `INTEGER GENERATED ...`, for these identity columns.
3. Remove `autoincrement` from UUID primary key definitions.
4. Ensure all future insert paths provide UUID4 values explicitly or use a verified PostgreSQL UUID default through the PostgreSQL-specific layer.
5. Keep project/watch_dir IDs stable and validate/cast them as UUID during migration.

## Layering requirements
- Schema definitions express logical identity and relationships.
- PostgreSQL-specific DDL mapping belongs in `schema_sync_sql_postgres.py` or a PostgreSQL schema branch.
- Runtime CRUD changes belong to Step 12, not this file.
- Data migration belongs to Step 10.

## Must not do
- Do not update `files.crud.add_file` here; see Step 12.
- Do not change chunk/vector logic here.
- Do not change `chunk_uuid` here.
- Do not regenerate project/watch_dir ids.
- Do not use SQLite limitations to weaken PostgreSQL UUID design.

## Tests required
1. Schema definition test: all core PK/FK identity columns are UUID/logical UUID.
2. PostgreSQL DDL test: generated DDL uses UUID-compatible columns.
3. Constraint test: `UNIQUE(project_id, path)` remains on files.
4. FK graph test: classes/functions/methods/entity_cross_ref reference UUID columns.
5. Regression test: schema DDL no longer emits integer identity for migrated core IDs.

## Verification
No live DB migration in this step. Verify generated PostgreSQL DDL and schema metadata only.

## References
- `01-current-schema-inventory.md`
- `02-uuid-generation-and-type-policy.md`
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `09-migration-framework-and-id-map.md`
- `12-file-crud-and-path-identity.md`
