# list_cst_blocks

**Command name:** `list_cst_blocks`  
**Class:** `ListCSTBlocksCommand`  
**Source:** `code_analysis/commands/list_cst_blocks_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_cst_blocks command lists logical blocks (functions, classes, methods) in a Python file with stable IDs and exact line ranges. These blocks can be used with cst_modify_tree for safe refactoring operations.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Validates file is a .py file
4. Validates file exists
5. Reads file source code
6. Parses source using LibCST
7. Extracts logical blocks (functions, classes, methods)
8. Generates stable block IDs for each block
9. Returns list of blocks with metadata

Logical Blocks:
- Top-level functions: Functions defined at module level
- Top-level classes: Classes defined at module level
- Class methods: Methods defined inside classes (qualified name: ClassName.method)
- Blocks are identified by their logical structure, not just syntax

Block ID Format:
- Format: `kind:qualname:start_line-end_line`
- Example: `function:process_data:10-25`
- Example: `class:MyClass:30-100`
- Example: `method:MyClass.process:45-60`
- Stable enough for edit workflows (if code moves, refresh via list_cst_blocks)

Block Information:
- id: Stable block identifier (use with cst_modify_tree)
- kind: Block type (function, class, method)
- qualname: Qualified name (function name, class name, or ClassName.method)
- start_line: Starting line number (1-based)
- end_line: Ending line number (1-based, inclusive)

Use cases:
- Discover code structure before refactoring
- Get stable IDs for cst_modify_tree operations
- Find functions, classes, and methods in a file
- Understand file organization
- Prepare for safe code modifications

Typical Workflow:
1. Run list_cst_blocks to discover blocks
2. Pick block_id from results
3. Use cst_modify_tree with selector kind='block_id'
4. Preview diff and compile result
5. Apply changes if satisfied

Important notes:
- Only lists logical blocks (functions, classes, methods)
- Block IDs are stable but refresh if code structure changes
- Line numbers are 1-based and inclusive
- Methods are listed with qualified names (ClassName.method)
- Nested functions/classes inside methods are not listed separately
- Use query_cst for more granular node discovery

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `file_path`: Path to analyzed file
- `blocks`: List of block dictionaries. Each contains:
- id: Stable block identifier (use with cst_modify_tree)
- kind: Block type (function, class, method)
- qualname: Qualified name
- start_line: Starting line number (1-based)
- end_line: Ending line number (1-based, inclusive)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_FILE, FILE_NOT_FOUND, CST_LIST_ERROR (and others).

---

## Examples

### Correct usage

**List blocks in a Python file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Lists all logical blocks (functions, classes, methods) in main.py with stable IDs and line ranges.

**Discover file structure before refactoring**
```json
{
  "root_dir": ".",
  "file_path": "code_analysis/core/backup_manager.py"
}
```

Lists blocks to understand file structure before using cst_modify_tree.

### Incorrect usage

- **INVALID_FILE**: File is not a Python file. Ensure file_path points to a .py file

- **FILE_NOT_FOUND**: File does not exist. Verify file_path is correct and file exists

- **CST_LIST_ERROR**: Error during block listing. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_FILE` | File is not a Python file | Ensure file_path points to a .py file |
| `FILE_NOT_FOUND` | File does not exist | Verify file_path is correct and file exists |
| `CST_LIST_ERROR` | Error during block listing |  |

## Best practices

- Use list_cst_blocks before cst_modify_tree to discover blocks
- Save block IDs for use in cst_modify_tree operations
- Refresh block list if file structure changes significantly
- Use block IDs with cst_modify_tree selector kind='block_id'
- Check start_line and end_line to understand block boundaries
- Use qualname to identify specific methods (ClassName.method)
- Combine with query_cst for more granular node discovery
- Use this as first step in refactoring workflow

---
