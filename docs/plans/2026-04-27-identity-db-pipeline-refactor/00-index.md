# Refactor plan — identity, DB layers, indexing/chunking/vectorization pipeline

## Purpose
This directory contains step-by-step refactoring tasks. Each file is one isolated step for one code area or one new code file. The steps are written for a weak model: each step is explicit, bounded, and references related steps instead of relying on hidden context.

## Current runtime baseline
At the time this index was updated, MCP `get_database_status` showed:

```text
active files: 2053
indexed: 2052 / 2053 = 99.95%
needing_indexing: 15  # inconsistent with indexed/active; see Step 14
chunks total: 1141
vectorized chunks: 1136 / 1141 = 99.56%
```

The pipeline is alive:

```text
watcher -> indexing -> chunking -> vectorization
```

Known active status problem:

```text
get_database_status counters are not internally consistent:
active=2053, indexed=2052, needing_indexing=15.
Step 14 owns this investigation and fix.
```

## Step order
1. `01-code_analysis_core_database_files_crud.md`
2. `02-code_analysis_commands_comprehensive_analysis_mcp_execute_single.md`
3. `03-code_analysis_core_file_identity.md`
4. `04-code_analysis_core_project_ignore_policy.md`
5. `05-code_analysis_core_database_schema_identity.md`
6. `06-code_analysis_core_database_code_chunk_sql.md`
7. `07-code_analysis_core_file_watcher_pkg_scanner.md`
8. `08-code_analysis_core_database_driver_pkg_drivers_postgres_run.md`
9. `09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md`
10. `10-code_analysis_core_vectorization_worker_pkg_batch_processor.md`
11. `11-code_analysis_core_vectorization_worker_pkg_processing_cycle_projects.md`
12. `12-uuid_business_identity_transition.md`
13. `13-parallelization-map.md`
14. `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`

## Global rules for every step
- Do not edit `.venv`, `site-packages`, installed packages, `mcp-proxy-adapter`, or `queuemgr`.
- For Python source changes use MCP/CST workflow whenever available: search/read -> CST inspect -> preview diff -> apply -> read verification.
- Do not mix schema migration with hotfixes.
- Do not use paths as global business identifiers.
- Do not globally ban `.venv`; config intentionally supports allowlisted dependency packages.
- Runtime changes require server restart and MCP verification.

## Required MCP verification after each implementation step

```text
health
get_database_status
get_worker_status(worker_type="file_watcher")
get_worker_status(worker_type="indexing")
get_worker_status(worker_type="vectorization")
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
view_worker_logs(worker_type="vectorization", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

## Definition of done for this plan
- False cross-project relative-path conflicts are eliminated.
- Destructive path-only cleanup is removed or strictly justified and tested.
- DB/dialect SQL remains portable between SQLite and PostgreSQL.
- Chunking/vectorization continue to produce chunks and embeddings.
- File identity rules are centralized and tested.
- `get_database_status` counters are internally consistent or explicitly documented as non-additive.
- UUID transition is designed separately and not mixed with hotfixes.
