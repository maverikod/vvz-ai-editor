# Step 09 — `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`

## Goal
Keep chunk extraction focused on docstrings and make persistence use the database abstraction instead of owning SQL details.

## Why this step exists
Runtime chunking was blocked until PostgreSQL-compatible code_chunks upsert was introduced. `DocstringChunker` must not duplicate SQL or know PostgreSQL syntax. It should build chunk parameter rows and pass them to an abstraction.

## Current code checked before this step
`DocstringChunker` currently builds param rows in `_code_chunk_upsert_param_rows_for_docstring_rows(...)` and persists through `_persist_code_chunk_param_rows(...)`.

Important current fact:
`chunk_uuid` is generated from a string that includes integer `file_id`:

```python
uuid_name = (
    f"{file_id}:{it.ast_node_type}:{it.line}:{it.source_type}:"
    f"{chunk_index}:{text_sig}"
)
chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, uuid_name))
```

Do not change this in this step. If the UUID business identity transition later changes file identity, the `chunk_uuid` scheme must be handled in Step 12 as a migration/design decision.

## File to inspect
`code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`

## Related files
- `code_analysis/core/database/code_chunk_sql.py`
- `code_analysis/core/database_client/client_operations.py`
- `code_analysis/core/database/base.py`
- `tests/test_docstring_chunker_batch_persist.py`
- `tests/test_vectorization_chunking_without_svo.py`

## Required code search before edits
Use MCP source search/read tools before editing:

```text
fulltext_search(query="chunk_uuid uuid_name file_id ast_node_type source_type text_sig")
file_structure(file_path="code_analysis/core/docstring_chunker_pkg/docstring_chunker.py")
read_project_text_file(file_path="code_analysis/core/docstring_chunker_pkg/docstring_chunker.py", ...)
```

If exact fulltext search returns no results, read the candidate file directly.

## Required checks
1. Confirm `DocstringChunker` does not define its own `INSERT OR REPLACE INTO code_chunks` SQL string.
2. Confirm it creates stable chunk params including `chunk_uuid`.
3. Confirm `chunk_uuid` generation includes `file_id` and is not based on path alone.
4. Confirm persistence uses `upsert_code_chunks_batch` when available.
5. Confirm fallback uses `build_code_chunk_upsert_batch(...)` from `code_chunk_sql.py`.
6. Confirm no PostgreSQL-specific SQL appears here.

## Required changes
Only if checks fail:
1. Remove duplicated SQL from this file.
2. Add a small helper that converts extracted docstring rows into code chunk param tuples.
3. Use database abstraction first:
   `database.upsert_code_chunks_batch(param_rows)`.
4. Keep execute_batch fallback only through shared `build_code_chunk_upsert_batch`.
5. Add docstrings explaining that this class extracts chunks, not SQL dialects.

## Must not do
- Do not import PostgreSQL driver code here.
- Do not make chunk ownership depend on file path.
- Do not change `chunk_uuid` scheme in this step unless tests are updated and migration impact is documented in Step 12.
- Do not vectorize here; vectorization is a separate stage.

## Tests
Run:

```text
python -m pytest tests/test_docstring_chunker_batch_persist.py tests/test_vectorization_chunking_without_svo.py -v
```

Required assertions:
1. Mock database receives `upsert_code_chunks_batch` calls.
2. Extracted docstrings create code chunk param rows.
3. No raw SQL duplication is required in chunker.
4. A Python file with module/class/function docstrings creates at least one chunk.
5. `chunk_uuid` remains stable for the current integer-file-id scheme.

## Runtime verification
After restart:

```text
get_database_status
view_worker_logs(worker_type="vectorization", tail=200)
```

Expected:
- `chunk_count` grows;
- chunk previews look like docstrings;
- vectorization has chunks to process.

## References
- Shared SQL step: `06-code_analysis_core_database_code_chunk_sql.md`
- Batch processor step: `10-code_analysis_core_vectorization_worker_pkg_batch_processor.md`
- UUID transition decision: `12-uuid_business_identity_transition.md`
