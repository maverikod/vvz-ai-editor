# Step 13 — Indexing, AST/CST, and entity write paths

## Goal
Update runtime indexing and entity-write paths so all DB identities are UUID-safe after the PostgreSQL-first migration.

## Architecture constraint
Runtime writes must follow the project layering:

```text
command/application code -> universal DB/driver contract -> specific driver -> specific DB
```

Application/indexing code may generate and pass UUID values through the universal contract, but it must not contain PostgreSQL-specific SQL. PostgreSQL-specific normalization, placeholders, casts, and DDL belong only in the PostgreSQL driver branch. SQLite compatibility, if implemented, belongs only in the SQLite branch.

## Current risk
Indexing currently writes rows into tables whose primary keys are integer/autoincrement in the existing schema:

```text
files
classes
methods
functions
entity_cross_ref
imports
issues
usages
code_content
ast_trees
cst_trees
```

After migration, any insert path that previously relied on integer autoincrement or `insert(...) -> int` must explicitly become UUID-safe.

## Files to inspect/edit
- `code_analysis/core/indexing/*`
- `code_analysis/core/database/entities.py`
- `code_analysis/core/database/entity_cross_ref.py`
- `code_analysis/core/database/ast.py`
- `code_analysis/core/database/cst.py`
- `code_analysis/core/database/files/update.py`
- `code_analysis/core/database_client/client_api_classes_functions.py`
- `code_analysis/core/database_client/client_api_methods_imports.py`
- `code_analysis/core/database_client/client_api_issues_usages.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_operations.py`
- `code_analysis/core/database_driver_pkg/drivers/postgres_run.py`

## Required changes

### UUID generation and insert target
Every insert into a migrated table must have a clear UUID owner:

```text
Option A: application/write path generates UUID4 and includes id in insert data.
Option B: PostgreSQL branch generates UUID with a PostgreSQL default and returns it through a UUID-safe insert contract.
```

Default for runtime write paths: Option A, unless a file-specific reason is documented.

### Entity tables
The following tables must be treated as UUID primary-key insert targets:

```text
classes.id
methods.id
functions.id
entity_cross_ref.id
imports.id
issues.id
usages.id
code_content.id
ast_trees.id
cst_trees.id
```

Do not update only `files.id`, `classes.id`, `methods.id`, and `functions.id`. `entity_cross_ref.id`, `imports.id`, `issues.id`, `usages.id`, `code_content.id`, `ast_trees.id`, and `cst_trees.id` are also migrated identities.

### Foreign-key writes
All FK writes must pass UUID values after migration:

```text
file_id
class_id
method_id
function_id
caller_class_id
caller_method_id
caller_function_id
callee_class_id
callee_method_id
callee_function_id
```

No path may preserve integer FK values after the table it references has moved to UUID.

### Polymorphic references
`code_content.entity_id` must be handled as a polymorphic reference, not as a generic integer. It must use the same chosen design decision as `vector_index.entity_id` from the schema/migration steps:

```text
Option A: entity_type + UUID entity_id
Option B: typed nullable UUID FK columns
Option C: unified entities table
```

Indexing code must not silently write old integer entity IDs into `code_content.entity_id` after entity tables are UUID.

### entity_cross_ref
`entity_cross_ref.id` itself is a migrated UUID primary key. Its caller/callee columns are migrated references and must be rewritten/generated consistently with the entity graph. Do not treat `entity_cross_ref` only as a relationship table without its own migrated identity.

## Required verification
After code changes in this step, run MCP-level checks, not only unit tests:

```text
update_indexes on a test project
list_code_entities
get_code_entity_info
get_imports
find_usages
find_dependencies
get_entity_dependencies
get_entity_dependents
```

Expected checks:
- returned IDs are UUID-shaped where DB identities are exposed;
- `imports.id`, `issues.id`, `usages.id`, and `code_content.id` are UUID PKs;
- FK fields such as `file_id`, `class_id`, `method_id`, and `function_id` are UUID-shaped;
- `entity_cross_ref.id` is UUID-shaped;
- `code_content.entity_id` follows the documented polymorphic UUID design;
- no command claims an integer DB identity for migrated tables.

## Must not do
- Do not put PostgreSQL SQL into indexing/application code.
- Do not rely on integer return values from insert after UUID migration.
- Do not update only entity table PKs while leaving relationship/log tables integer.
- Do not write integer `entity_id` into polymorphic references after migration.
- Do not parallelize runtime write-path changes with migration swap execution.

## References
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `06-schema-mid-ast-cst-chunks-vector-index.md`
- `09-migration-framework-and-id-map.md`
- `18-test-matrix-and-runtime-verification.md`
