# Step 10 — PostgreSQL data migration driver branch

## Goal
Implement the real PostgreSQL data migration from integer identity columns to UUID identity columns using the mapping framework from Step 09.

## Backend policy
PostgreSQL is the target backend. This step is PostgreSQL-specific and may use PostgreSQL transactions, temporary tables, UUID column types, `ALTER TABLE ... RENAME`, and PostgreSQL validation queries.

SQLite is handled separately in Step 11 and must not constrain this step.

## Prerequisites
Complete first:
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `06-schema-mid-ast-cst-chunks-vector-index.md`
- `07-schema-rest-duplicates-analysis-snapshots.md`
- `08-indexes-and-constraints.md`
- `09-migration-framework-and-id-map.md`

## Files to inspect/edit
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/database/schema_creation_migrate.py`
- new PostgreSQL migration module, for example:
  - `code_analysis/core/database/migrations/uuid_identity_postgres.py`
- database driver transaction helpers
- PostgreSQL migration tests

## Required preconditions before running on real DB
1. Server is in maintenance mode or mutation workers are stopped.
2. Queue has no active indexing/vectorization/file_watcher mutation jobs.
3. A database backup/snapshot exists.
4. Preflight invariants from Step 09 pass.
5. Mapping tables exist and are populated idempotently.
6. Driver insert contract can return UUID strings and does not return `0` for UUID IDs.

## Required migration order
Use dependency order. Do not migrate child tables before parent mappings exist.

### Group 1 — root tables already UUID-like
Validate and cast if using PostgreSQL-native UUID:

```text
watch_dirs.id
watch_dir_paths.watch_dir_id
projects.id
projects.watch_dir_id
project_activity_locks.project_id
```

Do not regenerate these IDs.

### Group 2 — files
Migrate:

```text
files.id INTEGER -> UUID
files.project_id TEXT -> UUID FK projects(id)
files.watch_dir_id TEXT -> UUID FK watch_dirs(id)
```

Keep:

```text
UNIQUE(project_id, path)
path / relative_path semantics unchanged
```

### Group 3 — source entities
Migrate:

```text
classes.id, classes.file_id
functions.id, functions.file_id
methods.id, methods.class_id
```

### Group 4 — entity references
Migrate:

```text
entity_cross_ref.id
entity_cross_ref.file_id
entity_cross_ref.caller_class_id / callee_class_id
entity_cross_ref.caller_method_id / callee_method_id
entity_cross_ref.caller_function_id / callee_function_id
```

### Group 5 — analysis/indexing data
Migrate:

```text
imports.id, imports.file_id
issues.id, issues.file_id, class_id, function_id, method_id
usages.id, usages.file_id
code_content.id, code_content.file_id, entity_id according to Step 06 decision
ast_trees.id, ast_trees.file_id
cst_trees.id, cst_trees.file_id
```

### Group 6 — chunks/vectors
Migrate:

```text
code_chunks.id
code_chunks.file_id
code_chunks.class_id / function_id / method_id
vector_index.id
vector_index.entity_id according to Step 06 / Step 15 decision
```

`vector_id` is not database identity. Do not convert it to UUID.

### Group 7 — duplicates / snapshots / comprehensive analysis
Migrate:

```text
code_duplicates.id
duplicate_occurrences.id, duplicate_id, file_id
comprehensive_analysis_results.id, file_id
file_tree_snapshots.id, file_id
file_tree_snapshot_roots.snapshot_id
file_tree_snapshot_nodes.id, snapshot_id
```

## Required validation queries
After copying to new tables, run row-count and FK checks for every migrated table. At minimum:

```sql
SELECT COUNT(*) FROM code_chunks cc LEFT JOIN files f ON f.id = cc.file_id WHERE f.id IS NULL;
```

```sql
SELECT COUNT(*) FROM code_chunks cc JOIN files f ON f.id = cc.file_id WHERE cc.project_id != f.project_id;
```

```sql
SELECT COUNT(*) FROM ast_trees a LEFT JOIN files f ON f.id = a.file_id WHERE f.id IS NULL;
```

Polymorphic `vector_index.entity_id` / `code_content.entity_id` validation depends on the decision in Step 06.

## Required transaction / rollback behavior
Preferred:
1. Create new tables and copy data in transaction-safe phases.
2. Validate before swap.
3. Swap table names in a transaction if feasible.
4. Keep old tables as `*_int_backup_<migration_id>` until runtime verification passes.

If full transaction is too large, record migration state:

```text
uuid_identity_migration_state
  migration_id UUID
  phase TEXT
  started_at
  completed_at
  success BOOLEAN
  details JSON/TEXT
```

## Layering requirements
- Migration module owns PostgreSQL DDL/data copy/swap SQL.
- Command layer only invokes migration command and reports result.
- Generic CRUD/indexing code must not contain migration SQL.
- PostgreSQL-specific SQL stays in PostgreSQL migration branch.

## Must not do
- Do not run automatically at normal server startup.
- Do not drop old integer tables immediately.
- Do not rewrite by matching paths.
- Do not treat SQLite behavior as equivalent here.
- Do not rebuild FAISS blindly before Step 15 defines mapping behavior.

## Tests required
1. PostgreSQL integration migration test on a small DB with all relation types.
2. Idempotent retry test for mapping/copy phases.
3. Failure-in-middle test: rerun resumes or clearly refuses with state explanation.
4. Post-migration FK validation test.
5. Runtime smoke test after migration using MCP commands.

## Runtime verification
After migration and restart:

```text
health
get_database_status
list_project_files(project_id=<project>)
get_ast(project_id=<project>, file_path=<path>)
semantic_search(project_id=<project>, query=<query>)
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- all migrated DB identity IDs returned by commands are UUID strings;
- no FK errors;
- chunks and vectors are still usable or intentionally rebuilt per Step 15.

## References
- `09-migration-framework-and-id-map.md`
- `15-vector-index-and-faiss-mapping.md`
- `18-test-matrix-and-runtime-verification.md`
