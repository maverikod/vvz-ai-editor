# split_file_to_package

**Command name:** `split_file_to_package`  
**Class:** `SplitFileToPackageMCPCommand`  
**Source:** `code_analysis/commands/refactor_mcp_commands.py`  
**Category:** refactor

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The split_file_to_package command splits a large Python file into a package with multiple modules. The original file is replaced by a package directory containing __init__.py and module files.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Parses config (JSON object or string)
4. Validates file can be parsed as Python AST
5. Creates package directory (file_stem/)
6. Creates __init__.py in package directory
7. For each module in config:
   - Creates module_name.py file
   - Extracts specified classes and functions from original file
   - Preserves imports, docstrings, and formatting
8. Creates backup of original file
9. Returns backup UUID and list of created modules

Configuration Requirements:
- modules: Dictionary mapping module names to their configurations
  Each module must specify:
  - classes: List of class names to include (must exist in file)
  - functions: List of function names to include (must exist in file)
- Module names become Python module files (module_name.py)
- Package directory is created as file_stem/ (e.g., task_queue/ for task_queue.py)

Result:
- Original file is replaced by package directory
- Package contains __init__.py and module files
- Each module contains its assigned classes and functions
- Imports are preserved in each module
- Original formatting, comments, and docstrings are preserved

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Path to Python file (relative to project root) |
| `config` | object | **Yes** | File-to-package split configuration object. Structure: {   'modules': dict (required) - Dictionary mapping module names to their configs.     Each module config has:       'classes': list[str] - List  |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True if operation succeeded
- `message`: Human-readable success message with package path
- `backup_uuid`: UUID of created backup. Use this with restore_backup_file command to restore original file.
- `package_path`: Path to created package directory
- `modules`: List of created module names

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, SPLIT_FILE_TO_PACKAGE_ERROR (and others).

---

## Examples

### Correct usage

**Split large file into package by functionality**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/core/task_queue.py",
  "config": {
    "modules": {
      "ftp_executor": {
        "classes": [
          "FTPExecutor"
        ],
        "functions": [
          "create_ftp_connection"
        ]
      },
      "docker_executor": {
        "classes": [
          "DockerExecutor"
        ],
        "functions": []
      }
    }
  }
}
```

Splits task_queue.py into task_queue/ package with ftp_executor.py and docker_executor.py modules. Creates backup automatically.

**Split file by entity type (models vs utils)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models.py",
  "config": {
    "modules": {
      "models": {
        "classes": [
          "User",
          "Product",
          "Order"
        ],
        "functions": []
      },
      "utils": {
        "classes": [],
        "functions": [
          "validate_email",
          "format_date"
        ]
      }
    }
  }
}
```

Splits models.py into models/ package with models.py (classes) and utils.py (functions) modules.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Run update_indexes or ensure project is registered in database

- **FILE_NOT_FOUND**: file_path='nonexistent.py'. Provide valid file path relative to root_dir or absolute path

- **SPLIT_FILE_TO_PACKAGE_ERROR**: Error: Failed to parse file AST
Error: Class 'NonExistentClass' not found
Error: No modules specified in config. Use list_cst_blocks command to discover all classes and functions. Ensure file has valid Python syntax. Check that all specified classes/functions exist in the file.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database for given root_dir | Run update_indexes or ensure project is registered |
| `FILE_NOT_FOUND` | File path doesn't exist or is not accessible | Provide valid file path relative to root_dir or ab |
| `SPLIT_FILE_TO_PACKAGE_ERROR` | Split operation failed. Common causes:
- Failed to parse fil | Use list_cst_blocks command to discover all classe |

## Best practices

- Use list_cst_blocks command to discover file structure before creating config
- Group related classes and functions together in modules
- Ensure all classes and functions are distributed across modules
- Keep module names descriptive and follow Python naming conventions
- Test imports after split to ensure package structure is correct
- Save backup_uuid for easy restoration if needed

---
