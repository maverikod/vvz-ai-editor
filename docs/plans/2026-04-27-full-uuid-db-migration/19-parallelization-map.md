# Step 19 — Parallelization map for full UUID migration

## Goal
Split the full UUID migration into safe parallel work blocks. Each block must have clear ownership, non-overlapping files, dependencies, backend ownership, and verification.

## Global rule
Each performer owns only the files listed in their block. Do not edit `.venv`, `site-packages`, installed packages, `mcp-proxy-adapter`, or `queuemgr`. Do not edit files owned by another block unless the coordinator explicitly reassigns ownership.

## Architecture rule
All blocks must preserve this layering:

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

Both PostgreSQL and SQLite are full supported backends. The universal layer receives backend-neutral command requests and adapts them to the selected backend contract. Each specific driver must strictly follow the syntax, feature set, and behavioral constraints of its own DB.

## Critical serialization rules

### Rule 1 — Inventory and driver contract before schema edits
Steps 01–04 must complete before schema implementation starts. The schema must not switch to UUID while the universal driver insert contract is still integer-only.

### Rule 2 — Schema before runtime writes
Steps 05–08 define logical schema and backend mappings. Runtime write paths in Steps 12–15 must not be changed until schema target and backend mapping rules are stable.

### Rule 3 — Migration framework before data migration
Step 09 must complete before Steps 10 and 11. Do not implement either PostgreSQL or SQLite migration/rebuild without mapping tables, preflight checks, and explicit migration-state ownership.

### Rule 4 — Both backend migration branches are required
Step 10 owns the PostgreSQL-specific migration branch. Step 11 owns the SQLite-specific migration/rebuild branch. Neither branch may constrain the other branch's SQL design, but both must implement the same logical UUID contract.

### Rule 5 — Vector/FAISS IDs are separate
Step 15 owns the boundary between UUID DB ids and integer FAISS `vector_id`. No other block may convert `vector_id` to UUID.

### Rule 6 — MCP API after field semantics are stable
Step 16 may start with inventory, but final schema/API updates must wait for Steps 12–15 decisions and both backend storage mappings.

### Rule 7 — Migration state and migration command are single-owner
Block E is the only owner of shared migration state tables, migration command execution, migration locking/maintenance-mode semantics, backup-table naming, swap/rebuild execution, and rollback state. Other blocks may define schema/write-path requirements, but must not create migration-state tables or migration execution commands.

### Rule 8 — Runtime write paths must not run during swap/rebuild
Blocks F/G/I may implement and test runtime write/read behavior before final migration execution, but their write paths must not run concurrently with Block E PostgreSQL swap or SQLite rebuild/swap. During preflight, copy, validation, swap, or rebuild, workers and mutation commands must be stopped or maintenance-gated.

## Work blocks

## Block A — Inventory, UUID policy, driver contract, universal adaptation

### Owns
- `01-current-schema-inventory.md`
- `02-uuid-generation-and-type-policy.md`
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `schema_inventory.md`

### Source files allowed
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- read-only schema files for inventory
- driver contract tests
- universal selected-backend adaptation tests

### Deliverable
- Complete inventory of integer PK/FK columns.
- UUID policy for both PostgreSQL and SQLite.
- Universal driver insert contract can return UUID strings.
- Universal driver/adaptation layer routes logical command requests to the selected backend.
- PostgreSQL insert does not return `0` for UUID primary keys.
- SQLite insert returns explicit UUID/TEXT identity for migrated UUID tables.

## Block B — Core schema

### Owns
- `05-schema-core-files-and-entities.md`

### Source files allowed
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- backend schema definition tests

### Must coordinate with
- Block A for driver/policy/adaptation.
- Block C for mid-layer FKs.
- Block E for migration mapping.

### Deliverable
- Core logical schema uses UUID ids for files/classes/functions/methods/entity_cross_ref.
- PostgreSQL maps logical UUID to native UUID.
- SQLite maps logical UUID to canonical TEXT.

## Block C — Mid schema and polymorphic references

### Owns
- `06-schema-mid-ast-cst-chunks-vector-index.md`

### Source files allowed
- `code_analysis/core/database/schema_definition_tables_mid.py`
- backend schema tests for mid schema

