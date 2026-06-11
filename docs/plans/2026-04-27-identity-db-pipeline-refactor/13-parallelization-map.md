# Step 13 — Parallelization map

## Goal
Show which refactoring steps can be assigned to different performers in parallel, which steps must be sequential, and which files must not be edited by more than one performer at the same time.

## Rule for all performers
Each performer owns only the files listed in their block. Do not edit `.venv`, `site-packages`, installed packages, `mcp-proxy-adapter`, or `queuemgr`. Do not edit files owned by another block unless the coordinator explicitly moves the file to your block.

## Dependency overview

```text
Phase A — safe independent audits
  02 execute_single destructive path-only cleanup audit
  04 ignore policy audit
  05 schema identity map
  08 postgres adapter audit
  10 batch processor audit
  14 get_database_status counter consistency audit

Phase B — small code hardening
  01 files.crud verification/final polish
  03 file_identity helper
  06 code_chunk_sql hardening
  09 DocstringChunker persistence hardening
  11 vectorization cycle observability
  14 get_database_status predicate alignment

Phase C — design-only migration
  12 UUID business identity transition
```

## Critical serialization rules

### Rule 1 — `files/crud.py` before broad identity refactor
Step 01 must be verified before Step 03 changes callers. The current hotfix is already present, but it must remain the baseline.

### Rule 2 — `code_chunk_sql.py` before chunker/driver changes
Step 06 owns the shared code chunk upsert SQL. Steps 08 and 09 must not duplicate or redefine the same SQL.

### Rule 3 — `project_ignore_policy.py` before watcher/chunking/status selection changes
Step 04 owns ignore/allowlist semantics. Steps 07, 11, and 14 must call shared policy instead of inventing new ignore rules.

### Rule 4 — UUID transition is design-only until hotfixes stabilize
Step 12 must not change schema while Steps 01–11 and Step 14 are active.

### Rule 5 — status semantics depend on lifecycle semantics
Step 14 must coordinate with Step 11. `get_database_status` must not invent lifecycle meanings that contradict vectorization/chunking worker behavior.

## Parallel work blocks

## Block A — File identity / CRUD safety

### Performer A1 owns
- `01-code_analysis_core_database_files_crud.md`
- `03-code_analysis_core_file_identity.md`

### Source files allowed
- `code_analysis/core/database/files/crud.py`
- `code_analysis/core/file_identity.py` if created
- `tests/test_add_file_cross_project_path.py`
- `tests/test_file_identity.py`

### Must coordinate with
- Performer A2 before changing `execute_single.py` behavior.
- Performer C1 before adding schema constraints.

### Deliverable
- No cross-project conflict based on `relative_path`.
- Helper module defines project-local path identity rules.
- Tests prove same relative path in different projects is safe.

## Block B — Comprehensive analysis path lookup

### Performer A2 owns
- `02-code_analysis_commands_comprehensive_analysis_mcp_execute_single.md`

### Source files allowed
- `code_analysis/commands/comprehensive_analysis_mcp/execute_single.py`
- tests for comprehensive analysis single-file execution

### Must coordinate with
- Performer A1 for identity helper usage.

### Deliverable
- Normal comprehensive analysis does not destructively clear another project's file data through path-only lookup.
- Any global `WHERE path = ?` lookup is either project-scoped or explicitly diagnostic-only.

## Block C — Ignore / allowlist policy

### Performer B1 owns
- `04-code_analysis_core_project_ignore_policy.md`
- `07-code_analysis_core_file_watcher_pkg_scanner.md`

### Source files allowed
- `code_analysis/core/project_ignore_policy.py`
- `code_analysis/core/file_watcher_pkg/scanner.py`
- `code_analysis/core/file_watcher_pkg/project_discovery.py` only for read or tiny logging adjustments
- `code_analysis/core/file_watcher_pkg/ignore_pre_scan_purge.py`
- `tests/test_project_ignore_policy.py`
- `tests/test_scanner_with_discovery.py`

### Must coordinate with
- Performer A1 to avoid using ignore policy as identity logic.
- Performer H1 before changing status aggregate filters.

### Deliverable
- `.venv` is ignored by default.
- Configured allowlisted site-packages distributions can still be included.
- Watcher does not descend broadly into `.venv`.

## Block D — Schema identity documentation

### Performer C1 owns
- `05-code_analysis_core_database_schema_identity.md`
- `12-uuid_business_identity_transition.md`
- `schema_identity_map.md`

### Source files allowed
Design/read-only by default:
- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py`
- `code_analysis/core/database/schema_creation_migrate.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- documentation files under this plan directory

### Must coordinate with
- All other performers before proposing schema changes.

### Deliverable
- `schema_identity_map.md` with PK/FK/unique/index map.
- UUID transition proposal that does not replace integer FK internals in the first implementation.

## Block E — code_chunks SQL abstraction and PostgreSQL adapter

### Performer D1 owns
- `06-code_analysis_core_database_code_chunk_sql.md`
- `08-code_analysis_core_database_driver_pkg_drivers_postgres_run.md`

### Source files allowed
- `code_analysis/core/database/code_chunk_sql.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`
- `code_analysis/core/database_client/client_operations.py` only for code chunk upsert adapter calls
- `code_analysis/core/database/base.py` only for `upsert_code_chunks_batch`
- `code_analysis/core/database/chunks.py` only for chunk upsert call path
- `tests/test_postgres_dml_adapt.py`

