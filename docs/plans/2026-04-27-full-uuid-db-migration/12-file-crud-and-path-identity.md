# Step 12 — File CRUD and path identity after UUID migration

## Goal
Update file CRUD code after `files.id` becomes UUID while preserving the already-fixed project-scoped path identity model.

## Current code checked
`code_analysis/core/database/files/crud.py` currently assumes integer file ids:

- `add_file(...) -> int`
- `get_file_id(...) -> Optional[int]`
- `get_file_by_id(file_id: int)`
- `delete_file(file_id: int)`
- `_clear_file_vectors(file_id: int)`
- `clear_file_data(file_id: int)`

`add_file` currently inserts into `files` without an explicit `id` and then reads `_lastrowid()`. This is invalid after PostgreSQL UUID primary key migration unless the DB has a verified UUID default and the driver returns it correctly.

The same file currently has the correct project-scoped path model. The cross-project check is based on the same absolute path only. Do not reintroduce cross-project `relative_path` matching.

## Prerequisites
Complete first:
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `09-migration-framework-and-id-map.md`

## Files to edit
- `code_analysis/core/database/files/crud.py`
- `code_analysis/core/database/files/update.py`
- `code_analysis/core/database/files/query.py` if present
- tests for file CRUD and cross-project path behavior

## Required changes
1. Change file id type annotations from integer to UUID string.
2. Generate UUID4 in Python before inserting a new file row, unless a PostgreSQL-specific default is explicitly chosen and driver-return tests pass.
3. Insert `files.id` explicitly in the insert statement when Python-generated UUIDs are used.
4. Stop using `_lastrowid()` for `files` after UUID migration.
5. Existing update path must accept UUID string returned from DB.
6. `get_file_id` returns optional UUID string.
7. `get_file_by_id`, `delete_file`, `_clear_file_vectors`, and `clear_file_data` accept UUID strings.
8. All path lookups must remain project-scoped.
9. Same-project relative path lookup may remain project-local only.
10. Path normalization behavior must not change.

## Layering requirements
- Command layer passes UUID strings and does not use PostgreSQL casts.
- Universal DB layer accepts UUID strings as parameters.
- PostgreSQL driver/schema layer owns UUID column typing.
- Do not put PostgreSQL-specific casts in generic CRUD SQL unless tests prove the driver layer requires it.

## Must not do
- Do not use paths as a fallback to recover IDs after insert.
- Do not rely on `_lastrowid()` for UUID tables.
- Do not convert UUIDs to integers or hashes.
- Do not make chunks or vector indexes infer ownership by path.
- Do not change project or watch_dir id generation here.
- Do not mix cleanup/trash behavior into this step; see Step 17.

## Tests required
1. `add_file` returns a valid UUID string.
2. Inserted row has that exact UUID in `files.id`.
3. `get_file_id` returns a UUID string.
4. `get_file_by_id` works with a UUID string.
5. Same relative path in two projects remains safe.
6. Same project same path updates a single UUID row.
7. Vector/chunk cleanup works by UUID file id.
8. No CRUD test depends on integer `lastrowid` for `files`.

## Runtime verification
After migration and restart:

```text
list_project_files(project_id=<project>)
get_database_status
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- file ids in command results are UUID strings;
- add/update/cleanup still works;
- no cross-project relative path collision returns.

## References
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `16-mcp-api-compatibility.md`
