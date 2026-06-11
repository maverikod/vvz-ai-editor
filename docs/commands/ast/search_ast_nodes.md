# search_ast_nodes

**Command name:** `search_ast_nodes`  
**Class:** `SearchASTNodesMCPCommand`  
**Source:** `code_analysis/commands/ast/search_nodes.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The search_ast_nodes command searches for AST nodes by type across project files. It maps AST node types to database tables (classes, functions, methods) and returns matching nodes with their locations and metadata.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Based on node_type, queries appropriate tables:
   - 'ClassDef' or 'class': Searches classes table
   - 'FunctionDef' or 'function': Searches functions table
   - 'method': Searches methods table
   - If node_type is null, searches all types
5. If file_path provided, filters to nodes in that file
6. Applies limit (default 100)
7. Returns list of matching nodes with type, name, location, docstring

Node Type Mapping:
- 'ClassDef' or 'class': Maps to classes table
- 'FunctionDef' or 'function': Maps to functions table
- 'method': Maps to methods table
- null: Searches all node types

Use cases:
- Find all classes in project
- Find all functions in a file
- Find all methods in project
- Search for specific AST node types
- Analyze code structure by node type

Important notes:
- Maps AST node types to database tables (not full AST traversal)
- For full AST traversal, use get_ast and parse JSON
- Default limit is 100 to prevent large result sets
- Results include node_type, name, file_path, line, docstring

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `node_type` | string | No | AST node type to search (e.g., ClassDef, FunctionDef) |
| `file_path` | string | No | Optional file path to limit search (relative to project root) |
| `limit` | integer | No | Maximum results Default: `100`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `node_type`: Node type that was searched (or null if all types)
- `nodes`: List of node dictionaries. Each contains:
- node_type: AST node type ('ClassDef' or 'FunctionDef')
- name: Node name (class/function/method name)
- file_path: File where node is defined
- line: Line number where node is defined
- docstring: Node docstring (if available)
- class_name: Class name (for methods only)
- `count`: Number of nodes found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, SEARCH_AST_ERROR (and others).

---

## Examples

### Correct usage

**Find all classes in project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "node_type": "ClassDef"
}
```

Returns all classes in the project with their locations and metadata.

**Find all functions in a file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "node_type": "FunctionDef",
  "file_path": "src/main.py"
}
```

Returns all functions defined in src/main.py file.

**Find all methods in project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "node_type": "method",
  "limit": 200
}
```

Returns up to 200 methods in the project.

**Find all node types**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "limit": 500
}
```

Returns up to 500 nodes of all types (classes, functions, methods) combined.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **SEARCH_AST_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `SEARCH_AST_ERROR` | General error during AST node search | Check database integrity, verify parameters, ensur |

## Best practices

- Use node_type to filter specific node types for better performance
- Use file_path filter to focus on specific file
- Set appropriate limit to prevent large result sets
- Note: This searches database tables, not full AST. Use get_ast for full AST traversal
- Combine with list_code_entities for comprehensive entity listing

---
