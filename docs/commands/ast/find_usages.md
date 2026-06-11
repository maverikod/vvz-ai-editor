# find_usages

**Command name:** `find_usages`  
**Class:** `FindUsagesMCPCommand`  
**Source:** `code_analysis/commands/ast/usages.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The find_usages command finds all places where a method, property, class, or function is used in the project. It searches the usages table in the analysis database to locate all references to the target entity.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Builds query filtering by target_name, target_type, target_class, file_path
5. If file_path provided, limits search to that specific file
6. Applies pagination: limit and offset
7. Returns list of usages with file paths and line numbers

Search Behavior:
- Searches usages table for exact matches on target_name
- Can filter by target_type (method/property/class/function)
- Can filter by target_class for methods/properties
- Can filter by file_path to limit scope
- Results ordered by file_id and line number

Use cases:
- Find all places where a function is called
- Find all places where a class is used
- Find all places where a method is called
- Find all places where a property is accessed
- Code navigation and refactoring support
- Impact analysis before changes

Important notes:
- Results include file_id, not just file_path (use get_file_by_path to resolve)
- Supports pagination with limit and offset
- For methods, use target_class to disambiguate
- If file_path provided, searches only in that file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `target_name` | string | **Yes** | Name of target to find usages for |
| `target_type` | string | No | Type of target: 'method', 'property', 'class', 'function', or null for all |
| `target_class` | string | No | Optional class name for methods/properties |
| `file_path` | string | No | Optional file path to filter by (where usage occurs) |
| `limit` | integer | No | Optional limit on number of results |
| `offset` | integer | No | Offset for pagination Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `target_name`: Target name that was searched
- `usages`: List of usage dictionaries from database. Each contains:
- file_id: Database ID of file
- line: Line number where usage occurs
- target_name: Name of target entity
- target_type: Type of target (method/property/class/function)
- target_class: Class name if target is method/property
- Additional database fields as available
- `count`: Number of usages found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FIND_USAGES_ERROR (and others).

---

## Examples

### Correct usage

**Find all usages of a function**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "target_name": "process_data",
  "target_type": "function"
}
```

Finds all places where process_data function is called across the project.

**Find method usages with class context**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "target_name": "execute",
  "target_type": "method",
  "target_class": "TaskHandler"
}
```

Finds all calls to execute method specifically in TaskHandler class.

**Find usages in specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "target_name": "MyClass",
  "target_type": "class",
  "file_path": "src/main.py"
}
```

Finds all usages of MyClass only within src/main.py file.

**Find usages with pagination**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "target_name": "calculate",
  "limit": 100,
  "offset": 0
}
```

Finds first 100 usages of 'calculate' (any type). Use offset for next page.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FIND_USAGES_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify target_name and target_type parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FIND_USAGES_ERROR` | General error during usage search | Check database integrity, verify target_name and t |

## Best practices

- Specify target_type to narrow search and improve performance
- Use target_class parameter when searching for methods/properties to avoid false matches
- Use limit and offset for pagination when dealing with many results
- Use file_path filter to focus on specific file
- Combine with find_dependencies for comprehensive usage tracking

---
