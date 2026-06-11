# Step 15 - Ignore, staging, and purge metadata

Previous: [Step 14](step_14_watcher_coordination.md). Next: [Step 16](step_16_indexer_coordination.md).

Mandatory context: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md).

Files:

- `code_analysis/core/file_watcher_pkg/ignore_pre_scan_purge.py`
- `code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py`
- new watcher staging helper module if needed
- database/storage helper module if backend-specific staging SQL is needed

## Goal

Replace unsafe pre-scan purge semantics with a deterministic staged candidate-set flow that honors ignore rules and ignore exceptions, inserts new files first, and mutates only affected rows.

## Definitions

- Candidate path: a normalized project-relative path discovered from the filesystem scan.
- Ignored path: a path matched by an ignore pattern and not re-included by an ignore-exception pattern.
- Final candidate set: candidate paths that remain after ignore patterns and ignore-exception patterns are applied.
- Staging relation: temporary table, cycle-scoped table, CTE, or storage helper input containing the final candidate set for one `project_id` and one scan cycle.

## Required behavior

For each `project_id` selected by watcher, execute this exact order under the Step 13 project activity lease:

1. Build candidate paths from filesystem scan results for that project only.
2. Normalize every candidate path to project-relative POSIX form.
3. Reject candidates outside the target project root.
4. Apply ignore patterns.
5. Apply ignore-exception patterns after ignore patterns. An ignore exception re-includes a path excluded by a broader ignore pattern.
6. Store the final candidate set in a staging relation for the current `project_id` and scan cycle.
7. Insert new file rows first by anti-joining staged candidates against existing `files` rows for the same `project_id`.
8. Update changed file rows second.
9. Mark/delete absent file rows third by comparing existing DB rows against the staged candidate set.
10. Invalidate/delete chunks only for rows confirmed as changed or deleted.

## Staging fields

The staged candidate set must contain at least:

- `project_id`
- `relative_path`
- `absolute_path`
- `size_bytes` or `NULL` when intentionally unavailable
- `mtime_ns` or `NULL` when intentionally unavailable
- `content_hash` or `NULL` when hashing is intentionally deferred
- `scan_cycle_id`

Optional debug fields are allowed only if they do not affect behavior:

- `ignore_matched_pattern`
- `ignore_exception_matched_pattern`

## Backend requirements

1. PostgreSQL and SQLite must both be supported.
2. Backend-specific SQL must be isolated in a storage helper or in clearly separated backend branches in the staging helper.
3. PostgreSQL implementation must use one of these exact approaches:
   - temporary table plus `INSERT ... SELECT ... ON CONFLICT DO NOTHING`; or
   - CTE/value table plus `INSERT ... SELECT ... ON CONFLICT DO NOTHING`; or
   - an existing storage abstraction that produces equivalent SQL.
4. SQLite implementation must use one of these exact approaches:
   - temporary table plus `INSERT OR IGNORE`; or
   - CTE/value table plus `INSERT OR IGNORE`; or
   - an existing storage abstraction that produces equivalent SQL.
5. Do not use SQLite-only constructs in PostgreSQL mode.
6. Do not use PostgreSQL-only constructs in SQLite mode unless hidden behind backend-specific branches.
7. Staging rows must be transaction-local or identified by `scan_cycle_id` and cleaned before the next cycle can reuse them.

## Coordination requirements

1. Staging and all DB mutations must run under the Step 13 project activity lease.
2. Use precise activities:
   - `watcher_staging`
   - `watcher_inserting_new_files`
   - `watcher_updating_changed_files`
   - `watcher_marking_deleted_files`
3. Long phases must heartbeat the lease.
4. If the lease cannot be acquired, skip the project for the current cycle and do not mutate its DB rows.

## Idempotency requirements

Repeating the same logical watcher write transaction after a retry must not:

1. duplicate file rows;
2. mark active files deleted;
3. delete chunks for unchanged files;
4. lose ignore-exception files;
5. corrupt `needs_chunking` or equivalent indexing flags.

## Forbidden

- Do not purge before constructing the staged candidate set.
- Do not delete rows only because a broad ignore pattern matched them if an ignore exception re-includes them.
- Do not perform filesystem side effects inside retried DB transactions.
- Do not use direct `project_activity_locks` SQL here; use the coordinator API.
- Do not mutate rows for any project other than the currently leased `project_id`.

## Verification

Run [Step 25](step_25_tests_watcher_indexer_coordination.md).

Required proof:

1. New file rows are inserted before changed/deleted rows are processed.
2. Ignore exceptions are honored after ignore patterns.
3. Staged candidates outside the project root are rejected.
4. Changed/deleted operations affect only expected rows.
5. Chunk invalidation/deletion happens only for changed/deleted rows.
6. SQLite and PostgreSQL staging paths pass equivalent tests.

## Observation entry

Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
