# Step 16 — MCP API compatibility after UUID migration

## Goal
Update MCP command schemas, outputs, diagnostics, and compatibility behavior so callers can work with UUID identifiers after full database migration on both supported backends: PostgreSQL and SQLite.

## Architecture constraint
MCP commands must follow the project layering:

```text
command/application code
-> universal DB/driver contract and selected-backend adaptation layer
-> PostgreSQL-specific driver
-> PostgreSQL DB

command/application code
-> universal DB/driver contract and selected-backend adaptation layer
-> SQLite-specific driver
-> SQLite DB
```

Command schemas may declare UUID-string values and validate UUID format. They must not embed PostgreSQL casts, PostgreSQL DDL, SQLite rowid assumptions, SQLite FTS assumptions, or backend-specific placeholder/UPSERT syntax. The universal driver/adaptation layer routes logical requests to the selected backend. Each specific driver owns strict syntax and behavior for its DB.

## Current risk
Many command outputs and internal payloads currently expose integer database IDs such as:

```text
file_id
class_id
function_id
method_id
chunk_id
id
snapshot_id
duplicate_id
```

After full UUID migration these fields become UUID strings where they represent DB identity. Some fields remain integers because they are not DB identity:

```text
vector_id  # FAISS vector id / position, remains integer unless FAISS is redesigned
line
end_line
chunk_ordinal
binding_level
token_count
```

`project_id` and `watch_dir_id` are already UUID-like strings. After migration they must be validated as canonical UUIDs at API boundaries. PostgreSQL stores them as native UUID; SQLite stores them as canonical UUID TEXT.

