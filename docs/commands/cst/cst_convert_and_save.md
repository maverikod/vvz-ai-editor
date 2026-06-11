# cst_convert_and_save

**Command name:** `cst_convert_and_save`  
**Class:** `CSTConvertAndSaveCommand`  
**Source:** `code_analysis/commands/cst_convert_and_save_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_convert_and_save command converts source code to CST tree, saves both CST and AST to database, and optionally saves code to file on disk.

Operation flow:
1. Validates source code is not empty
2. Gets project from database using project_id
3. Validates project is linked to watch directory
4. Resolves absolute file path: watch_dir_path / project_name / file_path
5. If save_to_file=True: saves code to file on disk
6. Parses source code to AST using parse_with_comments
7. Creates CST tree from source code using create_tree_from_code
8. Calculates hashes (AST JSON hash and CST source code hash)
9. Gets or creates file_id in database
10. Saves AST tree to database (ast_trees table with ast_json)
11. Saves CST tree to database (cst_trees table with cst_code)
12. Returns tree_id, file_id, ast_tree_id, cst_tree_id, and node metadata

Database Storage:
- AST trees: Stored in ast_trees table as JSON (ast_json column)
  * Format: JSON string from ast.dump(tree)
  * Hash: SHA256 of ast_json
  * Used for: Code analysis, querying, dependency tracking

- CST trees: Stored in cst_trees table as source code (cst_code column)
  * Format: Original Python source code string
  * Hash: SHA256 of source code
  * Used for: Code editing, refactoring, file restoration

Both AST and CST are saved for each file, allowing:
- Fast analysis using AST (lightweight, structured)
- Code editing using CST (preserves formatting, comments)
- File restoration from CST (full source code available)

Use cases:
- Convert code string to CST tree and save to database
- Import code from external sources
- Create files programmatically with full database integration
- Ensure both AST and CST are available for analysis and editing

Important notes:
- Both AST and CST are always saved to database (if file_id exists)
- File is created on disk only if save_to_file=True
- File must be added to database before AST/CST can be saved
- CST tree is stored in memory and can be modified immediately
- Use returned tree_id with cst_modify_tree to modify code
- AST and CST are synchronized (same source code, same file_mtime)

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target Python file path (relative to project root). Required for saving to database. |
| `source_code` | string | **Yes** | Source code to convert to CST and save. Required. |
| `save_to_file` | boolean | No | Whether to save code to file on disk. Default is True. Default: `true`. |
| `include_nodes` | boolean | No | If True, include full list of CST node metadata in response (can be large). Default False to keep response small and avoid connection/buffer issues. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: CST tree ID for use with other CST commands (cst_modify_tree, cst_save_tree)
- `file_id`: File ID in database
- `file_path`: Absolute path to file
- `ast_saved`: Always True (AST is always saved if file_id exists)
- `cst_saved`: Always True (CST is always saved if file_id exists)
- `ast_tree_id`: AST tree ID in database (ast_trees table)
- `cst_tree_id`: CST tree ID in database (cst_trees table)
- `nodes`: List of node metadata dictionaries
- `total_nodes`: Total number of nodes in CST tree

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** EMPTY_CODE, SYNTAX_ERROR, AST_SAVE_ERROR, CST_SAVE_ERROR, CST_CONVERT_ERROR (and others).

---

## Examples

### Correct usage

**Convert code and save to database and file**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "source_code": "\"\"\"CLI application.\"\"\"\n\ndef main():\n    print(\"Hello, World!\")",
  "save_to_file": true
}
```

Converts source code to CST tree, saves both AST and CST to database, and saves code to file on disk. Returns tree_id for further modifications. Absolute path is formed as: watch_dir_path / project_name / src/main.py.

**Convert code and save only to database (no file)**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/utils.py",
  "source_code": "def helper():\n    return True",
  "save_to_file": false
}
```

Converts source code to CST tree and saves both AST and CST to database, but does not create file on disk. Useful for importing code from external sources or creating database records without files.

### Incorrect usage

- **EMPTY_CODE**: Source code is empty. Provide non-empty source code

- **SYNTAX_ERROR**: Source code has syntax errors. Fix syntax errors in source code. Ensure code is valid Python.

- **AST_SAVE_ERROR**: Failed to save AST to database. Check database connection and permissions. Ensure file_id exists in database.

- **CST_SAVE_ERROR**: Failed to save CST to database. Check database connection and permissions. Ensure file_id exists in database.

- **CST_CONVERT_ERROR**: Error during conversion. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `EMPTY_CODE` | Source code is empty | Provide non-empty source code |
| `SYNTAX_ERROR` | Source code has syntax errors | Fix syntax errors in source code. Ensure code is v |
| `AST_SAVE_ERROR` | Failed to save AST to database | Check database connection and permissions. Ensure  |
| `CST_SAVE_ERROR` | Failed to save CST to database | Check database connection and permissions. Ensure  |
| `CST_CONVERT_ERROR` | Error during conversion |  |

## Best practices

- Always provide project_id - it is required and used to form absolute path
- Ensure project is linked to watch directory before using this command
- Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')
- Provide valid Python source code (will be validated during AST parsing)
- Save tree_id immediately for use with cst_modify_tree
- Both AST and CST are saved automatically - no need to call save separately
- Use save_to_file=False if you only want database records without files
- File must be added to database before AST/CST can be saved

---
