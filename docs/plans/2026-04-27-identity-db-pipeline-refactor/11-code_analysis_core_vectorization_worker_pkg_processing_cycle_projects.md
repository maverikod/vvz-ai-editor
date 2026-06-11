# Step 11 — `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`

## Goal
Make the project-level vectorization cycle explicit, resilient, fair across projects, and easy to debug.

## Why this step exists
A PostgreSQL error in project-cycle Step 0 previously aborted per-project processing before Step 1 chunking could run. A weak model must be able to see the exact stages and failure boundaries.

## Current runtime context checked before this step
Chunking/vectorization are now running, but status still needs careful interpretation:

```text
code_analysis: 206 chunks, 206 vectorized
mcp_proxy_adapter: 628 chunks, 626 vectorized
vast_srv: 307 chunks, 304 vectorized
```

Work can progress at different speeds per project. This is acceptable only if project ordering/fairness is intentional and no project is starved.

## File to inspect
`code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`

## Related files
- `code_analysis/core/vectorization_worker_pkg/batch_processor.py`
- `code_analysis/core/vectorization_worker_pkg/chunking.py`
- `code_analysis/core/vectorization_worker_pkg/processing_cycle.py`
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- `code_analysis/core/project_ignore_policy.py`

## Required code search before edits
Use MCP source search/read tools before editing:

```text
fulltext_search(query="process_projects_in_cycle Step 0 Step 1 request_chunking project_id")
fulltext_search(query="needs_chunking code_chunks processing_cycle_projects")
file_structure(file_path="code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py")
read_project_text_file(file_path="code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py", ...)
```

If exact fulltext search returns no results, read the candidate file directly.

## Required checks
1. Find the per-project processing loop.
2. Identify all stages in order:
   - project selection;
   - project-cycle Step 0: process existing chunks missing embedding params;
   - project-cycle Step 1: request chunking for files;
   - embedding/vectorization work;
   - FAISS rebuild/update.
3. Confirm Step 0 no-work result is not treated as a failure.
4. Confirm exceptions include project_id and stage name.
5. Confirm Step 1 candidate query includes only active files and does not include ignored non-allowlisted paths.
6. Confirm chunking selection does not use path-only global identity.
7. Confirm project ordering/fairness: one project must not starve others.
8. Confirm `needing_chunking` decreases according to the same semantics as `chunked_files`, or explicitly document why it is non-additive.

## Required changes
Only if checks fail:
1. Add stage-specific log messages such as:
   - `[PROJECT_CYCLE STEP 0] existing chunks embedding params`
   - `[PROJECT_CYCLE STEP 1] docstring chunking candidates`
   - `[PROJECT_CYCLE STEP 2] embedding/vectorization`
2. Wrap stage errors with clear context but do not silently swallow them.
3. Ensure one failing project does not prevent other projects from being processed.
4. Add counters: candidates selected, files chunked, chunks created, chunks vectorized.
5. Add fairness guard or at least metrics if one project repeatedly consumes the entire batch.

## Must not do
- Do not create chunks in vectorization code directly if the chunker abstraction exists.
- Do not duplicate ignore policy logic; call shared helpers.
- Do not use SQLite-only SQL.
- Do not infer project ownership by path.
- Do not fix `get_database_status` counter semantics here; see Step 14.

## Tests
Create/update tests that simulate:
1. Step 0 empty result → Step 1 still runs.
2. Step 0 SQL/database error → logged with stage name and project_id.
3. Step 1 creates chunks for indexed files with docstrings.
4. One project failure does not block a second project.
5. Project ordering does not permanently starve projects later in the list.

Suggested test files:
- `tests/test_vectorization_chunking_without_svo.py`
- new `tests/test_vectorization_project_cycle_stages.py`

## Runtime verification
After restart:

```text
view_worker_logs(worker_type="vectorization", tail=300)
get_database_status
```

Expected:
- stage logs show project-cycle Step 1 runs;
- `chunk_count` grows or remains stable only when candidates are exhausted;
- `vectorized_chunks` grows or remains stable only when no vectorization candidates remain;
- failures identify exact stage and project_id;
- all active projects eventually receive chunking/vectorization work when they have eligible files.

## References
- Batch processor step: `10-code_analysis_core_vectorization_worker_pkg_batch_processor.md`
- Chunking step: `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`
- Status counter semantics: `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`
