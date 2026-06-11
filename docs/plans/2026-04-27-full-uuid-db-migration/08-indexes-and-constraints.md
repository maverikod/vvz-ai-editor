# Step 08 — Indexes, unique constraints, and virtual tables

## Goal
Update indexes and uniqueness constraints after integer identity columns become UUID columns, without changing business semantics.

## Current code checked
`schema_definition_indexes.py` currently defines indexes over identity columns and partial predicates. Important examples:

```text
idx_files_project: files(project_id)
idx_classes_file: classes(file_id)
idx_methods_class: methods(class_id)
idx_functions_file: functions(file_id)
idx_entity_cross_ref_*: entity_cross_ref caller/callee ids
idx_code_content_entity: code_content(entity_type, entity_id)
idx_vector_index_entity: vector_index(entity_type, entity_id)
idx_code_chunks_file: code_chunks(file_id)
idx_code_chunks_not_vectorized: code_chunks(project_id, id) WHERE vector_id IS NULL
idx_duplicate_occurrences_file: duplicate_occurrences(file_id)
idx_file_tree_snapshots_file_id: file_tree_snapshots(file_id)
```

`get_schema_virtual_tables()` defines SQLite FTS5 `code_content_fts`. PostgreSQL FTS is not equivalent and must not be treated as normal index migration.

## Files to edit
- `code_analysis/core/database/schema_definition_indexes.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- PostgreSQL index/DDL tests

## Required changes
1. Keep index names stable where possible.
2. Update all indexes that include migrated ID columns so they target UUID columns with the same names.
3. Review partial indexes using SQLite boolean syntax:
   - `deleted = 1`
   - `(deleted = 0 OR deleted IS NULL)`
   - `vector_id IS NULL`
4. In PostgreSQL DDL, boolean partial indexes must use PostgreSQL-compatible predicates, for example `deleted IS TRUE` and `(deleted IS FALSE OR deleted IS NULL)`.
5. Decide whether `idx_code_chunks_not_vectorized` should remain `(project_id, id)` after `id` becomes UUID. If chronological batching is needed, prefer `(project_id, created_at)` or `(project_id, created_at, id)`.
6. Preserve unique constraints from table definitions.

## PostgreSQL-first virtual table policy
Do not port SQLite FTS5 by rewriting UUID ids into `rowid`. PostgreSQL target needs a separate FTS design if `code_content_fts` is still required.

Required decision:

```text
Option A: PostgreSQL uses native tsvector/search columns or materialized index table.
Option B: FTS feature is disabled in PostgreSQL until separately implemented.
Option C: code_content_fts remains SQLite-only and all PostgreSQL cleanup/search code bypasses it.
```

Do not let UUID migration depend on SQLite FTS rowids.

## Layering requirements
- Index definitions remain backend-neutral where possible.
- PostgreSQL predicate translation belongs in PostgreSQL schema sync, not command code.
- SQLite FTS handling belongs to SQLite branch only.

## Must not do
- Do not use paths as index substitutes for UUID identity.
- Do not rely on UUID ordering as processing order.
- Do not keep SQLite-only partial-index predicates in PostgreSQL DDL.
- Do not migrate FTS by pretending PostgreSQL has `rowid`.

## Tests required
1. PostgreSQL DDL/index generation test for boolean partial indexes.
2. Index coverage test: every UUID FK has a supporting index where read/delete paths need it.
3. Non-vectorized chunk index test verifies intended ordering after UUID id.
4. FTS policy test: PostgreSQL migration does not create SQLite FTS5 table or `rowid` dependency.

## Verification
No live DB migration in this step. Verify generated PostgreSQL DDL and index metadata only.

## References
- `05-schema-core-files-and-entities.md`
- `06-schema-mid-ast-cst-chunks-vector-index.md`
- `07-schema-rest-duplicates-analysis-snapshots.md`
- `17-cleanup-trash-repair-commands.md`
