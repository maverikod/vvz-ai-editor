# list_code_entities

**Command name:** `list_code_entities`  
**Class:** `ListCodeEntitiesMCPCommand`  
**Source:** `code_analysis/commands/ast/list_entities.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_code_entities command lists all code entities (classes, functions, methods) in a file or project. It provides a comprehensive catalog of all code entities with their locations and metadata.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Based on entity_type, queries appropriate tables:
   - If entity_type is null or 'class': Queries classes table
   - If entity_type is null or 'function': Queries functions table
   - If entity_type is null or 'method': Queries methods table (with class join)
5. If file_path provided, filters to entities in that file
6. Applies pagination: limit and offset
7. Combines results from all entity types (if entity_type is null)
8. Returns list of entities with type indicator

Entity Types:
- 'class': Lists all classes with name, file_path, line, bases, docstring
- 'function': Lists all functions with name, file_path, line, parameters, docstring
- 'method': Lists all methods with name, class_name, file_path, line, parameters, docstring
- null: Lists all entity types combined

Use cases:
- Get catalog of all classes in project
- List all functions in a file
- Find all methods in a class
- Generate code documentation
- Analyze code structure

Important notes:
- If entity_type is null, returns all types combined
- Each entity includes 'type' field indicating its type
- Results ordered by file_path and line number
- Supports pagination with limit and offset

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `entity_type` | string | No | Type of entity: 'class', 'function', 'method', or null for all |
| `file_path` | string | No | Optional file path to filter by (relative to project root) |
| `limit` | integer | No | Optional limit on number of results |
| `offset` | integer | No | Offset for pagination Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `entities`: List of entity dictionaries. Each entity includes:
- type: Entity type ('class', 'function', or 'method')
- For classes: name, file_path, line, bases, docstring, and other class fields
- For functions: name, file_path, line, parameters, docstring, and other function fields
- For methods: name, class_name, file_path, line, parameters, docstring, and other method fields
- All database fields are included
- `count`: Number of entities found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, LIST_ENTITIES_ERROR (and others).

---

## Examples

### Correct usage

**List all classes in project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "class"
}
```

Returns list of all classes in the project with their locations and metadata.

**List all entities in a file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Returns all classes, functions, and methods defined in src/main.py.

**List all functions in project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "function"
}
```

Returns list of all functions in the project.

**List entities with pagination**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "method",
  "limit": 50,
  "offset": 0
}
```

Returns first 50 methods. Use offset for next page.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **LIST_ENTITIES_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `LIST_ENTITIES_ERROR` | General error during entity listing | Check database integrity, verify parameters, ensur |

## Best practices

- Use entity_type to filter specific entity types for better performance
- Use file_path filter to focus on specific file
- Use limit and offset for pagination with large result sets
- Check 'type' field in results when entity_type is null
- Combine with get_code_entity_info for detailed entity information

---
