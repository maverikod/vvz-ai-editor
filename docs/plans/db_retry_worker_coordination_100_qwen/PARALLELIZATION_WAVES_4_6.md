# Parallelization waves 4-6

Previous: [Waves 2-3](PARALLELIZATION_WAVES_2_3.md). Next: [Waves 7-8](PARALLELIZATION_WAVES_7_8.md).

## Wave 4: schema and coordinator foundation

### Agent G: schema and migrations

Can start immediately in parallel with Waves 2-3.

Owns:
- Step 11 schema activity locks.
- Step 12 activity lock migrations.

Files:
- `code_analysis/core/database/schema_definition.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_migrations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_migrations.py`

Waits for:
- No source dependency, only the agreed table shape from Step 11.

Blocks:
- Agent I worker activity coordinator.
- Step 24 worker activity tests.

Deliverable:
- `project_activity_locks` exists in schema.
- SQLite and PostgreSQL migrations are idempotent and backend-aware.

### Agent I: worker activity coordinator

Starts after Agent G defines table shape and migrations.

Owns:
- Step 13 worker activity coordinator.
- Step 24 worker activity tests.

Files:
- `code_analysis/core/worker_project_activity.py`
- `tests/test_worker_project_activity.py`

Waits for:
- Agent G schema and migration shape.

Blocks:
- Agent J watcher integration.
- Agent K indexer integration.
- Agent L watcher/indexer coordination tests.

Deliverable:
- Race-safe acquire, heartbeat, release, and get activity API.
- Tests prove lease ownership, expiry, and release behavior.

## Wave 5: compatibility lane

### Agent H: SQLite, base driver, client fallback

Starts after Agents A and B are merged.

Owns:
- Step 17 SQLite retry compatibility.
- Step 18 base driver compatibility.
- Step 19 client transient fallback.
- Step 26 SQLite retry tests.

Files:
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_client/transient.py`
- `tests/test_sqlite_retry_compatibility.py`

Waits for:
- Agent A structured transient details.
- Agent B shared retry policy.

Can run in parallel with:
- Agent I after G is ready.
- Agent D if imports are stable.

Blocks:
- SQLite compatibility acceptance.

Deliverable:
- SQLite retry covers only busy/locked transient failures.
- Base driver remains backend-neutral.
- Client string matching remains fallback only.

## Wave 6: watcher and indexer integration

### Agent J: watcher integration

Starts after Agent I, and after Agent E and Agent D for Step 15 metadata/logical-write dependencies.

Owns:
- Step 14 watcher coordination.
- Step 15 ignore purge metadata.

Files:
- `code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py`
- `code_analysis/core/file_watcher_pkg/ignore_pre_scan_purge.py`

Waits for:
- Agent I coordinator API.
- Agent E logical-write metadata fields.
- Agent D logical-write retry path.

Can run in parallel with:
- Agent K after Agent I is ready.

Blocks:
- Agent L watcher/indexer coordination tests.
- Step 32 MCP worker coordination check.

Deliverable:
- Watcher skips busy project IDs and logs `[WORKER_COORD] watcher skip ...`.
- Ignore purge logical write includes `operation_name`, `project_id`, and `lock_scope`.

### Agent K: indexer integration

Starts after Agent I.

Owns:
- Step 16 indexer coordination.

Files:
- `code_analysis/core/indexing_worker_pkg/processing.py`

Waits for:
- Agent I coordinator API.

Can run in parallel with:
- Agent J.

Blocks:
- Agent L watcher/indexer coordination tests.
- Step 32 MCP worker coordination check.

Deliverable:
- Indexer skips busy project IDs and logs `[WORKER_COORD] indexer skip ...`.
- No SQL retry or ignore deletion logic is added to indexer.

### Agent L: watcher/indexer coordination tests

Can draft tests after Agent I API is known. Final passing run waits for Agents J and K.

Owns:
- Step 25 watcher/indexer coordination tests.

Files:
- `tests/test_watcher_indexer_coordination.py`

Waits for:
- Agent I coordinator implementation.
- Agent J watcher integration.
- Agent K indexer integration.

Deliverable:
- Tests prove watcher and indexer skip a project when the other worker has an active lease.

## Wave 4-6 merge rule

Merge Agent G before Agent I. Merge Agent I before Agents J and K. Merge Agents J and K before Agent L final test pass. Agent H can merge independently after Agents A and B if tests pass.
