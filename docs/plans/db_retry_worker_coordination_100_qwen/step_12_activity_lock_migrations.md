# Step 12 — SQLite/PostgreSQL migrations

Previous: [Step 11](step_11_schema_activity_locks.md). Next: [Step 13](step_13_worker_activity_coordinator.md).

Files:
- `code_analysis/core/database_driver_pkg/drivers/sqlite_migrations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_migrations.py`

Goal: make `project_activity_locks` appear in existing databases without manual DB reset.

Required changes:
1. Add idempotent migration for SQLite: create `project_activity_locks` and `idx_project_activity_locks_lease_until` only if absent.
2. Add idempotent migration for PostgreSQL with backend-correct DDL.
3. Do not use SQLite-only constructs in PostgreSQL migrations.
4. Do not reference `rowid`, `code_content_fts`, or other SQLite-specific internals in PostgreSQL mode.
5. Keep migration safe to run repeatedly.

Verification:
- Run migration/unit tests where available.
- Use schema/table inspection command or integration test to confirm the table and index exist after migration.
- Record result in [Step 28](step_28_observations_document.md).
