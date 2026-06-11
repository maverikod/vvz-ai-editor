# get_ast

**Command name:** `get_ast`  
**Class:** `GetASTMCPCommand`  
**Source:** `code_analysis/commands/ast/get_ast.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_ast command retrieves the stored Abstract Syntax Tree (AST) for a Python file from the analysis database. The AST is stored as JSON and represents the complete syntactic structure of the Python code.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Normalizes file_path (converts absolute to relative if possible)
5. Attempts multiple path matching strategies:
   - Exact path match
   - Versioned path pattern (data/versions/{uuid}/...)
   - Filename match (if path contains /)
6. Retrieves AST tree from database for the file
7. If include_json=true, parses and includes full AST JSON
8. Returns file metadata and optionally AST JSON

Path Resolution:
The command tries multiple strategies to find the file:
1. Exact path match against database
2. Versioned path pattern matching (for files in versioned storage)
3. Filename matching (if multiple matches, prefers path structure match)

Use cases:
- Retrieve AST for code analysis
- Inspect code structure programmatically
- Build tools that work with AST
- Verify AST data exists for a file
- Extract code structure information

Important notes:
- AST must be stored in database (created during file analysis)
- AST JSON can be large for big files
- Set include_json=false to get metadata only
- Path resolution is flexible to handle versioned files

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `file_path` | string | **Yes** | Path to Python file (relative to project root) |
| `include_json` | boolean | No | Include full AST JSON in response Default: `true`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `file_path`: File path (normalized)
- `file_id`: Database ID of file
- `ast`: Full AST JSON (if include_json=true). AST structure follows Python AST module format with node types, line numbers, and code structure.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, AST_NOT_FOUND, GET_AST_ERROR (and others).

---

## Examples

### Correct usage

**Get AST with JSON for a file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py",
  "include_json": true
}
```

Retrieves full AST JSON for src/main.py. Use for detailed AST analysis.

**Check if AST exists without retrieving JSON**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py",
  "include_json": false
}
```

Checks if AST exists for file without retrieving large JSON. Useful for verification before detailed analysis.

**Get AST using absolute path**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "/home/user/projects/my_project/src/main.py"
}
```

Uses absolute path. Command will normalize to relative path if possible.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FILE_NOT_FOUND**: file_path='src/main.py' but file not in database. Ensure file exists and has been indexed. Check file path is correct. Run update_indexes to index files.

- **AST_NOT_FOUND**: File exists in database but has no AST tree. File may not have been analyzed yet. Run update_indexes or analyze_file to create AST for the file.

- **GET_AST_ERROR**: Database error, JSON parsing error, or corrupted data. Check database integrity, verify file_path parameter, ensure AST data is valid. Try repair_sqlite_database if database is corrupted.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FILE_NOT_FOUND` | File not found in database | Ensure file exists and has been indexed. Check fil |
| `AST_NOT_FOUND` | AST not found for file | File may not have been analyzed yet. Run update_in |
| `GET_AST_ERROR` | General error during AST retrieval | Check database integrity, verify file_path paramet |

## Best practices

- Set include_json=false for large files to reduce response size
- Use this command to verify AST exists before AST-dependent operations
- AST JSON follows Python AST module structure for compatibility
- Path resolution is flexible - use relative paths when possible
- Combine with other AST commands for comprehensive code analysis

---
