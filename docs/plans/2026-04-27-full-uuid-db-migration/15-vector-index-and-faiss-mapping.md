# Step 15 — Vector index and FAISS mapping after UUID migration

## Goal
Update vectorization storage and FAISS mapping so UUID database identities do not break chunk-to-vector and entity-to-vector resolution.

## Current code checked
`code_analysis/core/vectorization_worker_pkg/batch_processor.py` currently treats DB chunk/file IDs as integers in places such as:

```text
file_table: List[Tuple[int, str, int]]
int(r["file_id"])
updates_to_apply: List[Tuple[int, int, str]]
UPDATE code_chunks SET vector_id = ?, embedding_model = ? WHERE id = ?
ORDER BY cc.id
```

Important distinction:

```text
code_chunks.id          -> database row identity, target UUID
code_chunks.file_id     -> database FK, target UUID
code_chunks.vector_id   -> FAISS vector position/id, remains integer unless FAISS is redesigned
vector_index.id         -> database row identity, target UUID
vector_index.entity_id  -> polymorphic DB identity, target depends on Step 06 decision
vector_index.vector_id  -> FAISS vector position/id, remains integer unless FAISS is redesigned
```

## Prerequisites
Complete first:
- `06-schema-mid-ast-cst-chunks-vector-index.md`
- `13-indexing-ast-cst-entity-writes.md`
- `14-docstring-chunks-and-chunk-uuid.md`

## Files to inspect/edit
- `code_analysis/core/vectorization_worker_pkg/batch_processor.py`
- `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`
- `code_analysis/core/vectorization_worker_pkg/chunking.py`
- FAISS manager modules
- semantic search modules
- `code_analysis/core/database/schema_definition_tables_mid.py`
- vectorization/search tests

## Required design decisions
1. `code_chunks.id` becomes UUID.
2. `vector_index.id` becomes UUID.
3. `vector_id` remains integer FAISS id unless a separate FAISS redesign is approved.
4. `vector_index.entity_id` must follow the polymorphic UUID strategy from Step 06.
5. Search result payloads must distinguish:
   - `chunk_id`: UUID database row id;
   - `chunk_uuid`: stable chunk business key;
   - `vector_id`: integer FAISS id.

## Required code changes
1. Replace chunk/file DB id type hints from integer to UUID string.
2. Remove `int(...)` casts for DB IDs after UUID migration.
3. Keep `vector_id` as integer where it represents FAISS position.
4. Update SQL parameter handling for UUID `cc.id` and UUID `cc.file_id`.
5. Generate UUID `vector_index.id` explicitly if vector_index rows are inserted and no PostgreSQL default is used.
6. Update semantic search result mapping to use UUID chunk IDs and UUID file IDs.
7. Update serialization that assumes DB IDs are integers.

## Important ordering issue
Current code orders chunks by `cc.id` in some places. After UUID migration, UUID ordering is not creation ordering.

Required fix direction:
- Prefer `ORDER BY cc.created_at, cc.id` or another explicit timestamp/ordinal order.
- Update indexes if needed, for example `(project_id, created_at)` for non-vectorized chunks.

## Layering requirements
- Vectorization worker should not know PostgreSQL UUID syntax.
- Universal DB layer should pass UUID strings as params.
- PostgreSQL schema/driver owns UUID column typing.
- FAISS manager owns only vector positions, not database identity.

## Must not do
- Do not store UUID database ids in FAISS `vector_id` fields.
- Do not rely on UUID ordering for processing order.
- Do not use `ORDER BY cc.id` as chronological order after UUID migration unless explicitly acceptable.
- Do not rebuild FAISS silently during migration without an explicit plan.
- Do not change `chunk_uuid` formula here; see Step 14.

## Tests required
1. Vectorization selects chunks with UUID `cc.id` and UUID `cc.file_id` without integer casts.
2. `vector_id` remains integer and is written correctly.
3. Semantic search returns UUID `file_id`, UUID `chunk_id`, string `chunk_uuid`, and integer `vector_id` if present.
4. Processing order does not depend on UUID lexical order.
5. FAISS rebuild after migration either works or is explicitly required before search.
6. Any `int(r["file_id"])` or `int(chunk_id)` conversion is removed or guarded as legacy-only.

## Runtime verification
After migration and restart:

```text
get_database_status
semantic_search(project_id=<project>, query=<query>)
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- vectorization writes integer `vector_id` values to UUID chunk rows;
- semantic search resolves UUID-backed chunks;
- no `int()` conversion errors for UUID ids.

## References
- `06-schema-mid-ast-cst-chunks-vector-index.md`
- `10-data-migration-postgres-driver-branch.md`
- `14-docstring-chunks-and-chunk-uuid.md`
- `16-mcp-api-compatibility.md`
