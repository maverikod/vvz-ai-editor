# find_classes

**Command name:** `find_classes`  
**Class:** `FindClassesMCPCommand`  
**Source:** `code_analysis/commands/search_mcp_commands.py`  
**Category:** search

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The find_classes command searches for classes by name pattern. It can search for classes matching a specific pattern or return all classes if no pattern is provided.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Searches for classes matching the pattern (if provided)
5. If no pattern provided, returns all classes
6. Returns list of classes with metadata

Pattern Matching:
- Supports SQL LIKE pattern matching
- Use '%' for wildcard (e.g., '%Manager' matches 'DatabaseManager')
- Use '_' for single character wildcard
- Case-sensitive matching
- If pattern is None, returns all classes

Class Information:
- Class name
- File path where class is defined
- Line numbers (start, end)
- Docstring (if available)
- Base classes (if available)

Use cases:
- Find classes by name pattern
- Discover all classes in project
- Search for classes with specific naming convention
- Explore project structure

Important notes:
- Requires built database (run update_indexes first)
- Pattern uses SQL LIKE syntax
- If pattern is None, returns all classes (may be large result set)
- Results are sorted by class name

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `pattern` | string | No | Name pattern to search (optional, if not provided returns all classes) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `pattern`: Pattern that was used (or None)
- `classes`: List of classes. Each contains:
- name: Class name
- file_path: Path to file containing the class
- line_start: Starting line number
- line_end: Ending line number
- docstring: Class docstring (if available)
- base_classes: List of base classes (if available)
- `count`: Number of classes found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, SEARCH_ERROR (and others).

---

## Examples

### Correct usage

**Find all classes**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns all classes in the project. May return large result set.

**Find classes by pattern**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "pattern": "%Manager"
}
```

Returns all classes ending with 'Manager' (e.g., 'DatabaseManager', 'FileManager').

**Find classes starting with pattern**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "pattern": "Base%"
}
```

Returns all classes starting with 'Base' (e.g., 'BaseClass', 'BaseHandler').

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **SEARCH_ERROR**: Database error, pattern syntax error, or query error. Check database integrity, verify pattern syntax (SQL LIKE), ensure database was built with update_indexes.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `SEARCH_ERROR` | General error during search | Check database integrity, verify pattern syntax (S |

## Best practices

- Run update_indexes first to build the database
- Use pattern to narrow down results (avoid returning all classes)
- Pattern uses SQL LIKE syntax with '%' and '_' wildcards
- Use list_class_methods after finding a class to explore its methods
- Empty result means no classes match the pattern

---
