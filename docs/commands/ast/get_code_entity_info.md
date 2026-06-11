# get_code_entity_info

**Command name:** `get_code_entity_info`  
**Class:** `GetCodeEntityInfoMCPCommand`  
**Source:** `code_analysis/commands/ast/entity_info.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_code_entity_info command retrieves detailed information about a code entity (class, function, or method) from the analysis database. It returns complete metadata including location, docstrings, signatures, and other attributes.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Based on entity_type, queries appropriate table:
   - 'class': Queries classes table
   - 'function': Queries functions table
   - 'method': Queries methods table (with class join)
5. Filters by entity_name (required)
6. If file_path provided, filters to that file
7. If line provided, filters to that line number (for disambiguation)
8. Returns all matching entities with full metadata

Entity Types:
- class: Returns class information including bases, docstring, file location
- function: Returns function information including parameters, docstring, file location
- method: Returns method information including class context, parameters, docstring

Use cases:
- Get detailed information about a specific entity
- Inspect entity signatures and docstrings
- Find entity location (file and line)
- Disambiguate entities with same name
- Code navigation and documentation

Important notes:
- Returns all matching entities (may be multiple if same name in different files)
- Use file_path and line parameters to disambiguate
- For methods, includes class_name in results
- Returns full database record with all available fields

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `entity_type` | string | **Yes** | Type of entity: 'class', 'function', or 'method' |
| `entity_name` | string | **Yes** | Name of the entity |
| `file_path` | string | No | Optional file path to search in (relative to project root) |
| `line` | integer | No | Optional line number for disambiguation |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `entity_type`: Entity type that was searched
- `entity_name`: Entity name that was searched
- `entities`: List of entity dictionaries from database. Each contains:
- For classes: name, file_path, line, bases, docstring, and other class fields
- For functions: name, file_path, line, parameters, docstring, and other function fields
- For methods: name, class_name, file_path, line, parameters, docstring, and other method fields
- All database fields are included
- `count`: Number of matching entities found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, INVALID_ENTITY_TYPE, ENTITY_NOT_FOUND, GET_ENTITY_INFO_ERROR (and others).

---

## Examples

### Correct usage

**Get information about a class**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "class",
  "entity_name": "DataProcessor"
}
```

Retrieves detailed information about DataProcessor class, including location, bases, docstring, and other attributes.

**Get information about a function**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "function",
  "entity_name": "process_data"
}
```

Retrieves detailed information about process_data function, including parameters, docstring, and file location.

**Get method information with file filter**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "method",
  "entity_name": "execute",
  "file_path": "src/handlers.py"
}
```

Retrieves execute method information from src/handlers.py file only. Useful when multiple classes have methods with same name.

**Disambiguate with line number**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_type": "function",
  "entity_name": "helper",
  "file_path": "src/utils.py",
  "line": 42
}
```

Retrieves helper function at line 42 in src/utils.py. Useful when file has multiple functions with same name.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **INVALID_ENTITY_TYPE**: entity_type='invalid' (not class/function/method). Use one of: 'class', 'function', 'method'

- **ENTITY_NOT_FOUND**: entity_name='NonExistent' but entity doesn't exist. Verify entity name is correct (case-sensitive). Check that entity exists and has been indexed. Run update_indexes to index entities.

- **GET_ENTITY_INFO_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `INVALID_ENTITY_TYPE` | Invalid entity_type parameter | Use one of: 'class', 'function', 'method' |
| `ENTITY_NOT_FOUND` | Entity not found in database | Verify entity name is correct (case-sensitive). Ch |
| `GET_ENTITY_INFO_ERROR` | General error during entity info retrieval | Check database integrity, verify parameters, ensur |

## Best practices

- Use file_path parameter to disambiguate entities with same name
- Use line parameter for precise matching when multiple entities exist
- Check count field to see if multiple matches found
- Combine with find_usages to get complete entity information
- Use for code navigation and documentation generation

---
