# get_entity_dependencies

**Command name:** `get_entity_dependencies`  
**Class:** `GetEntityDependenciesMCPCommand`  
**Source:** `code_analysis/commands/ast/entity_dependencies.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_entity_dependencies command returns the list of entities that a given entity **depends on** (what it calls or uses), using the entity cross-reference table. You can call it with **entity_name + entity_type** (resolved to id in the project) or with **entity_id**; the caller does not need to know the database id when using the name.

**Operation flow:**
1. Validates root_dir exists and is a directory
2. Opens database connection via proxy
3. Resolves project_id (from parameter or inferred from root_dir)
4. If entity_name given, resolves entity_name + entity_type to entity_id in the project; if entity_id given, uses it
5. Queries entity_cross_ref table by caller_* column (class_id, method_id, or function_id)
6. Resolves file_id to file_path for each row
7. Returns list of callee entities with type, id, ref_type, file_path, line

**Data source:**
- The entity_cross_ref table is populated during update_file_data_atomic (and update_indexes) when usages are tracked. Each row links a caller entity (class/method/function) to a callee entity. ref_type can be 'call', 'instantiation', 'attribute', 'inherit'.

**Use cases:**
- Get all entities that a specific method calls (functions, other methods, classes)
- Get all entities that a function calls
- Get all entities that a class uses (e.g. instantiations, attribute access)
- Build dependency graphs by entity ID for refactoring or impact analysis
- Combine with get_entity_dependents for full call graph

**Important notes:**
- Use **entity_name + entity_type** when you have the name from code; the command resolves it to id.
- Use **entity_id** when you already have the id (e.g. from list_code_entities).
- If no dependencies are recorded (e.g. project not indexed or entity has no usages), returns empty list
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
- `dependencies`: List of dicts. Each contains:
  - `callee_entity_type`: 'class' | 'method' | 'function'
  - `callee_entity_id`: Database ID of the callee entity
  - `ref_type`: 'call' | 'instantiation' | 'attribute' | 'inherit'
  - `file_path`: Path of file where the reference occurs
  - `line`: Line number (optional)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, VALIDATION_ERROR, GET_ENTITY_DEPENDENCIES_ERROR.

---

## Examples (Примеры вызова)

### Correct usage

**Get dependencies of a function by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "function",
  "entity_id": 15
}
```
Returns all entities (functions, methods, classes) that the function with id 15 calls or uses. Use list_code_entities to get function ids.

**Get dependencies of a method by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "method",
  "entity_id": 42
}
```
Returns all entities that the method with id 42 depends on (e.g. other methods, functions, class instantiations).

**Get dependencies of a class by id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "class",
  "entity_id": 3,
  "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```
Returns all entities that the class with id 3 uses (e.g. base classes, functions called from class body). project_id is optional if project is known.

### Example success response

```json
{
  "success": true,
  "data": {
    "dependencies": [
      {
        "callee_entity_type": "function",
        "callee_entity_id": 8,
        "ref_type": "call",
        "file_path": "/home/user/projects/my_project/src/main.py",
        "line": 42
      },
      {
        "callee_entity_type": "class",
        "callee_entity_id": 2,
        "ref_type": "instantiation",
        "file_path": "/home/user/projects/my_project/src/main.py",
        "line": 45
      }
    ]
  }
}
```

### Incorrect usage / Error codes

- **PROJECT_NOT_FOUND**: root_dir points to directory but project not registered. Ensure project is registered; run update_indexes first.
- **VALIDATION_ERROR**: entity_type not one of 'class', 'method', 'function'. Use exactly one of these.
- **GET_ENTITY_DEPENDENCIES_ERROR**: Database error, proxy unavailable, or corrupted data. Check database integrity and proxy connection.

---

## Error codes summary

| Code                         | Description              | Action |
|-----------------------------|--------------------------|--------|
| `PROJECT_NOT_FOUND`         | Project not found        | Register project, run update_indexes. |
| `VALIDATION_ERROR`          | Invalid entity_type      | Use 'class', 'method', or 'function'. |
| `GET_ENTITY_DEPENDENCIES_ERROR` | General query error  | Check DB and proxy. |

---

## Best practices

- Obtain entity_id from list_code_entities or get_code_entity_info before calling.
- Use get_entity_dependents to find who depends on an entity (reverse direction).
- Run update_indexes after code changes so entity_cross_ref is up to date.
- Combine with find_dependencies (by name) for name-based discovery first.

---

## Related commands

- **get_entity_dependents** — Who depends on this entity (callers).
- **find_dependencies** — Find dependencies by entity **name** (usages/imports).
- **list_code_entities** — List entities and their IDs in file or project.
- **get_code_entity_info** — Get entity details including id by name/path.
