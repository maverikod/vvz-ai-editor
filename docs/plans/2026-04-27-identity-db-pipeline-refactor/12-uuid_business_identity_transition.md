# Step 12 — UUID business identity transition

## Goal
Prepare a safe transition toward UUID business identifiers without replacing integer foreign keys in one risky migration.

## Why this step exists
Current schema uses UUID-like text IDs for `projects` and `watch_dirs`, but `files.id`, `code_chunks.id`, AST/CST/entity IDs are integer autoincrement. Changing them directly would touch many FK relationships and runtime APIs. This step is design-first and must not be mixed with hotfixes.

## Files to inspect before any implementation
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- all MCP command metadata files that expose `file_id` or `chunk_id`

## Current code checked before this step
`DocstringChunker` currently generates `chunk_uuid` from a string that includes integer `file_id`:

```python
uuid_name = (
    f"{file_id}:{it.ast_node_type}:{it.line}:{it.source_type}:"
    f"{chunk_index}:{text_sig}"
)
chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, uuid_name))
```

Therefore any transition from integer `files.id` to `files.file_uuid` must explicitly decide whether `chunk_uuid` generation remains based on legacy integer `file_id` or gets a versioned UUID-based scheme. Do not change this accidentally.

## Recommended strategy
Do not replace integer PKs immediately.

Preferred staged approach:
1. Keep internal integer PKs and FKs.
2. Add UUID business columns, for example:
   - `files.file_uuid TEXT UNIQUE NOT NULL`
   - optional `code_chunks.row_uuid TEXT UNIQUE NOT NULL` only if `chunk_uuid` is not sufficient.
3. Backfill existing rows with UUID4 values.
4. Expose UUIDs in MCP responses alongside legacy integer IDs.
5. Accept UUIDs in new commands only after backward-compatible readers exist.
6. Consider replacing internal FK columns only in a later major migration.

## Required investigation
1. List every table with `file_id` FK.
2. List every command response that exposes integer `file_id`.
3. List every command parameter that accepts integer `file_id`.
4. Check how `chunk_uuid` is generated and whether it already acts as stable business identity.
5. Check FAISS/vector mappings and whether they store integer DB IDs.
6. Check backup/restore and trash workflows for integer assumptions.
7. Decide and document chunk UUID versioning:
   - keep current `chunk_uuid` formula based on integer `file_id` forever; or
   - introduce a versioned chunk identity formula based on `file_uuid`; or
   - keep `chunk_uuid` stable and add a separate future chunk business UUID.

## Must not do
- Do not convert `files.id` to UUID in the first implementation step.
- Do not break existing MCP clients expecting integer IDs.
- Do not regenerate `chunk_uuid` for existing chunks without a migration plan.
- Do not change live data without dry-run and backup.
- Do not mix UUID work with the `get_database_status` counter fix.

## Proposed tests
1. Migration test: existing DB rows get `file_uuid` backfilled idempotently.
2. New file insert test: `file_uuid` is created automatically.
3. MCP compatibility test: response includes both integer `id` and UUID where applicable.
4. Lookup test: new helper can resolve by `file_uuid` and legacy int id.
5. Rollback test: old commands still work after UUID columns are added.
6. Chunk identity test: current `chunk_uuid` stays stable unless a documented versioned scheme is introduced.

## Runtime verification after future implementation

```text
get_database_status
list_project_files(project_id=<project>)
get_ast(project_id=<project>, file_path=<path>)
semantic_search(project_id=<project>, query=<query>)
```

Expected:
- existing integer-based commands still work;
- UUIDs are present where explicitly added;
- no FK integrity errors;
- existing chunks remain searchable.

## References
- Schema map: `05-code_analysis_core_database_schema_identity.md`
- File identity helper: `03-code_analysis_core_file_identity.md`
- Chunk UUID source: `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`
