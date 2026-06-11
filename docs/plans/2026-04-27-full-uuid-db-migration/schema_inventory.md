# Schema inventory for full UUID database migration

## Status
This is the required output artifact for Step 01. It is a structured inventory template plus the facts already verified from the current code. Complete this file before any schema migration implementation.

## Backend and layering policy
Both PostgreSQL and SQLite are full supported backends for this migration.

Required architecture:

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

Commands emit backend-neutral logical requests. The universal driver/adaptation layer selects the configured backend and adapts logical requests to that backend contract. Specific drivers must strictly follow their DB syntax and behavior:

```text
PostgreSQL: native UUID columns, PostgreSQL DDL/casts/placeholders/RETURNING/UPSERT rules.
SQLite: canonical UUID TEXT columns, SQLite DDL/rebuild/placeholders/UPSERT/FTS/rowid rules.
```

Do not put PostgreSQL SQL into universal or SQLite code. Do not put SQLite rowid/FTS assumptions into universal or PostgreSQL code.

## Source files to verify

```text
code_analysis/core/database/schema_definition_tables_core.py
code_analysis/core/database/schema_definition_tables_mid.py
code_analysis/core/database/schema_definition_tables_rest.py
code_analysis/core/database/schema_definition_indexes.py
code_analysis/core/database/schema_sync_sql.py
code_analysis/core/database/schema_sync_sql_postgres.py
code_analysis/core/database/schema_creation_migrate.py
code_analysis/core/database_driver_pkg/drivers/base.py
code_analysis/core/database_driver_pkg/drivers/postgres.py
code_analysis/core/database_driver_pkg/drivers/postgres_operations.py
code_analysis/core/database_driver_pkg/drivers/postgres_run.py
code_analysis/core/database_driver_pkg/drivers/postgres_schema.py
code_analysis/core/database_driver_pkg/drivers/sqlite.py
code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py
code_analysis/core/database_driver_pkg/drivers/sqlite_run.py
code_analysis/core/database_driver_pkg/drivers/sqlite_schema.py
```

## Verified current root IDs

```text
watch_dirs.id: TEXT primary key, UUID-like, already application supplied
watch_dir_paths.watch_dir_id: TEXT primary key / FK -> watch_dirs.id
projects.id: TEXT primary key, UUID-like, already application supplied
projects.watch_dir_id: TEXT nullable FK -> watch_dirs.id
```

Do not regenerate existing project/watch_dir IDs during integer-to-UUID migration. Validate them as canonical UUIDs. After migration:

```text
PostgreSQL stores them as native UUID.
SQLite stores them as canonical UUID TEXT.
MCP/API represents them as UUID strings on both backends.
```

## Verified current integer primary keys

```text
files.id
classes.id
methods.id
functions.id
entity_cross_ref.id
imports.id
issues.id
usages.id
code_content.id
ast_trees.id
cst_trees.id
vector_index.id
code_chunks.id
code_duplicates.id
duplicate_occurrences.id
comprehensive_analysis_results.id
file_tree_snapshots.id
file_tree_snapshot_nodes.id
```

## Verified current integer foreign/reference columns

```text
classes.file_id -> files.id
functions.file_id -> files.id
methods.class_id -> classes.id
entity_cross_ref.file_id -> files.id
entity_cross_ref.caller_class_id -> classes.id
entity_cross_ref.callee_class_id -> classes.id
entity_cross_ref.caller_method_id -> methods.id
entity_cross_ref.callee_method_id -> methods.id
entity_cross_ref.caller_function_id -> functions.id
entity_cross_ref.callee_function_id -> functions.id
imports.file_id -> files.id
issues.file_id -> files.id
issues.class_id -> classes.id
issues.function_id -> functions.id
issues.method_id -> methods.id
usages.file_id -> files.id
code_content.file_id -> files.id
code_content.entity_id -> polymorphic entity id, no direct FK
ast_trees.file_id -> files.id
cst_trees.file_id -> files.id
vector_index.entity_id -> polymorphic entity id, no direct FK
code_chunks.file_id -> files.id
code_chunks.class_id -> classes.id
code_chunks.function_id -> functions.id
code_chunks.method_id -> methods.id
duplicate_occurrences.duplicate_id -> code_duplicates.id
duplicate_occurrences.file_id -> files.id
comprehensive_analysis_results.file_id -> files.id
file_tree_snapshots.file_id -> files.id
file_tree_snapshot_roots.snapshot_id -> file_tree_snapshots.id
file_tree_snapshot_nodes.snapshot_id -> file_tree_snapshots.id
```

