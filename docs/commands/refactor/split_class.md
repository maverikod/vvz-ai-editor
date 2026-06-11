# split_class

**Command name:** `split_class`  
**Class:** `SplitClassMCPCommand`  
**Source:** `code_analysis/commands/refactor_mcp_commands.py`  
**Category:** refactor

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The split_class command splits a large class into multiple smaller classes while maintaining functionality. The original class becomes a facade that delegates to the new classes.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Parses config (JSON object or string)
4. Validates that ALL properties and methods from src_class are distributed
5. If dry_run=true: generates preview without making changes
6. If dry_run=false:
   - Creates backup of original file
   - Splits class according to config
   - Validates Python syntax of result
   - Validates completeness (all members present)
   - Formats code with black
   - Returns backup UUID for restoration if needed

Configuration Requirements:
- src_class: Name of the class to split (must exist in file)
- dst_classes: Dictionary mapping new class names to their configurations
  Each destination class must specify:
  - props: List of property names (instance attributes from __init__)
  - methods: List of method names to move to this class
- CRITICAL: ALL properties and ALL methods (except __init__, __new__, __del__) must be distributed across dst_classes
- Special methods (__init__, __new__, __del__) remain in the original class

Result:
- Original class becomes a facade with instances of new classes
- Methods in original class delegate to corresponding new class instances
- New classes are created with their assigned properties and methods
- Original formatting, comments, and docstrings are preserved

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Path to Python file (relative to project root) |
| `config` | object | **Yes** | Split configuration object. Structure: {   'src_class': str (required) - Name of source class to split,   'dst_classes': dict (required) - Dictionary mapping new class names to their configs.     Each |
| `dry_run` | boolean | No | If true, preview changes without applying them Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True if operation succeeded
- `message`: Human-readable success message
- `backup_uuid`: UUID of created backup (if dry_run=false). Use this with restore_backup_file command to restore original file.
- `preview`: Preview code (only if dry_run=true). Shows how the file will look after split.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, SPLIT_CLASS_PREVIEW_ERROR, SPLIT_CLASS_ERROR (and others).

---

## Examples

### Correct usage

**Preview split before applying (recommended first step)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models/user_manager.py",
  "config": {
    "src_class": "UserManager",
    "dst_classes": {
      "UserAuth": {
        "props": [
          "username",
          "password"
        ],
        "methods": [
          "authenticate"
        ]
      },
      "UserEmail": {
        "props": [
          "email"
        ],
        "methods": [
          "send_email"
        ]
      }
    }
  },
  "dry_run": true
}
```

Validates configuration and returns preview code without making changes. Review the preview to ensure split is correct before applying.

**Split class into multiple classes**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models/user_manager.py",
  "config": {
    "src_class": "UserManager",
    "dst_classes": {
      "UserAuth": {
        "props": [
          "username",
          "password"
        ],
        "methods": [
          "authenticate"
        ]
      },
      "UserEmail": {
        "props": [
          "email"
        ],
        "methods": [
          "send_email"
        ]
      }
    }
  },
  "dry_run": false
}
```

Performs actual split. Creates backup automatically. Returns backup_uuid for restoration if needed.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Run update_indexes or ensure project is registered in database

- **FILE_NOT_FOUND**: file_path='nonexistent.py'. Provide valid file path relative to root_dir or absolute path

- **SPLIT_CLASS_PREVIEW_ERROR**: Error: Missing properties in split config: {'logger', 'config'}
Missing methods in split config: {'run_server', 'create_app'}. Use list_cst_blocks command to discover all properties and methods. Ensure ALL properties and methods (except __init__, __new__, __del__) are distributed across dst_classes in config.

- **SPLIT_CLASS_ERROR**: Syntax error in generated code, validation failed. Check error message for details. Backup was created - use restore_backup_file if needed. Review configuration and try again with dry_run=true first.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database for given root_dir | Run update_indexes or ensure project is registered |
| `FILE_NOT_FOUND` | File path doesn't exist or is not accessible | Provide valid file path relative to root_dir or ab |
| `SPLIT_CLASS_PREVIEW_ERROR` | Configuration validation failed. Common causes:
- Missing pr | Use list_cst_blocks command to discover all proper |
| `SPLIT_CLASS_ERROR` | Split operation failed during execution | Check error message for details. Backup was create |

## Best practices

- Always use dry_run=true first to preview changes
- Use list_cst_blocks command to discover class structure before creating config
- Ensure ALL properties and methods are distributed (validation is strict)
- Keep related functionality together in destination classes
- Test split result with dry_run before applying
- Save backup_uuid for easy restoration if needed

---
