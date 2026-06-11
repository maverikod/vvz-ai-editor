# Step 04 — Driver insert return contract

## Goal
Fix the insert-return contract before UUID primary keys are introduced. UUID migration must not proceed while the universal driver contract says `insert(...) -> int` or while any selected backend driver loses a non-integer returned identity.

## Current code checked
Verified files:

```text
code_analysis/core/database_driver_pkg/drivers/base.py
code_analysis/core/database_driver_pkg/drivers/postgres_operations.py
```

Current behavior:

```text
BaseDatabaseDriver.insert(...) -> int
PostgreSQLOperations.insert(...) -> int
PostgreSQLOperations.insert executes INSERT ... RETURNING <pk>
if returned pk is int: returns int(row[0])
otherwise: returns 0
```

This is a hard blocker for UUID PKs on both supported backends.

## Required architecture
The insert contract must follow this layering:

```text
command/application logical insert request
-> universal DB/driver contract and selected-backend adaptation layer
-> PostgreSQL-specific insert implementation
-> PostgreSQL DB

command/application logical insert request
-> universal DB/driver contract and selected-backend adaptation layer
-> SQLite-specific insert implementation
-> SQLite DB
```

The universal layer owns the logical return shape and adapts command-level insert requests to the selected backend contract. The specific backend driver owns backend-native SQL behavior: PostgreSQL `RETURNING`, PostgreSQL UUID values, SQLite `lastrowid`, SQLite explicit TEXT UUID primary keys, placeholders, and UPSERT details.

## Files to edit
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- any wrapper that exposes `_lastrowid()` or `lastrowid`

## Required changes
1. Add a shared type alias, for example:

```python
DbIdentity = int | str
```

2. Change the abstract insert contract from integer-only to:

```python
def insert(...) -> DbIdentity | None
```

or a result object if the project already has a suitable result type.

3. PostgreSQL insert must return the actual returned primary key:

```text
int for old integer PK tables during transition
str for UUID PK tables
None only if no returning value exists
```

4. PostgreSQL must never return `0` just because the returned value is not an integer.
5. SQLite insert must support explicit UUID/TEXT primary keys for migrated UUID tables and return that explicit UUID string or a typed result that exposes it.
6. SQLite may return integer `lastrowid` only for tables that genuinely remain integer identities.
7. Raw `execute` / `_lastrowid()` callers must be audited before UUID tables are switched.
8. Add universal-adaptation tests proving the same logical insert request routes to PostgreSQL-valid behavior on PostgreSQL and SQLite-valid behavior on SQLite.

## Layering requirements
- Universal driver contract owns return shape and selected-backend adaptation.
- PostgreSQL operations own PostgreSQL `RETURNING` behavior and PostgreSQL UUID conversion.
- SQLite operations own SQLite explicit ID / `lastrowid` behavior and canonical TEXT UUID handling.
- Command/CRUD code must not compensate for a broken driver by re-querying by path.
- Backend-specific casts/defaults/placeholders belong in the matching backend driver/schema branch only.

## Must not do
- Do not keep public annotation `-> int` for insert.
- Do not return `0` for UUID primary keys.
- Do not use path lookup to recover inserted UUID ids.
- Do not introduce PostgreSQL-only SQL into application CRUD to work around driver limitations.
- Do not introduce SQLite `lastrowid` assumptions into universal or command code for migrated UUID tables.
- Do not describe SQLite as compatibility-only; it is a full supported backend with a backend-native insert contract.

## Tests required
1. PostgreSQL operation insert with integer PK returns integer.
2. PostgreSQL operation insert with UUID PK returns UUID string.
3. PostgreSQL operation insert never returns `0` for non-integer returned id.
4. SQLite operation insert with explicit UUID/TEXT PK returns UUID string or equivalent typed identity result.
5. SQLite operation insert with real integer table may still return integer `lastrowid`.
6. CRUD code no longer depends on `_lastrowid()` for migrated UUID tables.
7. Universal-adaptation test proves command-level insert does not branch on backend SQL directly.

## Runtime verification
This step is driver-level. After implementation, before schema migration, run driver/unit tests for both PostgreSQL and SQLite. Do not run live UUID migration yet.

## References
- `03-driver-layer-boundaries.md`
- `12-file-crud-and-path-identity.md`
- `18-test-matrix-and-runtime-verification.md`
