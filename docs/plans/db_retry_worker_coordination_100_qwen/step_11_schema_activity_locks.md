# Step 11 - Schema definition for activity locks

Previous: [Step 10](step_10_config_validator.md). Next: [Step 12](step_12_activity_lock_migrations.md).

File: `code_analysis/core/database/schema_definition.py`

## Goal

Add the backend-neutral schema table used by project-scoped worker leases.

## Required changes

1. Add table `project_activity_locks` if it does not already exist.
2. The table must have exactly one active lease row per project. Use `project_id` as the primary key.
3. Columns:
   - `project_id TEXT PRIMARY KEY`
   - `owner_type TEXT NOT NULL`
   - `owner_id TEXT NOT NULL`
   - `activity TEXT NOT NULL`
   - `acquired_at REAL NOT NULL`
   - `heartbeat_at REAL NOT NULL`
   - `lease_until REAL NOT NULL`
4. Time values are Unix epoch seconds as `float`, produced by the application layer. Do not use backend-specific time functions as the canonical stored value.
5. Add index `idx_project_activity_locks_lease_until` on `lease_until`.
6. Keep schema definition backend-neutral. Backend-specific DDL conversion belongs to migration/driver code from [Step 12](step_12_activity_lock_migrations.md).

## Constraints and validation ownership

1. The schema stores values; validation of allowed `owner_type` and `activity` belongs to [Step 13](step_13_worker_activity_coordinator.md).
2. The table is a lease table, not a history table. Re-acquiring or heartbeat by the same owner updates the row for the same `project_id`.
3. Do not add a second lease table for watcher/indexer unless Step 13 explicitly documents why the shared table is insufficient.

## Forbidden

- Do not use PostgreSQL advisory locks here.
- Do not duplicate a similar existing table without checking first.
- Do not put PostgreSQL-only or SQLite-only SQL in watcher/indexer code.

## Verification

Schema read/CST check must show table and index definitions. Migration is handled in [Step 12](step_12_activity_lock_migrations.md). Record command, expected result, actual result, and status in [Step 28](step_28_observations_document.md).
