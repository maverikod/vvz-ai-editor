# get_imports

**Command name:** `get_imports`  
**Class:** `GetImportsMCPCommand`  
**Source:** `code_analysis/commands/ast/imports.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_imports command retrieves import information from files or the entire project. It returns a list of all import statements with filtering options by file, import type, and module name.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. If file_path provided:
   - Normalizes file path (absolute to relative if possible)
   - Tries multiple path matching strategies
   - Filters imports to that specific file
5. If file_path not provided, queries all imports in project
6. Applies filters: import_type, module_name (LIKE pattern)
7. Applies pagination: limit and offset
8. Returns list of imports ordered by file_id and line

Import Types:
- 'import': Standard import statements (import os)
- 'import_from': From-import statements (from os import path)

Use cases:
- List all imports in a file
- Find all files importing a specific module
- Analyze import dependencies
- Check for unused imports
- Understand module usage patterns

Important notes:
- Results ordered by file_id and line number
- Supports pagination with limit and offset
- module_name filter uses LIKE pattern matching
- Path resolution is flexible to handle versioned files

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | No | Optional file path to filter by (relative to project root) |
| `import_type` | string | No | Type of import: 'import' or 'import_from' |
| `module_name` | string | No | Optional module name to filter by |
| `limit` | integer | No | Optional limit on number of results |
| `offset` | integer | No | Offset for pagination Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `imports`: List of import dictionaries from database. Each contains:
- file_id: Database ID of file
- line: Line number where import occurs
- import_type: Type of import ('import' or 'import_from')
- module: Module name (for import_from) or null
- name: Imported name
- Additional database fields as available
- `count`: Number of imports found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, GET_IMPORTS_ERROR (and others).

---

## Examples

### Correct usage

**Get all imports in a file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Returns all import statements from src/main.py file.

**Get all imports in project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns all import statements across the entire project.

**Find all files importing a module**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "module_name": "os"
}
```

Finds all files that import 'os' module (or modules containing 'os').

**Get only import_from statements**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "import_type": "import_from"
}
```

Returns only 'from X import Y' style imports, excluding 'import X' statements.

**Get imports with pagination**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "limit": 100,
  "offset": 0
}
```

Returns first 100 imports. Use offset for next page.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FILE_NOT_FOUND**: file_path='src/main.py' but file not in database. Ensure file exists and has been indexed. Check file path is correct. Run update_indexes to index files.

- **GET_IMPORTS_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FILE_NOT_FOUND` | File not found in database | Ensure file exists and has been indexed. Check fil |
| `GET_IMPORTS_ERROR` | General error during import retrieval | Check database integrity, verify parameters, ensur |

## Best practices

- Use file_path filter to focus on specific file imports
- Use module_name filter to find module usage patterns
- Use import_type filter to separate import styles
- Use limit and offset for pagination with large result sets
- Combine with export_graph (graph_type='dependencies') for visualization

---
