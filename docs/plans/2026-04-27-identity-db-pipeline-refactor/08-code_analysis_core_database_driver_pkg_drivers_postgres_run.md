# Step 08 — `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`

## Goal
Keep PostgreSQL SQL adaptation centralized in the driver layer and prevent SQLite-only SQL from leaking into runtime PostgreSQL execution.

## Why this step exists
Two PostgreSQL issues were found during runtime validation:

1. `HAVING cnt > 0` failed because PostgreSQL does not accept the select alias in `HAVING`.
2. `INSERT OR REPLACE INTO code_chunks` required PostgreSQL adaptation to `ON CONFLICT (chunk_uuid) DO UPDATE`.

The first belongs to worker SQL because `HAVING COUNT(cc.id) > 0` is portable. The second belongs to SQL abstraction / driver adaptation, not worker code.

## Current code checked before this step
`postgres_run.py` currently contains:
- `_adapt_sqlite_dml_for_postgres`
- `_sqlite_qmarks_to_psycopg`
- table-specific norms for `indexing_errors`, `watch_dirs`, `watch_dir_paths`, and `code_chunks`
- `_CODE_CHUNKS_INSERT_OR_REPLACE_NORM = code_chunk_upsert_norm_for_postgres_adapter()`
- code_chunks adaptation to `ON CONFLICT (chunk_uuid) DO UPDATE`

## File to inspect
`code_analysis/core/database_driver_pkg/drivers/postgres_run.py`

## Related files
- `code_analysis/core/database/code_chunk_sql.py`
- `code_analysis/core/vectorization_worker_pkg/batch_processor.py`
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- `code_analysis/core/database/files/crud.py`
- `tests/test_postgres_dml_adapt.py`

## Required checks
1. Find `_adapt_sqlite_dml_for_postgres`.
2. Find `_sqlite_qmarks_to_psycopg` or equivalent placeholder conversion.
3. Confirm adaptation for `code_chunks` upsert is table-specific and based on the shared norm from `code_chunk_sql.py`.
4. Confirm no duplicated hardcoded `code_chunks` norm string exists outside `code_chunk_sql.py`.
5. Confirm `julianday('now')` and similar timestamp conversion works for new code chunk SQL.
6. Confirm unsupported SQLite-only SQL is either adapted intentionally or covered by a failing test before behavior is changed.

## Required caution about unknown SQLite-only SQL
Do not change runtime behavior for unknown SQL in the same patch unless a failing test proves it. First add a diagnostic/test, then decide whether to fail loudly, adapt, or route through backend-specific code.

Important known risk from code check:
`code_analysis/core/database/files/crud.py::clear_file_data` contains SQLite/FTS-specific SQL using `code_content_fts` and `rowid`. This step should add PostgreSQL adaptation tests or a follow-up task for backend-aware cleanup, but must not silently break cleanup behavior.

## Required changes only if checks fail
1. Import the norm helper from `code_chunk_sql.py`.
2. Add/keep adapter case for code_chunks upsert.
3. Add clear comments: generic worker/chunker code must not emit PostgreSQL-specific SQL.
4. Add tests for every table-specific `INSERT OR REPLACE` adaptation.
5. Add or schedule a PostgreSQL cleanup test for `code_content_fts` / `rowid` paths.

## Must not do
- Do not put PostgreSQL `ON CONFLICT` SQL inside `DocstringChunker`.
- Do not modify `mcp-proxy-adapter` or `queuemgr`.
- Do not silently ignore unknown SQLite-only SQL.
- Do not change schema here.
- Do not combine this with file identity changes.

## Tests
Run:

```text
python -m pytest tests/test_postgres_dml_adapt.py -v
```

Required assertions:
1. `INSERT OR REPLACE INTO code_chunks` adapts to valid PostgreSQL.
2. Conflict target is `chunk_uuid`.
3. `HAVING cnt > 0` does not appear in vectorization SQL tests.
4. Placeholder conversion preserves parameter order.
5. A test or explicit pending task covers SQLite FTS cleanup SQL under PostgreSQL.

## Runtime verification
After restart:

```text
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
get_database_status
```

Expected:
- no PostgreSQL syntax errors;
- `chunk_count` and `vectorized_chunks` grow.

## References
- Code chunk SQL step: `06-code_analysis_core_database_code_chunk_sql.md`
- Vectorization SQL step: `10-code_analysis_core_vectorization_worker_pkg_batch_processor.md`
- File cleanup risk: `01-code_analysis_core_database_files_crud.md`
