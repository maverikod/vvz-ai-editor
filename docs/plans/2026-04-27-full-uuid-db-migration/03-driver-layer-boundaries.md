# Step 03 — Driver layer boundaries

## Goal
Define and enforce the database layering before any UUID schema or migration work starts.

## Current code checked
The current driver stack was inspected in:

```text
code_analysis/core/database_driver_pkg/drivers/base.py
code_analysis/core/database_driver_pkg/drivers/postgres_operations.py
code_analysis/core/database/schema_sync_sql_postgres.py
```

Important current facts:

```text
BaseDatabaseDriver.insert(...) -> int
PostgreSQLOperations.insert(...) -> int
PostgreSQLOperations.insert returns int(row[0]) only if returned PK is int, otherwise returns 0.
schema_sync_sql_postgres._map_column_type has no UUID mapping yet.
```

This means UUID schema migration cannot be correct until the universal driver contract stops assuming integer inserted IDs.

## Required architecture
Keep layers separate and make the adaptation responsibility explicit:

```text
Command/application layer
  - emits backend-neutral logical DB operations;
  - works with domain values and UUID strings;
  - validates MCP/API inputs;
  - must not contain PostgreSQL or SQLite DDL, casts, placeholder syntax, UPSERT syntax, FTS syntax, or rowid assumptions.

Universal DB/driver contract and selected-backend adaptation layer
  - defines logical insert/select/update/delete contracts;
  - receives backend-neutral requests from commands;
  - selects the configured backend;
  - adapts logical requests to the selected backend contract;
  - supports inserted IDs of type int or str during transition;
  - exposes logical UUID type if schema definitions use it;
  - must not hard-code one backend's SQL dialect as universal behavior.

PostgreSQL-specific driver/schema layer
  - strictly follows PostgreSQL syntax and semantics;
  - maps logical UUID to PostgreSQL native UUID;
  - handles PostgreSQL DDL, constraints, indexes, migrations, placeholders/casts, RETURNING, and PostgreSQL UPSERT behavior;
  - may use PostgreSQL-specific SQL only inside this layer.

SQLite-specific driver/schema layer
  - strictly follows SQLite syntax and semantics;
  - is a full supported backend-specific implementation, not an optional partial fallback;
  - maps logical UUID to canonical UUID TEXT;
  - owns SQLite DDL, rebuild/migration behavior, placeholders, UPSERT behavior, FTS, and rowid semantics.
```

## Files to inspect/edit
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite_operations.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py`
- `code_analysis/core/database/schema_sync_sql.py`

## Required changes
1. Introduce a DB identity return type alias, for example:

```python
DbIdentity = int | str
```

2. Change universal insert contract:

```python
def insert(...) -> DbIdentity | None
```

or a typed result object if that already fits the codebase better.

3. Update driver docstrings: inserted row ID is not always SQLite `lastrowid`.
4. Make PostgreSQL insert return UUID strings when `RETURNING id` returns UUID/text.
5. Make SQLite insert return string IDs for explicit UUID/TEXT PK inserts and integer IDs only for tables that genuinely remain integer identities.
6. Ensure raw `execute` result shape can carry string returned IDs where applicable.
7. Add tests proving that the same logical insert request is adapted into PostgreSQL-valid behavior on PostgreSQL and SQLite-valid behavior on SQLite.

## Must not do
- Do not patch command code to work around driver return type bugs.
- Do not put PostgreSQL `::uuid` casts in command/application code.
- Do not put SQLite rowid/FTS assumptions in command/application code.
- Do not keep `insert -> int` while changing primary keys to UUID.
- Do not silently return `0` for successful UUID inserts.
- Do not describe SQLite as optional or partial; it is a full backend-specific implementation.

## Tests required
1. Base driver typing test or static test proving insert result can be `str`.
2. PostgreSQL insert operation test where `RETURNING id` returns UUID string and the driver returns that string.
3. SQLite insert operation test where explicit UUID/TEXT primary key insert returns the UUID string or a typed result that exposes it.
4. Regression test: PostgreSQL insert must not return `0` for UUID primary keys.
5. Universal-adaptation test: command-level logical insert is translated through the selected backend path, not through command-side SQL branching.
6. Specific-driver syntax tests: PostgreSQL branch emits PostgreSQL-valid SQL; SQLite branch emits SQLite-valid SQL.

## Verification
No schema migration in this step. Run driver-level tests only.

## References
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `10-data-migration-postgres-driver-branch.md`
- `11-data-migration-sqlite-driver-branch.md`