### Must coordinate with
- Performer D2 before changing `DocstringChunker` persistence.

### Deliverable
- One shared code chunk upsert SQL source.
- PostgreSQL adaptation uses `ON CONFLICT (chunk_uuid)`.
- Worker/chunker code contains no PostgreSQL-specific SQL.

## Block F — Docstring chunker persistence

### Performer D2 owns
- `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`

### Source files allowed
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py`
- `tests/test_docstring_chunker_batch_persist.py`
- `tests/test_vectorization_chunking_without_svo.py`

### Must coordinate with
- Performer D1 for `code_chunk_sql.py` API names and parameter order.
- Performer C1 before any future change to `chunk_uuid` generation.

### Deliverable
- `DocstringChunker` builds param rows and calls `upsert_code_chunks_batch`.
- No duplicated `INSERT OR REPLACE INTO code_chunks` SQL inside the chunker.

## Block G — Vectorization batch / cycle stages

### Performer E1 owns
- `10-code_analysis_core_vectorization_worker_pkg_batch_processor.md`
- `11-code_analysis_core_vectorization_worker_pkg_processing_cycle_projects.md`

### Source files allowed
- `code_analysis/core/vectorization_worker_pkg/batch_processor.py`
- `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`
- `code_analysis/core/vectorization_worker_pkg/chunking.py` only if Step 11 requires candidate selection fix
- `tests/test_vectorization_chunking_without_svo.py`
- new `tests/test_vectorization_project_cycle_stages.py`

### Must coordinate with
- Performer B1 if adding ignore-policy filters to chunking selection.
- Performer D1/D2 if changing code chunk persistence assumptions.
- Performer H1 for status semantics.

### Deliverable
- No `HAVING cnt > 0`.
- Step 0 empty result does not prevent Step 1 chunking.
- Logs show stage-specific progress and failures.
- Project ordering/fairness is tested or documented.

## Block H — Database status consistency

### Performer H1 owns
- `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`

### Source files allowed
- `code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py`
- `tests/test_get_database_status_ops_dialect.py`
- `tests/test_get_database_status_ignored_paths.py`
- new `tests/test_get_database_status_counter_consistency.py`

### Must coordinate with
- Performer B1 for ignore-policy status filters.
- Performer E1 for lifecycle semantics of indexing/chunking/vectorization.
- Performer C1 for schema identity and diagnostic invariant queries.

### Deliverable
- `indexed` and `needing_indexing` use compatible predicates.
- If counters are non-additive, fields and documentation make that explicit.
- Runtime contradiction like `active=2053`, `indexed=2052`, `needing_indexing=15` is eliminated or explained by explicit other-state counters.

## Recommended execution order

### Wave 1 — parallel, low conflict
Can run together:
- Block A / A1: verify Step 01 and draft Step 03 helper.
- Block B / A2: audit and fix destructive `execute_single.py` path-only cleanup.
- Block C / B1: audit ignore policy and scanner.
- Block D / C1: schema identity documentation.
- Block E / D1: verify code_chunk_sql and postgres adapter.
- Block G / E1: inspect batch processor stage logging.
- Block H / H1: audit status predicates and write counter consistency tests.

Do not apply large changes in Wave 1. Prefer read-only analysis plus tiny isolated patches.

### Wave 2 — coordinated implementation
Order:
1. A1 finalizes `file_identity.py` and `files/crud.py` usage.
2. D1 finalizes `code_chunk_sql.py` and `postgres_run.py` contract.
3. D2 updates `DocstringChunker` only after D1 API is stable.
4. B1 updates scanner/policy only after identity helper is stable.
5. E1 updates vectorization stage logs and chunking candidate filters after B1 and D1/D2.
6. H1 aligns `get_database_status` predicates after B1 and E1 confirm lifecycle/ignore semantics.
7. A2 updates comprehensive analysis path lookup after A1 identity helper is stable.

### Wave 3 — documentation and migration design
- C1 updates `schema_identity_map.md`.
- C1 updates UUID transition plan based on what actually changed.
- Coordinator updates `00-index.md` if step order changes.

## Files that must not be edited concurrently

```text
code_analysis/core/database/files/crud.py
code_analysis/core/project_ignore_policy.py
code_analysis/core/database/code_chunk_sql.py
code_analysis/core/database_driver_pkg/drivers/postgres_run.py
code_analysis/core/docstring_chunker_pkg/docstring_chunker.py
code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py
code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py
code_analysis/commands/comprehensive_analysis_mcp/execute_single.py
```

Only one performer may own each of these at a time.

## Merge verification after each block
Run the local tests owned by the block, then restart and run MCP:

```text
health
get_database_status
get_worker_status(worker_type="file_watcher")
get_worker_status(worker_type="indexing")
get_worker_status(worker_type="vectorization")
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

## Global success criteria
- No false cross-project relative-path conflict.
- Normal comprehensive analysis does not clear another project's file data.
- Watcher remains bounded and does not broadly scan `.venv`.
- PostgreSQL and SQLite SQL contracts remain portable.
- `chunk_count` and `vectorized_chunks` continue to grow after restart.
- `get_database_status` counters are internally consistent or explicitly non-additive.
- UUID migration remains separate and design-only until explicitly scheduled.
