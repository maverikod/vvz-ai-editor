# Architecture addendum - project-scoped smart coordination

Status: mandatory addendum for the DB retry and worker coordination plan.

This addendum records facts found during source review and refines the worker-coordination design. It must be read before executing Step 13, Step 14, Step 16, Step 24, Step 25, Step 32, and Step 35.

## Source facts that the plan must account for

1. `code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py` currently scans one `watch_dir`, not one project. It discovers all projects under the watched directory, runs `scan_directory(...)` once for the whole watch directory, computes per-project deltas, and then calls `processor.queue_changes(watch_dir, delta)`.
2. The existing `LockManager` is a watch-dir-level filesystem lock. It prevents competing watcher processes for the same watched directory. It must remain in place.
3. Watcher auto-create currently starts auto-indexing from inside watcher through a daemon thread that runs `UpdateIndexesMCPCommand`. This active mutation path must be removed and replaced with normal indexer scheduling/marking.
4. Watcher code currently contains direct SQL that uses SQLite-style placeholders and `julianday('now')`. PostgreSQL compatibility must be verified through the driver abstraction or fixed with backend-aware SQL/helpers.
5. `project_activity_locks` and `code_analysis/core/worker_project_activity.py` do not exist yet. They are a new coordination subsystem and must be tested on both SQLite and PostgreSQL paths.
6. PostgreSQL execution is split across `postgres.py`, `postgres_run.py`, `postgres_transactions.py`, `postgres_operations.py`, and RPC handlers. Retry implementation may require changes in all of these files while preserving the public driver contract.

## Refined coordination model

Use smart project-scoped coordination. Do not serialize the entire server and do not block unrelated projects.

Rules:

1. At any moment, only one worker pipeline may mutate one `project_id`.
2. Different projects may be processed concurrently if they do not share project-level or row-level/block-level write sets.
3. Allowed production owner types are exactly `watcher`, `indexer`, and `command`.
4. `owner_type=auto_indexing` must not be used by production mutation paths.
5. A project-level lease protects high-level ownership of mutation work for one project.
6. Inside the project lease, the worker must mutate only the DB rows or logical blocks that will actually be changed.
7. Read-only filesystem discovery/scanning may happen without a project mutation lease only if it does not write DB state. Any DB write, purge, queueing, indexing, chunk deletion, vector invalidation, or project metadata update must be covered by the project lease.
8. The existing watch-dir filesystem lock remains a watcher-process guard. The new project locks are cross-worker mutation guards.

## Mandatory watcher strategy

The watcher must not acquire one lease for an entire watch-dir scan and must not acquire all project leases for a shared watch-dir scan.

Use this strategy only:

1. Keep project discovery and filesystem scanning read-only with respect to per-project DB mutation state.
2. After the scan produces per-project data, process DB mutation phases one `project_id` at a time.
3. Acquire a project activity lease only for the currently mutated `project_id`.
4. If one project is busy, skip only that project for the current cycle and continue other safe projects.
5. Release each project lease before moving to another project.

## Watcher write ordering

Watcher must use a staged write strategy for each leased project.

Phase 1: build staging and insert new files first.

1. Build a normalized candidate set from filesystem paths for the target `project_id`.
2. Reject candidates outside the target project root.
3. Apply ignore patterns.
4. Apply ignore-exception patterns after ignore patterns. An ignore exception can re-include a path that a broader ignore pattern excluded.
5. Load the final candidate set into a temporary/staging relation for the current project and scan cycle.
6. Insert only new file rows by joining staged candidates against existing DB rows for the same `project_id`.
7. This phase must not mark existing files deleted and must not delete chunks.

Phase 2: update and delete after inserts are durable.

1. For changed files, mutate only rows whose content metadata/hash/mtime/size changed.
2. For deleted files, mutate only rows that are present in DB but absent from the staged candidate set.
3. Delete or invalidate chunks only for rows confirmed as changed/deleted.
4. The operation must be idempotent: repeating the same scan cycle after transient retry must not duplicate file rows or corrupt chunk state.

## SQL and backend requirements

1. Staging must be implemented as a temporary table, backend-specific CTE/value table, or storage-layer helper. Backend-specific SQL must be isolated.
2. PostgreSQL implementation must use `INSERT ... SELECT ... ON CONFLICT DO NOTHING` or an equivalent storage abstraction.
3. SQLite implementation must use `INSERT OR IGNORE` or an equivalent storage abstraction.
4. Do not place filesystem side effects inside retried DB write blocks.
5. Retry the logical write transaction, not individual statements inside one logical batch.
6. Unknown commit outcome must stop retries and return structured error with `commit_outcome_unknown=true` and `retryable=false`.

## Required plan updates

1. Step 13 must define project-scoped lease APIs and row/block mutation responsibilities.
2. Step 14 must keep raw watch-dir discovery/scan read-only and coordinate only per-project DB mutation phases.
3. Step 15 must define how ignore and ignore-exception rules are converted into the staged candidate set before insert/update/delete.
4. Step 16 must remove watcher daemon auto-indexing and make the normal indexer acquire the same project lease before mutating chunks, indexes, vector state, or file indexing flags.
5. Step 24 and Step 25 must include concurrency tests proving that two workers cannot mutate the same project concurrently, while independent projects are not unnecessarily blocked.
6. Step 32 must verify real MCP/log behavior with `[WORKER_COORD]` acquire/skip/release records.

## Acceptance criteria added by this addendum

1. Two workers attempting to mutate the same `project_id` cannot proceed concurrently.
2. Two workers mutating different `project_id` values are not globally blocked by the coordination design.
3. New-file insertion happens before changed/deleted-file mutation in watcher write flow.
4. Ignore exceptions are honored when building the candidate set.
5. Changed/deleted operations mutate only affected file rows and dependent chunks.
6. Watcher-launched daemon auto-indexing is removed from the active mutation path.
7. Auto-created projects are processed through the normal indexer path.
8. PostgreSQL and SQLite tests prove the staging/insert/update/delete strategy works on both backends.