## Prerequisites
Complete inventory first:
- `01-current-schema-inventory.md`
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`

Final API schema changes must wait until decisions from:
- `12-file-crud-and-path-identity.md`
- `13-indexing-ast-cst-entity-writes.md`
- `14-docstring-chunks-and-chunk-uuid.md`
- `15-vector-index-and-faiss-mapping.md`

## Files to inspect/edit
- command metadata files under `code_analysis/commands/**`
- command result dataclasses/models
- command help/schema generation
- semantic search commands
- AST/CST commands
- list/read file commands
- comprehensive analysis commands
- vectorization/chunking status commands
- database/status diagnostic commands
- tests for MCP command schemas and runtime responses

## Required code search before edits
Use MCP source tools before editing:

```text
fulltext_search(query="file_id chunk_id class_id function_id method_id vector_id")
fulltext_search(query="lastrowid file_id")
fulltext_search(query="id type integer file_id command metadata")
fulltext_search(query="get_database_status list_project_files semantic_search")
```

If exact fulltext search is blocked or returns no results, inspect candidate command packages directly and record the tool limitation.

## Required classification
Create a compatibility table:

```text
field_name
current_type
new_type
semantic meaning
command(s)
backend storage: PostgreSQL UUID | SQLite canonical TEXT | integer non-identity
backward compatibility behavior
```

At minimum classify:

```text
project_id: UUID string API value; PostgreSQL UUID storage; SQLite canonical TEXT storage
watch_dir_id: UUID string API value; PostgreSQL UUID storage; SQLite canonical TEXT storage
file_id: UUID string
class_id: UUID string
function_id: UUID string
method_id: UUID string
chunk_id: UUID string for code_chunks.id
chunk_uuid: stable UUID/TEXT business key, remains string
vector_id: integer FAISS id, remains integer
snapshot_id: UUID string
node_id: tree logical text id, remains string
line/end_line: integer, unchanged
```

## Required API decisions
1. Do command outputs keep field names such as `file_id` and change type to string, or add transition fields?
2. Do commands accept legacy integer IDs during a transition period?
3. If legacy IDs are accepted, where is the lookup map stored after migration?
4. Which commands should prefer path+project lookup instead of ID lookup?
5. Which commands must reject integers after migration with a clear error?

Recommended:
- For full migration, primary fields keep names such as `file_id`, but values are UUID strings.
- Add clear release note / schema docs that IDs are strings.
- Do not keep permanent integer compatibility unless a product client needs it.
- If temporary compatibility is needed, expose explicit `legacy_int_id` only in migration/diagnostic commands.

## Required status/diagnostic command checks
The plan must include sample output checks for these commands and must verify they do not claim integer DB identities after migration:

```text
get_database_status
list_project_files
semantic_search
list_code_entities
get_code_entity_info
get_imports
find_usages
get_ast
cst_load_file
```

Required expectations:
- `get_database_status` does not report migrated table IDs as integer-only identities.
- `list_project_files` returns UUID-shaped file IDs and UUID-shaped `project_id`/`watch_dir_id` values.
- `semantic_search` returns UUID `file_id`, UUID `chunk_id` for `code_chunks.id`, string `chunk_uuid`, and integer `vector_id` if exposed.
- AST/CST commands keep logical tree/node IDs separate from DB identity and do not label DB IDs as integers.
- Diagnostics must distinguish API representation from backend storage where needed: PostgreSQL UUID vs SQLite canonical TEXT.

## Layering requirements
- Command layer validates/serializes UUID strings.
- Command layer must not generate backend-specific casts, placeholders, UPSERT clauses, FTS SQL, or rowid logic.
- Universal DB layer receives UUID strings or UUID-safe logical values and adapts requests for the selected backend.
- PostgreSQL driver/schema owns PostgreSQL UUID typing and DB casts.
- SQLite driver/schema owns canonical TEXT UUID storage and SQLite rowid/FTS behavior.
- API compatibility must not require path-based identity.

## Must not do
- Do not convert UUIDs to integers for old clients.
- Do not make command layer query mapping tables unless the command is explicitly a migration/diagnostic command.
- Do not treat `vector_id` as UUID.
- Do not rename `chunk_uuid` to `chunk_id`; they are different concepts.
- Do not patch mcp-proxy-adapter here.
- Do not leave help/schema metadata saying `integer` for migrated DB identities.
- Do not describe SQLite as optional, partial, or compatibility-only.
- Do not present PostgreSQL native UUID storage as the only supported backend storage.

## Tests required
1. MCP schema/help tests show ID fields as strings/UUID where appropriate.
2. `get_database_status` sample output has no migrated DB identity described as integer-only.
3. `list_project_files` returns UUID `id`/`file_id` values and UUID-shaped `project_id`/`watch_dir_id`.
4. AST/CST commands accept project/path and return UUID-backed file/entity IDs where DB identities are included.
5. Semantic search returns UUID `file_id`, UUID `chunk_id`, string `chunk_uuid`, and integer `vector_id` if present.
6. Commands that accept IDs validate UUID format and fail clearly for invalid values.
7. PostgreSQL tests prove UUID API values are stored/queried through PostgreSQL UUID typed columns.
8. SQLite tests prove UUID API values are stored/queried through canonical UUID TEXT columns without integer identity leakage.
9. Compatibility tests for any intentionally retained legacy integer fields.

## Runtime verification
After migration and restart, run on both backends:

```text
help(command=<representative command>)
get_database_status
list_project_files(project_id=<project>)
get_ast(project_id=<project>, file_path=<path>)
semantic_search(project_id=<project>, query=<query>)
list_code_entities(project_id=<project>)
get_imports(project_id=<project>)
```

Expected:
- public IDs are UUID strings;
- `project_id` and `watch_dir_id` are valid UUID strings;
- PostgreSQL backend uses PostgreSQL UUID at DB boundary;
- SQLite backend uses canonical TEXT UUID at DB boundary;
- command schemas do not claim integer ID types for migrated DB identities;
- commands still work through project/path where supported;
- diagnostic/status output does not contradict the selected backend.

## References
- `12-file-crud-and-path-identity.md`
- `13-indexing-ast-cst-entity-writes.md`
- `14-docstring-chunks-and-chunk-uuid.md`
- `15-vector-index-and-faiss-mapping.md`
- `18-test-matrix-and-runtime-verification.md`
