# Step 06 — `code_analysis/core/database/code_chunk_sql.py`

## Goal
Make `code_chunks` persistence portable and keep all code-chunk upsert SQL in one shared place.

## Why this step exists
Chunking previously failed on PostgreSQL because SQL concerns leaked across layers. The fix introduced a shared `code_chunk_sql.py` module and driver adaptation for `INSERT OR REPLACE INTO code_chunks`. This must be hardened and documented so future changes do not reintroduce SQLite-only SQL in worker/chunker code.

## Current code checked before this step
`code_analysis/core/database/code_chunk_sql.py` currently contains:
- `CODE_CHUNK_UPSERT_SQL`
- `code_chunk_upsert_norm_for_postgres_adapter()`
- `build_code_chunk_upsert_batch(...)`

The module is already the shared source for the portable code-chunk upsert statement.

## File to inspect
`code_analysis/core/database/code_chunk_sql.py`

## Related files
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- `code_analysis/core/database_client/client_operations.py`
- `code_analysis/core/database/base.py`
- `code_analysis/core/database/chunks.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `tests/test_postgres_dml_adapt.py`
- `tests/test_docstring_chunker_batch_persist.py`

## Required checks
1. Confirm there is exactly one portable SQL source for code chunk upsert.
2. Confirm `CODE_CHUNK_UPSERT_SQL` remains SQLite-compatible portable source text.
3. Confirm PostgreSQL conversion happens in driver/adaptation layer, not in worker/chunker code.
4. Confirm the conflict key is `chunk_uuid`.
5. Confirm parameter order is documented and stable.
6. Confirm batch helper returns operations suitable for `execute_batch`.

## Required hardening
Make parameter order explicit. Add constants if they do not already exist:

```python
CODE_CHUNK_UPSERT_PARAM_COUNT = 18
CODE_CHUNK_UPSERT_PARAM_ORDER = (
    "file_id",
    "project_id",
    "chunk_uuid",
    "chunk_type",
    "chunk_text",
    "chunk_ordinal",
    "vector_id",
    "embedding_model",
    "bm25_score",
    "embedding_vector",
    "token_count",
    "class_id",
    "function_id",
    "method_id",
    "line",
    "ast_node_type",
    "source_type",
    "binding_level",
)
```

Then make `build_code_chunk_upsert_batch` validate tuple length and raise a clear error if a row has the wrong length.

## Additional required changes only if checks fail
1. Add docstring explaining layer ownership:
   - portable SQL here;
   - PostgreSQL adaptation in `postgres_run.py`;
   - callers pass params only.
2. Ensure helper names are unambiguous:
   - `build_code_chunk_upsert_batch`
   - `code_chunk_upsert_norm_for_postgres_adapter`

## Must not do
- Do not duplicate code_chunks SQL in `DocstringChunker`.
- Do not put PostgreSQL `ON CONFLICT` SQL in vectorization worker code.
- Do not change `chunk_uuid` generation in this step.
- Do not change schema in this step.

## Tests
Run/update:

```text
python -m pytest tests/test_postgres_dml_adapt.py tests/test_docstring_chunker_batch_persist.py -v
```

Required assertions:
1. SQLite source still contains `INSERT OR REPLACE INTO code_chunks`.
2. PostgreSQL adaptation produces `ON CONFLICT (chunk_uuid) DO UPDATE`.
3. Batch helper creates the expected number of operations.
4. Parameter order matches `DocstringChunker` rows.
5. Wrong-length param rows fail with a clear error.

## Runtime verification
After restart:

```text
get_database_status
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- `chunk_count` grows;
- no SQL syntax errors around code_chunks upsert;
- vectorized chunks continue increasing.

## References
- PostgreSQL adapter step: `08-code_analysis_core_database_driver_pkg_drivers_postgres_run.md`
- Chunker step: `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`
