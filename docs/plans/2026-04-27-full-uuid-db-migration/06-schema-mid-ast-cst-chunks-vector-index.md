# Step 06 — Mid schema: imports, issues, usages, code_content, AST/CST, vector_index, code_chunks

## Goal
Convert mid-layer identity and reference columns from integer IDs to PostgreSQL-first UUID IDs, with special care for polymorphic references and vector identifiers.

## Current code checked
`schema_definition_tables_mid.py` currently defines integer identity/reference columns:

```text
imports.id INTEGER PK
imports.file_id INTEGER -> files.id

issues.id INTEGER PK
issues.file_id INTEGER -> files.id
issues.class_id INTEGER -> classes.id
issues.function_id INTEGER -> functions.id
issues.method_id INTEGER -> methods.id

usages.id INTEGER PK
usages.file_id INTEGER -> files.id

code_content.id INTEGER PK
code_content.file_id INTEGER -> files.id
code_content.entity_id INTEGER polymorphic, no FK

ast_trees.id INTEGER PK
ast_trees.file_id INTEGER -> files.id

cst_trees.id INTEGER PK
cst_trees.file_id INTEGER -> files.id

vector_index.id INTEGER PK
vector_index.entity_id INTEGER polymorphic, no FK
vector_index.vector_id INTEGER FAISS id, not DB identity

code_chunks.id INTEGER PK
code_chunks.file_id INTEGER -> files.id
code_chunks.class_id INTEGER -> classes.id
code_chunks.function_id INTEGER -> functions.id
code_chunks.method_id INTEGER -> methods.id
code_chunks.vector_id INTEGER FAISS id, not DB identity
code_chunks.chunk_uuid TEXT UNIQUE
```

## Prerequisites
Complete first:
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`

## Files to edit in this step
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py` only if logical UUID type mapping is missing
- `code_analysis/core/database/schema_definition_indexes.py` only if schema tests require immediate index metadata alignment; main index work is Step 08
- tests for mid schema

## Target schema
PostgreSQL-first target:

```text
imports.id UUID PK
imports.file_id UUID FK -> files.id

issues.id UUID PK
issues.file_id UUID nullable FK -> files.id
issues.class_id UUID nullable FK -> classes.id
issues.function_id UUID nullable FK -> functions.id
issues.method_id UUID nullable FK -> methods.id

usages.id UUID PK
usages.file_id UUID FK -> files.id

code_content.id UUID PK
code_content.file_id UUID FK -> files.id
code_content.entity_id UUID nullable polymorphic reference, if Option A is chosen

ast_trees.id UUID PK
ast_trees.file_id UUID FK -> files.id

cst_trees.id UUID PK
cst_trees.file_id UUID FK -> files.id

vector_index.id UUID PK
vector_index.entity_id UUID polymorphic reference, if Option A is chosen
vector_index.vector_id INTEGER unchanged

code_chunks.id UUID PK
code_chunks.file_id UUID FK -> files.id
code_chunks.class_id UUID nullable FK -> classes.id
code_chunks.function_id UUID nullable FK -> functions.id
code_chunks.method_id UUID nullable FK -> methods.id
code_chunks.vector_id INTEGER unchanged
code_chunks.chunk_uuid TEXT/UUID-string UNIQUE unchanged
```

## Critical design issue: polymorphic IDs
`vector_index.entity_id` and `code_content.entity_id` are polymorphic. They cannot be enforced by a simple FK because `entity_type` determines the target table.

Required decision before implementation:

```text
Option A: Keep entity_type + entity_id UUID polymorphic fields.
Option B: Replace with nullable typed columns such as file_id/class_id/function_id/method_id.
Option C: Add a unified entities table with UUID id and type, then reference entities.id.
```

Recommended first migration path:
- Use Option A only if existing code can be updated with minimal risk.
- Do not invent a unified `entities` table inside this step unless explicitly approved, because that is a larger model change.

## Required code changes
1. Change PK columns from INTEGER autoincrement to UUID/logical UUID.
2. Change all direct FK columns to UUID.
3. Leave `vector_id` as INTEGER because it is FAISS/vector-storage id, not database row identity.
4. For polymorphic fields, implement only the chosen design and document it in this file or a linked design doc.
5. Preserve existing uniqueness:
   - `ast_trees UNIQUE(file_id, ast_hash)`
   - `cst_trees UNIQUE(file_id, cst_hash)`
   - `vector_index UNIQUE(project_id, entity_type, entity_id)` or replacement chosen in Step 15
   - `code_chunks UNIQUE(chunk_uuid)`
6. Ensure PostgreSQL DDL emits UUID for migrated IDs.

## Layering requirements
- Schema definitions express logical UUID fields.
- PostgreSQL-specific UUID DDL belongs to PostgreSQL schema sync/migration layer.
- Chunk persistence changes belong to Step 14.
- Vector/FAISS behavior belongs to Step 15.

## Must not do
- Do not drop `chunk_uuid`.
- Do not convert `vector_id` to UUID.
- Do not make `vector_index` point to file paths.
- Do not store integer IDs inside UUID-typed fields by casting to text.
- Do not change FAISS files here.
- Do not put PostgreSQL migration SQL in generic schema definitions.

## Tests required
1. Schema definition test for all mid-layer PK/FK columns.
2. PostgreSQL DDL generation test for UUID columns.
3. Polymorphic reference test for `vector_index.entity_id` / `code_content.entity_id` based on chosen design.
4. `vector_id` remains integer.
5. `code_chunks.chunk_uuid` remains unique.
6. `code_chunks.file_id` and optional entity refs use UUID types.

## Verification
No live DB migration in this step. Verify generated PostgreSQL DDL and schema metadata only.

## References
- `01-current-schema-inventory.md`
- `05-schema-core-files-and-entities.md`
- `08-indexes-and-constraints.md`
- `14-docstring-chunks-and-chunk-uuid.md`
- `15-vector-index-and-faiss-mapping.md`
