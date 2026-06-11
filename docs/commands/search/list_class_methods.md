# list_class_methods

**Command name:** `list_class_methods`  
**Class:** `ListClassMethodsMCPCommand`  
**Source:** `code_analysis/commands/search_mcp_commands.py`  
**Category:** search

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_class_methods command lists all methods of a specific class. It searches the database for all methods belonging to the specified class and returns their metadata including name, signature, file path, and line numbers.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Searches for class with given name
5. Retrieves all methods belonging to that class
6. Returns list of methods with metadata

Method Information:
- Method name
- Method signature (parameters, return type)
- File path where method is defined
- Line numbers (start, end)
- Class name
- Docstring (if available)

Use cases:
- Explore class API
- List all methods of a class
- Find method locations
- Understand class structure

Important notes:
- Requires built database (run update_indexes first)
- Class name must match exactly (case-sensitive)
- Returns all methods including inherited ones (if tracked)
- Methods are returned in order of appearance in file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `class_name` | string | **Yes** | Name of the class |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `class_name`: Name of the class
- `methods`: List of methods. Each contains:
- name: Method name
- signature: Method signature (parameters, return type)
- file_path: Path to file containing the method
- line_start: Starting line number
- line_end: Ending line number
- docstring: Method docstring (if available)
- class_name: Name of the class
- `count`: Number of methods found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, SEARCH_ERROR (and others).

---

## Examples

### Correct usage

**List all methods of a class**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "class_name": "MyClass"
}
```

Returns all methods of MyClass with their signatures, file paths, and line numbers.

**List methods with explicit project_id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "class_name": "DatabaseManager",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7"
}
```

Lists methods of DatabaseManager class for the specified project.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **SEARCH_ERROR**: Database error, class not found, or query error. Check database integrity, verify class name is correct, ensure database was built with update_indexes.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `SEARCH_ERROR` | General error during search | Check database integrity, verify class name is cor |

## Best practices

- Run update_indexes first to build the database
- Class name must match exactly (case-sensitive)
- Use find_classes first to discover available classes
- Empty result means class has no methods or class not found

---
