# Step 10 — `code_analysis/core/vectorization_worker_pkg/batch_processor.py`

## Goal
Keep vectorization batch SQL portable and ensure PostgreSQL does not abort project processing before chunking starts.

## Why this step exists
Runtime proved that `HAVING cnt > 0` in `process_chunks_missing_embedding_params` fails on PostgreSQL with `column "cnt" does not exist`. That exception happened in project-cycle Step 0 and prevented project-cycle Step 1 chunking from running.

## Current code checked before this step
`code_analysis/core/vectorization_worker_pkg/batch_processor.py` currently uses:

```sql
HAVING COUNT(cc.id) > 0
```

This is the required portable form.

Important naming note:
Inside `process_chunks_missing_embedding_params`, local comments may say "Step 1" for internal substeps. Do not confuse those internal substeps with the higher-level project-cycle Step 0 / Step 1 in `processing_cycle_projects.py`.

## File to inspect
`code_analysis/core/vectorization_worker_pkg/batch_processor.py`

## Related files
- `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `tests/test_postgres_dml_adapt.py`

## Required code search before edits
Use MCP source search/read tools before editing:

```text
fulltext_search(query="HAVING cnt HAVING COUNT cc.id process_chunks_missing_embedding_params")
file_structure(file_path="code_analysis/core/vectorization_worker_pkg/batch_processor.py")
read_project_text_file(file_path="code_analysis/core/vectorization_worker_pkg/batch_processor.py", ...)
```

If exact fulltext search returns no results, read the candidate file directly.

## Required checks
1. Find `process_chunks_missing_embedding_params`.
2. Confirm the query uses:

```sql
HAVING COUNT(cc.id) > 0
```

not:

```sql
HAVING cnt > 0
```

3. Confirm this function does not raise on empty result sets.
4. Confirm project processing continues to project-cycle Step 1 chunking when Step 0 has no work.
5. Confirm errors in Step 0 are logged with enough detail and do not hide the SQL/stage context entirely.
6. Decide whether local substep comments should be renamed to avoid Step 0 / Step 1 confusion.

## Required changes
Only if checks fail:
1. Replace `HAVING cnt > 0` with `HAVING COUNT(cc.id) > 0`.
2. Add a regression test that inspects the SQL or executes it against PostgreSQL-compatible path.
3. Ensure empty result is normal and not an error.
4. Align log/comment naming with project-cycle stages if ambiguity causes test/debug confusion.

## Must not do
- Do not rely on PostgreSQL-only syntax here.
- Do not move code_chunks upsert logic into this file.
- Do not make vectorizer create chunks directly; chunking belongs to the project-cycle Step 1 chunking path.

## Tests
Run:

```text
python -m pytest tests/test_postgres_dml_adapt.py -v
```

Required assertions:
1. `HAVING cnt > 0` does not appear.
2. `HAVING COUNT(cc.id) > 0` appears.
3. The vectorization cycle can reach chunking on PostgreSQL.
4. Empty Step 0 result does not count as a project failure.

## Runtime verification
After restart:

```text
view_worker_logs(worker_type="vectorization", search_pattern="column \"cnt\" does not exist", tail=200)
view_worker_logs(worker_type="vectorization", search_pattern="Step 1", tail=200)
get_database_status
```

Expected:
- no `column "cnt" does not exist`;
- project-cycle Step 1 chunking appears;
- `chunk_count` increases or stays stable only when no candidates remain.

## References
- PostgreSQL driver step: `08-code_analysis_core_database_driver_pkg_drivers_postgres_run.md`
- Chunker step: `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`
- Project cycle step: `11-code_analysis_core_vectorization_worker_pkg_processing_cycle_projects.md`
