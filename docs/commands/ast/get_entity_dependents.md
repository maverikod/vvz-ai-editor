# get_entity_dependents

**Command name:** `get_entity_dependents`  
**Class:** `GetEntityDependentsMCPCommand`  
**Source:** `code_analysis/commands/ast/entity_dependencies.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_entity_dependents command returns the list of entities that **depend on** a given entity (what calls or uses it), using the entity cross-reference table. You can call it with **entity_name + entity_type** (resolved to id in the project) or with **entity_id**; the caller does not need to know the database id when using the name.

**Operation flow:**
1. Validates root_dir exists and is a directory
2. Opens database connection via proxy
3. Resolves project_id (from parameter or inferred from root_dir)
4. If entity_name given, resolves entity_name + entity_type to entity_id in the project; if entity_id given, uses it
5. Queries entity_cross_ref table by callee_* column (class_id, method_id, or function_id)
6. Resolves file_id to file_path for each row
7. Returns list of caller entities with type, id, ref_type, file_path, line

**Data source:**
- The entity_cross_ref table is populated during update_file_data_atomic (and update_indexes) when usages are tracked. Each row links a caller entity to a callee entity. This command returns all **callers** of the given callee.

**Use cases:**
- Find all entities that call a specific function (impact analysis)
- Find all entities that call a specific method
- Find all entities that use a specific class (instantiation, inheritance)
- Impact analysis before renaming or deleting an entity
- Combine with get_entity_dependencies for full call graph

**Important notes:**
- Use **entity_name + entity_type** when you have the name from code; the command resolves it to id.
- Use **entity_id** when you already have the id (e.g. from list_code_entities).
- If no dependents are recorded, returns empty list
- Cross-ref is built from usages; run update_indexes after code changes to refresh

---

## Arguments (Аргументы)

| Parameter    | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `root_dir`  | string | **Yes**  | Project root directory (contains data/code_analysis.db). Can be absolute or relative. |
| `entity_type` | string | **Yes**  | Type of the entity: 'class', 'method', or 'function'. Required when using entity_name. |
| `entity_id` | integer | No       | Database ID of the entity. Either entity_id or entity_name must be set. |
| `entity_name` | string | No       | Name of the entity; resolved to id within the project. Either entity_id or entity_name must be set. For methods, optionally set target_class. |
| `target_class` | string | No       | Optional class name when entity_type is 'method' and entity_name is used. |
| `project_id` | string | No       | Optional project UUID; if omitted, inferred by root_dir. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted (for proxy).

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `dependents`: List of dicts. Each contains:
  - `caller_entity_type`: 'class' | 'method' | 'function'
  - `caller_entity_id`: Database ID of the caller entity
  - `ref_type`: 'call' | 'instantiation' | 'attribute' | 'inherit'
  - `file_path`: Path of file where the reference occurs
  - `line`: Line number (optional)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, VALIDATION_ERROR, GET_ENTITY_DEPENDENTS_ERROR.

---

## Examples (Примеры вызова)

### Correct usage

**Get dependents of a function by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "function",
  "entity_id": 8
}
```
Returns all entities (functions, methods) that call the function with id 8. Use for impact analysis before changing that function.

**Get dependents of a method by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "method",
  "entity_id": 42
}
```
Returns all entities that call the method with id 42 (e.g. other methods, functions).

**Get dependents of a class by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "class",
  "entity_id": 3,
  "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```
Returns all entities that use the class with id 3 (e.g. subclasses, functions that instantiate it). project_id is optional.

### Example success response

```json
{
  "success": true,
  "data": {
    "dependents": [
      {
        "caller_entity_type": "function",
        "caller_entity_id": 15,
        "ref_type": "call",
        "file_path": "/home/user/projects/my_project/src/main.py",
        "line": 42
      },
      {
        "caller_entity_type": "method",
        "caller_entity_id": 33,
        "ref_type": "call",
        "file_path": "/home/user/projects/my_project/src/handlers.py",
        "line": 101
      }
    ]
  }
}
```

### Incorrect usage / Error codes

- **PROJECT_NOT_FOUND**: root_dir points to directory but project not registered. Ensure project is registered; run update_indexes first.
- **VALIDATION_ERROR**: entity_type not one of 'class', 'method', 'function'. Use exactly one of these.
- **GET_ENTITY_DEPENDENTS_ERROR**: Database error, proxy unavailable, or corrupted data. Check database integrity and proxy connection.

---

## Error codes summary

| Code                         | Description              | Action |
|-----------------------------|--------------------------|--------|
| `PROJECT_NOT_FOUND`         | Project not found        | Register project, run update_indexes. |
| `VALIDATION_ERROR`          | Invalid entity_type      | Use 'class', 'method', or 'function'. |
| `GET_ENTITY_DEPENDENTS_ERROR` | General query error   | Check DB and proxy. |

---

## Best practices

- Obtain entity_id from list_code_entities or get_code_entity_info before calling.
- Use get_entity_dependencies to find what an entity depends on (reverse direction).
- Run update_indexes after code changes so entity_cross_ref is up to date.
- Use for impact analysis before refactoring or deleting an entity.

---

## Related commands

- **get_entity_dependencies** — What this entity depends on (callees).
- **find_usages** — Find usages by entity **name** (usages/imports).
- **list_code_entities** — List entities and their IDs in file or project.
- **get_code_entity_info** — Get entity details including id by name/path.
