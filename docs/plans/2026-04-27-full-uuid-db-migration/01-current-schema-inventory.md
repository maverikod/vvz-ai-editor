# Step 01 — Current schema inventory

## Goal
Build a complete inventory of every integer primary key, integer foreign key, polymorphic identifier, and public API field that must be considered before full UUID migration.

## Architecture constraint
Inventory must be read through the actual project layering:

```text
command/application code -> universal DB/driver contract -> PostgreSQL-specific driver -> PostgreSQL DB
command/application code -> universal DB/driver contract -> SQLite-specific driver -> SQLite DB
```

Both PostgreSQL and SQLite must be fully supported as separate backend-specific implementations. Do not merge backend SQL concerns into the universal layer. Do not let SQLite storage constraints weaken PostgreSQL native UUID design, and do not let PostgreSQL-only syntax leak into the SQLite branch.

## Files to inspect
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py`
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_schema.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_schema.py`
- `code_analysis/core/database/sqlite_to_postgres.py`

## Verified current schema facts
Already verified from schema definition files:

```text
Already UUID-like TEXT PK:
- watch_dirs.id
- watch_dir_paths.watch_dir_id
- projects.id

Still INTEGER autoincrement PK:
- files.id
- classes.id
- methods.id
- functions.id
- entity_cross_ref.id
- imports.id
- issues.id
- usages.id
- code_content.id
- ast_trees.id
- cst_trees.id
- vector_index.id
- code_chunks.id
- code_duplicates.id
- duplicate_occurrences.id
- comprehensive_analysis_results.id
- file_tree_snapshots.id
- file_tree_snapshot_nodes.id
```

## Required investigation
Create a table inventory with columns:

```text
table
column
current_type
current_role
references
on_delete
unique/index participation
public_api_exposed yes/no
migration_target_type
migration_risk
```

Every row must identify which layer owns the change:

```text
command/application
universal DB/driver contract
PostgreSQL-specific driver/schema/migration
SQLite-specific driver/schema/migration
```

## Must include these relationships

### Core entities
```text
files.id -> classes.file_id
files.id -> functions.file_id
files.id -> imports.file_id
files.id -> issues.file_id
files.id -> usages.file_id
files.id -> code_content.file_id
files.id -> ast_trees.file_id
files.id -> cst_trees.file_id
files.id -> code_chunks.file_id
files.id -> duplicate_occurrences.file_id
files.id -> comprehensive_analysis_results.file_id
files.id -> file_tree_snapshots.file_id
files.id -> entity_cross_ref.file_id
```

### Class/function/method graph
```text
classes.id -> methods.class_id
classes.id -> issues.class_id
classes.id -> code_chunks.class_id
classes.id -> entity_cross_ref.caller_class_id
classes.id -> entity_cross_ref.callee_class_id

functions.id -> issues.function_id
functions.id -> code_chunks.function_id
functions.id -> entity_cross_ref.caller_function_id
functions.id -> entity_cross_ref.callee_function_id

methods.id -> issues.method_id
methods.id -> code_chunks.method_id
methods.id -> entity_cross_ref.caller_method_id
methods.id -> entity_cross_ref.callee_method_id
```

### Duplicates/snapshots
```text
code_duplicates.id -> duplicate_occurrences.duplicate_id
file_tree_snapshots.id -> file_tree_snapshot_roots.snapshot_id
file_tree_snapshots.id -> file_tree_snapshot_nodes.snapshot_id
```

### Polymorphic entity references
```text
vector_index.entity_id currently INTEGER
vector_index.entity_type determines what entity_id points to

code_content.entity_id currently follows an entity-type-dependent reference pattern
code_content.entity_type determines what entity_id points to
```

This is the highest-risk area. It must be mapped before implementation. The inventory must make an explicit design decision for both `vector_index.entity_id` and `code_content.entity_id`:

```text
Option A: entity_type + UUID entity_id
Option B: typed nullable UUID FK columns
Option C: unified entities table
```

The plan must not silently preserve an integer polymorphic `entity_id` after migrating entity tables to UUID.

## Required output
Create or update:

```text
docs/plans/2026-04-27-full-uuid-db-migration/schema_inventory.md
```

The inventory must be complete before any schema changes.

## Tests / verification
No code changes in this step. Verify by reading these files and recording observations:

```text
read_project_text_file(schema_definition_tables_core.py)
read_project_text_file(schema_definition_tables_mid.py)
read_project_text_file(schema_definition_tables_rest.py)
read_project_text_file(schema_definition_indexes.py)
read_project_text_file(schema_sync_sql.py)
read_project_text_file(schema_sync_sql_postgres.py)
```

If MCP text reading for Python files is unavailable or routed through a Python parser incorrectly, record that as a tool limitation and verify with the nearest available structural/search command instead. Do not skip the verification requirement.

## Must not do
- Do not edit schema yet.
- Do not add migrations yet.
- Do not touch live data.
- Do not assume `id` always means the same entity type.
- Do not describe SQLite as optional or partial; it is a full backend-specific target.
- Do not mix PostgreSQL and SQLite SQL in the universal layer.

## References
- Next: `02-uuid-generation-and-type-policy.md`
- Index constraints: `08-indexes-and-constraints.md`