### Must coordinate with
- Block B for FK targets.
- Block G for vector_index/entity_id semantics.
- Block F for chunk_uuid/chunk persistence.

### Deliverable
- Mid schema UUID migration design implemented for both backends.
- Polymorphic fields have explicit chosen design.
- `vector_id` remains integer.

## Block D — Rest schema and indexes

### Owns
- `07-schema-rest-duplicates-analysis-snapshots.md`
- `08-indexes-and-constraints.md`

### Source files allowed
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py`
- PostgreSQL index generation tests
- SQLite index/FTS/rowid tests

### Must coordinate with
- Block E for migration order.
- Block H for cleanup/trash behavior.

### Deliverable
- Rest tables and indexes are UUID-compatible on both backends.
- PostgreSQL partial index predicates are correct.
- SQLite FTS/rowid behavior is SQLite-native and does not leak into PostgreSQL or universal code.

## Block E — Migration framework, migration state, and backend migrations

### Owns
- `09-migration-framework-and-id-map.md`
- `10-data-migration-postgres-driver-branch.md`
- `11-data-migration-sqlite-driver-branch.md`
- migration-state tables and diagnostics
- migration command entrypoints
- migration maintenance-mode / lock semantics
- backup-table naming and swap/rebuild execution
- migration rollback state

### Source files allowed
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database/schema_sync_sql.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- new `code_analysis/core/database/migrations/*`
- migration command modules, if introduced specifically for UUID migration
- PostgreSQL migration tests
- SQLite migration/rebuild tests

### Must coordinate with
- Blocks B/C/D before implementing backend migration SQL.
- Block F before allowing runtime write paths to run on migrated schema.
- Block G before migrating vector_index polymorphic references.
- Block I before runtime MCP verification.

### Deliverable
- Idempotent PostgreSQL migration with full mapping-table coverage, preflight, validation, safe swap, migration-state diagnostics, and rollback/backup documentation.
- SQLite migration/rebuild with full mapping-table coverage, preflight, validation, backend-native rebuild/swap behavior, migration-state diagnostics, and rollback/backup documentation.

### Must not do
- Do not let any other block own migration-state tables or migration command execution.
- Do not run swap/rebuild while runtime write paths, workers, or mutation commands are active.
- Do not treat queue `completed` as success without checking nested command success.
- Do not mix PostgreSQL and SQLite SQL in one backend branch.

## Block F — File CRUD, indexing, chunks

### Owns
- `12-file-crud-and-path-identity.md`
- `13-indexing-ast-cst-entity-writes.md`
- `14-docstring-chunks-and-chunk-uuid.md`

### Source files allowed
- `code_analysis/core/database/files/crud.py`
- `code_analysis/core/database/files/update.py`
- `code_analysis/commands/update_indexes_analyzer.py`
- structural indexing modules
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- `code_analysis/core/database/code_chunk_sql.py`
- related tests

### Must coordinate with
- Block B/C for schema.
- Block E for migration mapping and maintenance windows.
- Block G for vector/chunk IDs.

### Deliverable
- Runtime write paths create/use UUID ids on both backends.
- `chunk_uuid` strategy is explicit and tested.
- No `_lastrowid()` dependency for migrated UUID tables.
- Backend-specific SQL stays in backend-specific driver/adaptation code.

### Must not do
- Do not execute runtime write paths during Block E migration preflight/copy/validation/swap/rebuild.
- Do not create or mutate migration-state tables.

## Block G — Vectorization, FAISS, search mapping

### Owns
- `15-vector-index-and-faiss-mapping.md`

### Source files allowed
- `code_analysis/core/vectorization_worker_pkg/*`
- FAISS manager modules
- semantic search command/modules
- vectorization/search tests

### Must coordinate with
- Block C for `vector_index.entity_id` design.
- Block F for `code_chunks.id` and `chunk_uuid` behavior.
- Block E for migration window and vector-index copy/validation semantics.
- Block I for MCP result fields.

### Deliverable
- UUID DB ids and integer FAISS `vector_id` are clearly separated.
- Search works after UUID migration on each backend where vector/search is supported.

### Must not do
- Do not run vectorization workers during Block E swap/rebuild.
- Do not convert `vector_id` to UUID.

## Block H — Cleanup, trash, repair

### Owns
- `17-cleanup-trash-repair-commands.md`

### Source files allowed
- project trash/delete/restore commands
- cleanup/repair DB helpers
- tests for trash lifecycle

### Must coordinate with
- Block E for migration backup tables.
- Block D for PostgreSQL and SQLite FTS/rowid policy.

### Deliverable
- Cleanup and destructive commands are UUID-safe and backend-aware.
- PostgreSQL cleanup uses PostgreSQL-valid SQL.
- SQLite cleanup uses SQLite-valid SQL.

## Block I — MCP API and final verification

### Owns
- `16-mcp-api-compatibility.md`
- `18-test-matrix-and-runtime-verification.md`

### Source files allowed
- MCP command metadata/results under `code_analysis/commands/**`
- command schema/help tests
- integration verification scripts/tests

### Must coordinate with
- All blocks before final field/type assertions.
- Block E for migration-state/status diagnostics.

### Deliverable
- MCP APIs expose UUID strings for migrated DB identities.
- Status/diagnostic commands do not claim migrated DB identities are integers.
- Diagnostics distinguish PostgreSQL UUID storage from SQLite canonical TEXT storage where relevant.
- Runtime verification matrix passes on both backends.

## Recommended waves

### Wave 1 — Read-only/design + driver contract
Can run in parallel:
- Block A inventory/policy/driver contract/adaptation.
- Block D rest/index audit.
- Block I API field inventory.
- Block G vector/search inventory.

### Wave 2 — Schema implementation
Order:
1. Block B core logical schema and backend mappings.
2. Block C mid schema.
3. Block D rest/index schema.

### Wave 3 — Migration implementation
Order:
1. Block E shared migration framework and migration state.
2. Block E PostgreSQL migration dry-run.
3. Block E SQLite migration/rebuild dry-run.
4. Block E backend-specific migration validation.
5. Block E swap/rebuild only while runtime writes/workers are stopped.

### Wave 4 — Runtime write/read paths
Can partly parallelize after schema target is stable, but not during Block E swap/rebuild:
- Block F file CRUD/indexing/chunks.
- Block G vector/search.
- Block H cleanup/trash.
- Block I MCP API schemas.

### Wave 5 — Full verification
Run Step 18 end-to-end on both backends. Do not mark done until MCP runtime verification passes on both supported DBs.

## Files that must not be edited concurrently

```text
code_analysis/core/database_driver_pkg/drivers/base.py
code_analysis/core/database_driver_pkg/drivers/postgres_operations.py
code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py
code_analysis/core/database/schema_definition_tables_core.py
code_analysis/core/database/schema_definition_tables_mid.py
code_analysis/core/database/schema_definition_tables_rest.py
code_analysis/core/database/schema_definition_indexes.py
code_analysis/core/database/schema_sync_sql.py
code_analysis/core/database/schema_sync_sql_postgres.py
code_analysis/core/database/schema_creation_migrate.py
code_analysis/core/database/files/crud.py
code_analysis/core/database/files/update.py
code_analysis/core/docstring_chunker_pkg/docstring_chunker.py
code_analysis/core/database/code_chunk_sql.py
code_analysis/core/vectorization_worker_pkg/batch_processor.py
code_analysis/core/database/migrations/*
```

## Merge verification after each block
After each block, run the block tests and then the safe MCP checks on the relevant backend(s):

```text
health
get_database_status
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Destructive verification belongs only to Block H and must use test projects.

## Global success criteria
- Universal driver contract supports UUID returned IDs.
- Universal adaptation routes backend-neutral command requests to the selected backend.
- PostgreSQL schema uses native UUID ids for migrated DB identities.
- SQLite schema uses canonical TEXT UUID ids for migrated DB identities.
- Existing PostgreSQL data migrates with full mappings and validation.
- Existing SQLite data migrates/rebuilds with full mappings and validation.
- Migration state and migration command execution are owned by Block E only.
- Runtime write paths do not run during migration swap/rebuild.
- Runtime write paths no longer depend on integer `_lastrowid()` for migrated UUID tables.
- Vector/search still work with UUID DB ids and integer FAISS vector ids.
- MCP schemas and responses are consistent.
- Cleanup/trash lifecycle is safe and backend-aware.
