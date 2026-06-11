# Full UUID database migration plan

## Purpose
This directory contains a step-by-step plan for replacing remaining integer database identifiers with UUID4 identifiers in `code-analysis-server`.

Each file is one isolated step. Every step is written for a weak model: exact files, exact risks, expected tests, and runtime verification are included.

## Current verified runtime baseline
MCP `get_database_status` after restart showed:

```text
projects: 3
active files: 2058
indexed: 2058 / 2058 = 100%
needing_indexing: 0
chunks total: 3082
vectorized chunks: 3044 / 3082 = 98.77%
database_driver: postgres
```

The existing pipeline is working. UUID migration must not break:

```text
watcher -> indexing -> chunking -> vectorization -> search/FAISS
```

## Current driver-layer facts verified from code
Files read during driver analysis:

```text
code_analysis/core/database_driver_pkg/drivers/base.py
code_analysis/core/database_driver_pkg/drivers/postgres.py
code_analysis/core/database_driver_pkg/drivers/postgres_operations.py
code_analysis/core/database_driver_pkg/drivers/postgres_schema.py
code_analysis/core/database_driver_pkg/drivers/postgres_tables.py
code_analysis/core/database_driver_pkg/drivers/sqlite.py
code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py
code_analysis/core/database_driver_pkg/drivers/sqlite_schema.py
code_analysis/core/database_driver_pkg/drivers/sqlite_tables.py
code_analysis/core/database/schema_sync_sql.py
code_analysis/core/database/schema_sync_sql_postgres.py
code_analysis/core/database/sqlite_to_postgres.py
```

Important verified blockers:

```text
BaseDatabaseDriver.insert(...) -> int and docstring says lastrowid.
SQLiteDriver.insert(...) -> int and SQLiteOperations.insert returns cursor.lastrowid.
PostgreSQLDriver.insert(...) -> int and PostgreSQLOperations.insert returns int only; if RETURNING id is not int, it returns 0.
```

Therefore UUID migration must change driver insert contracts before UUID PK DDL is used.

## Target conceptual structure

```text
watch_dirs
  id UUID4 primary key

projects
  id UUID4 primary key
  watch_dir_id UUID4 foreign key -> watch_dirs.id

files
  id UUID4 primary key
  project_id UUID4 foreign key -> projects.id
  watch_dir_id UUID4 optional foreign key -> watch_dirs.id
  path / relative_path used for filesystem reconciliation only

code_chunks
  id UUID4 primary key
  file_id UUID4 foreign key -> files.id
  project_id UUID4 optional denormalized foreign key -> projects.id
  chunk_uuid UUID/TEXT stable chunk business key
```

## Layering rule
PostgreSQL is the target backend. SQLite is an optional compatibility branch and must not weaken the PostgreSQL design.

```text
Universal layer:
  logical schema contract, logical UUID type, driver API shape.
  No backend-specific DDL.

PostgreSQL-specific branch:
  primary target;
  PostgreSQL UUID DDL, PostgreSQL migrations, PostgreSQL constraints/indexes/defaults.

SQLite-specific branch:
  optional compatibility;
  SQLite UUID-as-TEXT DDL, SQLite migration/rebuild, SQLite FTS/rowid handling if supported.
```

## Step order
1. `01-current-schema-inventory.md`
2. `02-uuid-generation-and-type-policy.md`
3. `03-driver-layer-boundaries.md`
4. `04-driver-insert-return-contract.md`
5. `05-schema-core-files-and-entities.md`
6. `06-schema-mid-ast-cst-chunks-vector-index.md`
7. `07-schema-rest-duplicates-analysis-snapshots.md`
8. `08-indexes-and-constraints.md`
9. `09-migration-framework-and-id-map.md`
10. `10-data-migration-postgres-driver-branch.md`
11. `11-data-migration-sqlite-driver-branch.md`
12. `12-file-crud-and-path-identity.md`
13. `13-indexing-ast-cst-entity-writes.md`
14. `14-docstring-chunks-and-chunk-uuid.md`
15. `15-vector-index-and-faiss-mapping.md`
16. `16-mcp-api-compatibility.md`
17. `17-cleanup-trash-repair-commands.md`
18. `18-test-matrix-and-runtime-verification.md`
19. `19-parallelization-map.md`

## Global rules
- Do not edit `.venv`, `site-packages`, installed packages, `mcp-proxy-adapter`, or `queuemgr`.
- Do not change live production data without dry-run, backup, and explicit migration command.
- Do not mix UUID schema migration with unrelated watcher/chunking/vectorization fixes.
- Do not use paths as business identifiers.
- Do not make chunks infer file/project ownership from paths.
- PostgreSQL behavior is primary; SQLite behavior is optional and implemented in its own branch.
- Queue job `completed/progress=100` is not success unless `result.command.result.success` is true.

## Definition of done
- Universal driver contract no longer assumes inserted IDs are integers.
- PostgreSQL schema is created with UUID PK/FK columns for all targeted identity tables.
- Existing PostgreSQL DB can be migrated idempotently with integer-to-UUID mapping preserved.
- SQLite branch is either supported, rebuild-only, or explicitly refused with a clear error.
- `watch_dirs -> projects -> files -> code_chunks` ownership is enforced by UUID FKs.
- AST/CST/entities/chunks/duplicates/snapshots/comprehensive analysis still resolve correctly.
- MCP commands remain backward-compatible or provide explicit breaking-change migration notes.
- Runtime verification shows indexing, chunking, vectorization, and search still work after migration.

## Implementation closure — 2026-04-28

**Engineering status:** **closed.** The repository implements this plan end-to-end: universal driver `DbIdentity` / insert `RETURNING` behavior, logical UUID schema (core / mid / rest + indexes), migration framework (step 09), PostgreSQL phases 3–6 and SQLite phases 3–6 (swap opt-in), runtime CRUD/indexing/chunks/cleanup (steps 12–17), vector/FAISS boundary (15), MCP field/schema updates (16), MCP admin command **`run_uuid_identity_migration`**, migration helpers compatible with **`DatabaseClient.execute`** (no `_fetchone` / `_execute` on client), and PostgreSQL **`run_execute`** no longer appends **`RETURNING id`** for `INSERT` targets missing from `schema_tables` (e.g. `uuid_migration_*`).

**Automated verification:** Targeted pytest for schema, migration modules, vectorization, and the migration MCP command passes in development. Re-run the step **18** matrix after **data** migration (phase 2+ and any non–dry-run phases) on a **database clone** that matches production shape.

**Operator-only tail (per-instance, not implied by “closed” above):** backup; maintenance window; `run_uuid_identity_migration` sequence (`preflight` → `phase2_mappings` → `phases_345` dry rehearsal → apply → `phase6_swap` only with `i_confirm_maintenance_swap: true`); restart daemon (**`casmgr restart`** with active `.venv` per project rules); confirm **`health`**, **`get_database_status`**, worker logs (step 18); retain or drop `*_int_backup_*` per policy.

**Note:** Sections *Current verified runtime baseline* and *Current driver-layer facts* describe the **plan authoring** snapshot and historical blockers; implementation supersedes those driver constraints.
