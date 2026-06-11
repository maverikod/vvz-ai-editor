# find_dependencies

**Command name:** `find_dependencies`  
**Class:** `FindDependenciesMCPCommand`  
**Source:** `code_analysis/commands/ast/dependencies.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The find_dependencies command finds where a class, function, method, or module is used (depended upon) in the project. It searches through usages and imports tables to find all locations where the entity is referenced.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Searches usages table for entity usages (if entity_type is class/function/method/null)
5. Searches imports table for module dependencies (if entity_type is module/null)
6. Applies filters: entity_name, entity_type, target_class
7. Applies pagination: limit and offset
8. Returns list of dependency locations with file paths and line numbers

Search Behavior:
- For classes/functions/methods: Searches in usages table where target_name matches
- For modules: Searches in imports table where module or name matches
- If entity_type is null, searches both usages and imports
- Results include file path, line number, and entity details

Use cases:
- Find all places where a class is instantiated or used
- Find all places where a function is called
- Find all places where a method is called
- Find all files that import a specific module
- Impact analysis before refactoring
- Dependency tracking and code navigation

Important notes:
- Results are ordered by file path and line number
- Supports pagination with limit and offset
- For methods, use target_class parameter to disambiguate
- Module search uses LIKE pattern matching for partial matches

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `entity_name` | string | **Yes** | Name of entity to find dependencies for |
| `entity_type` | string | No | Type of entity: 'class', 'function', 'method', 'module', or null for all |
| `target_class` | string | No | Optional class name for methods |
| `limit` | integer | No | Optional limit on number of results |
| `offset` | integer | No | Offset for pagination Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `entity_name`: Entity name that was searched
- `entity_type`: Entity type that was searched (or null)
- `dependencies`: List of dependency dictionaries. Each contains:
- type: 'usage' or 'import'
- file_path: File where dependency occurs
- line: Line number where dependency occurs
- For usages: target_name, target_type, target_class
- For imports: module, name, import_type
- `count`: Number of dependencies found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FIND_DEPENDENCIES_ERROR (and others).

---

## Examples

### Correct usage

**Find all usages of a class**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_name": "DataProcessor",
  "entity_type": "class"
}
```

Finds all places where DataProcessor class is used, instantiated, or referenced in the project.

**Find all calls to a function**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_name": "process_data",
  "entity_type": "function"
}
```

Finds all function calls to process_data across the project.

**Find method usages with class context**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_name": "execute",
  "entity_type": "method",
  "target_class": "TaskHandler"
}
```

Finds all calls to execute method specifically in TaskHandler class, excluding execute methods in other classes.

**Find module imports with pagination**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "entity_name": "os",
  "entity_type": "module",
  "limit": 50,
  "offset": 0
}
```

Finds first 50 files that import 'os' module. Use offset for next page.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FIND_DEPENDENCIES_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify entity_name and entity_type parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FIND_DEPENDENCIES_ERROR` | General error during dependency search | Check database integrity, verify entity_name and e |

## Best practices

- Specify entity_type to narrow search and improve performance
- Use target_class parameter when searching for methods to avoid false matches
- Use limit and offset for pagination when dealing with many results
- Use this command for impact analysis before refactoring
- Combine with find_usages for comprehensive dependency tracking

---
