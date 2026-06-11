# cst_create_file

**Command name:** `cst_create_file`  
**Class:** `CSTCreateFileCommand`  
**Source:** `code_analysis/commands/cst_create_file_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_create_file command creates a new Python file with a docstring and returns a tree_id. This command solves the problem of creating files from scratch, which was previously impossible without an existing file to use as a template.

Operation flow:
1. Gets project from database using project_id
2. Validates project is linked to watch directory
3. Gets watch directory path from database
4. Forms absolute path: watch_dir_path / project_name / file_path
5. Validates file is a .py file
6. Checks file doesn't already exist
7. Formats docstring as triple-quoted string (if not already formatted)
8. Creates source code with only the docstring
9. Creates CST tree from source code using create_tree_from_code
10. Saves tree to file (creates file on disk and in database)
11. Returns tree_id and node metadata

File Creation:
- File is created on disk with only the docstring
- File is added to database with full metadata
- CST tree is stored in memory with tree_id
- File can be immediately modified using cst_modify_tree

Docstring Formatting:
- Docstring is automatically formatted as triple-quoted string
- If docstring already has triple quotes, they are preserved
- Docstring becomes the only content in the file
- Example: 'CLI application' becomes '"""CLI application."""'

Node Metadata:
- Returns node metadata for all nodes in the created file
- For a file with only docstring, typically returns:
  * Module node (root)
  * SimpleStatementLine node (docstring statement)
  * Expr node (docstring expression)
  * SimpleString node (docstring value)

Use cases:
- Create new Python files from scratch
- Initialize files with proper docstring structure
- Prepare files for modification via cst_modify_tree
- Create files programmatically without templates

Important notes:
- File must not exist (command will fail if file exists)
- Docstring is required and must not be empty
- File is created with only docstring (no other code)
- Tree is stored in memory and can be modified immediately
- Use returned tree_id with cst_modify_tree to add code
- File is automatically added to database
- File path is relative to project root

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target Python file path (relative to project root). File must not exist. |
| `docstring` | string | **Yes** | File-level docstring (required). Will be automatically formatted as triple-quoted string if not already formatted. Must not be empty. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID for use with other CST commands (cst_modify_tree, cst_save_tree)
- `file_path`: Absolute path to created file
- `nodes`: List of node metadata dictionaries
- `total_nodes`: Total number of nodes in the created file

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_EXISTS, INVALID_FILE, PROJECT_NOT_FOUND, CST_CREATE_ERROR (and others).

---

## Examples

### Correct usage

**Create file with simple docstring**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "docstring": "CLI application for working with data."
}
```

Creates a new file src/main.py with only a docstring. Docstring is automatically formatted as '"""CLI application for working with data."""'. Returns tree_id that can be used with cst_modify_tree to add code. Absolute path is formed as: watch_dir_path / project_name / src/main.py.

**Create file with pre-formatted docstring**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/utils.py",
  "docstring": "\"\"\"Utility functions for data processing.\"\"\""
}
```

Creates a new file with a docstring that already has triple quotes. Triple quotes are preserved as-is. File is created and ready for modification.

**Create file with multi-line docstring**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/models.py",
  "docstring": "Data models for the application.\n\nAuthor: John Doe\nemail: john@example.com"
}
```

Creates a new file with a multi-line docstring. Docstring is automatically formatted with triple quotes. Newlines are preserved in the docstring.

**Create file and immediately modify it**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "docstring": "CLI application."
}
```

Creates a new file and returns tree_id. Use the returned tree_id with cst_modify_tree to add functions, classes, or other code. Example: Use parent_node_id='node::Module:1:0-1:0' to insert code at module level.

### Incorrect usage

- **FILE_EXISTS**: File already exists. Delete existing file first or use a different file_path

- **INVALID_FILE**: File is not a Python file. Ensure file_path ends with .py extension

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct and project exists in database

- **CST_CREATE_ERROR**: Error during file creation. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_EXISTS` | File already exists | Delete existing file first or use a different file |
| `INVALID_FILE` | File is not a Python file | Ensure file_path ends with .py extension |
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct and project exists in |
| `CST_CREATE_ERROR` | Error during file creation |  |

## Best practices

- Always provide project_id - it is required and used to form absolute path
- Ensure project is linked to watch directory before using this command
- Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')
- Provide meaningful docstring that describes the file's purpose
- Save tree_id immediately for use with cst_modify_tree
- Use cst_modify_tree to add code after file creation
- File is created with only docstring - add code using cst_modify_tree
- Ensure file doesn't exist before calling this command

---