## Columns that must remain integer unless separately redesigned

```text
vector_id: FAISS/vector-storage id, not database identity
line
end_line
chunk_ordinal
binding_level
token_count
complexity
files.lines
worker counters/stat counters
```

## Required inventory table
Fill this table for every migrated column.

```text
table:
column:
current_type:
current_role: primary_key | foreign_key | polymorphic_reference | non_identity
references:
on_delete:
unique/index participation:
public_api_exposed: yes/no/unknown
migration_target_type: logical UUID
postgresql_storage_type: UUID | keep INTEGER
sqlite_storage_type: canonical UUID TEXT | keep INTEGER
migration_risk:
owner_step:
owner_layer: command/application | universal adaptation | PostgreSQL-specific branch | SQLite-specific branch
```

## Mandatory mapping-table coverage checklist
The migration must create and validate mapping tables for every currently integer primary key listed below. This is a mandatory list, not an example. PostgreSQL `new_id` is native UUID. SQLite `new_id` is canonical UUID TEXT.

```text
[ ] uuid_migration_files -> files.id
[ ] uuid_migration_classes -> classes.id
[ ] uuid_migration_methods -> methods.id
[ ] uuid_migration_functions -> functions.id
[ ] uuid_migration_entity_cross_ref -> entity_cross_ref.id
[ ] uuid_migration_imports -> imports.id
[ ] uuid_migration_issues -> issues.id
[ ] uuid_migration_usages -> usages.id
[ ] uuid_migration_code_content -> code_content.id
[ ] uuid_migration_ast_trees -> ast_trees.id
[ ] uuid_migration_cst_trees -> cst_trees.id
[ ] uuid_migration_vector_index -> vector_index.id
[ ] uuid_migration_code_chunks -> code_chunks.id
[ ] uuid_migration_code_duplicates -> code_duplicates.id
[ ] uuid_migration_duplicate_occurrences -> duplicate_occurrences.id
[ ] uuid_migration_comprehensive_analysis_results -> comprehensive_analysis_results.id
[ ] uuid_migration_file_tree_snapshots -> file_tree_snapshots.id
[ ] uuid_migration_file_tree_snapshot_nodes -> file_tree_snapshot_nodes.id
```

For each mapping table verify on both backends:

```text
source row count == mapping row count
old_id unique
new_id unique
new_id is valid UUID
all copied FK values can be joined through the mapping table
```

## Special mapping decision: file_tree_snapshot_roots
`file_tree_snapshot_roots` is not listed as a normal autoincrement-id mapping table because it must receive an explicit design decision first. Default decision unless code proves a separate identity is required:

```text
rewrite file_tree_snapshot_roots.snapshot_id through uuid_migration_file_tree_snapshots
```

Do not invent a separate mapping table for `file_tree_snapshot_roots` unless the schema/code proves it has a separate root identity.

## High-risk design decisions

### 1. Driver insert return contract
Current driver code assumes integer insert result. This must be fixed before UUID schema work.

Owner:
```text
03-driver-layer-boundaries.md
04-driver-insert-return-contract.md
```

Required outcome:
```text
Base/universal insert contract is UUID-safe.
Universal adaptation routes logical insert requests to selected backend behavior.
PostgreSQL insert never returns 0 for UUID primary keys.
SQLite insert returns explicit UUID/TEXT identities for migrated UUID tables.
Application code does not rely on integer lastrowid for migrated UUID tables.
```

### 2. Polymorphic references
These cannot be enforced by a simple FK without design choice:

```text
code_content.entity_id
vector_index.entity_id
```

Owner:
```text
06-schema-mid-ast-cst-chunks-vector-index.md
13-indexing-ast-cst-entity-writes.md
15-vector-index-and-faiss-mapping.md
```

Required decision:
```text
Option A: entity_type + UUID entity_id
Option B: typed nullable UUID FK columns
Option C: unified entities table
```

### 3. Chunk UUID formula
`chunk_uuid` is a separate stable key and currently depends on `file_id` in the input string. After file_id becomes UUID, new chunk UUID generation must be explicit/versioned.

Owner:
```text
14-docstring-chunks-and-chunk-uuid.md
```

Required distinction:
```text
code_chunks.id: migrated DB UUID PK
code_chunks.chunk_uuid: stable business key, not the DB PK
code_chunks.project_id: UUID-shaped denormalized project reference
vector_index.vector_id: FAISS/vector id, not UUID
```

### 4. SQLite FTS / rowid
SQLite FTS5 rowid behavior is valid only inside the SQLite-specific branch. It must not leak into PostgreSQL UUID migration or the universal driver contract.

Owner:
```text
08-indexes-and-constraints.md
11-data-migration-sqlite-driver-branch.md
17-cleanup-trash-repair-commands.md
```

### 5. MCP/API diagnostics
Status and diagnostic commands must not claim integer DB identities after migration.

Owner:
```text
16-mcp-api-compatibility.md
18-test-matrix-and-runtime-verification.md
```

Required samples:
```text
get_database_status
list_project_files
semantic_search
list_code_entities
get_imports
```

Diagnostics must distinguish API representation from backend storage where relevant:

```text
PostgreSQL: UUID storage
SQLite: canonical UUID TEXT storage
```

## Required invariant diagnostics for migration

```sql
-- Chunk ownership consistency
SELECT COUNT(*)
FROM code_chunks cc
JOIN files f ON f.id = cc.file_id
WHERE cc.project_id != f.project_id;
```

```sql
-- Orphan chunks
SELECT COUNT(*)
FROM code_chunks cc
LEFT JOIN files f ON f.id = cc.file_id
WHERE f.id IS NULL;
```

```sql
-- Orphan structural indexes
SELECT COUNT(*) FROM ast_trees a LEFT JOIN files f ON f.id = a.file_id WHERE f.id IS NULL;
SELECT COUNT(*) FROM cst_trees c LEFT JOIN files f ON f.id = c.file_id WHERE f.id IS NULL;
```

```sql
-- Same active absolute path in multiple projects is diagnostic
SELECT path, COUNT(DISTINCT project_id)
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY path
HAVING COUNT(DISTINCT project_id) > 1;
```

Backend-specific UUID validation:

```text
PostgreSQL: SELECT id::uuid FROM projects; SELECT id::uuid FROM watch_dirs;
SQLite: validate projects.id and watch_dirs.id with SQLite-safe canonical UUID string checks, not PostgreSQL casts.
```

## Completion checklist
- Every integer PK is assigned an owner step.
- Every FK/reference to a migrated PK is assigned an owner step.
- Every mandatory mapping table is present in the migration plan.
- Every mapping table has row-count parity and uniqueness checks on both backends.
- `file_tree_snapshot_roots` has an explicit design decision.
- Every public MCP field exposing an integer DB identity is listed for Step 16.
- Polymorphic ID strategy is chosen before implementation.
- Driver insert contract is fixed before UUID schema changes.
- Universal adaptation routes logical requests to the selected backend.
- PostgreSQL branch uses native PostgreSQL UUID behavior.
- SQLite branch uses canonical UUID TEXT and SQLite-native rebuild/FTS/rowid behavior.
- Runtime verification through MCP is required before declaring completion.
