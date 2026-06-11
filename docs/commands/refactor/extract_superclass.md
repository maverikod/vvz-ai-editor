# extract_superclass

**Command name:** `extract_superclass`  
**Class:** `ExtractSuperclassMCPCommand`  
**Source:** `code_analysis/commands/refactor_mcp_commands.py`  
**Category:** refactor

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The extract_superclass command extracts common functionality from multiple classes into a new base class. Child classes inherit from the base class and keep their unique methods.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Parses config (JSON object or string)
4. Validates all child classes exist in file
5. Checks for multiple inheritance conflicts
6. If dry_run=true: generates preview without making changes
7. If dry_run=false:
   - Creates backup of original file
   - Creates new base class with extracted members
   - Updates child classes to inherit from base class
   - Makes specified methods abstract if abstract_methods provided
   - Validates Python syntax of result
   - Formats code with black
   - Returns backup UUID for restoration if needed

Configuration Requirements:
- base_class: Name of new base class to create
- child_classes: List of child class names (must exist in file)
- extract_from: Dictionary mapping each child class to its extraction config
  Each child config specifies:
  - properties: List of property names to extract
  - methods: List of method names to extract
- abstract_methods: Optional list of methods to make abstract in base class
  (requires 'from abc import ABC, abstractmethod')

Result:
- New base class is created with extracted properties and methods
- Child classes inherit from base class
- Abstract methods (if specified) are marked with @abstractmethod
- Original formatting, comments, and docstrings are preserved

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Path to Python file (relative to project root) |
| `config` | object | **Yes** | Extraction configuration object. Structure: {   'base_class': str (required) - Name of new base class to create,   'child_classes': list[str] (required) - List of child class names to extract from,    |
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
- `preview`: Preview code (only if dry_run=true). Shows how the file will look after extraction.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, EXTRACT_SUPERCLASS_PREVIEW_ERROR, EXTRACT_SUPERCLASS_ERROR (and others).

---

## Examples

### Correct usage

**Preview extraction before applying (recommended first step)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models/animals.py",
  "config": {
    "base_class": "Animal",
    "child_classes": [
      "Dog",
      "Cat"
    ],
    "abstract_methods": [
      "make_sound"
    ],
    "extract_from": {
      "Dog": {
        "properties": [
          "name",
          "legs"
        ],
        "methods": [
          "move",
          "eat"
        ]
      },
      "Cat": {
        "properties": [
          "name",
          "legs"
        ],
        "methods": [
          "move",
          "eat"
        ]
      }
    }
  },
  "dry_run": true
}
```

Validates configuration and returns preview code without making changes. Review the preview to ensure extraction is correct before applying.

**Extract common functionality into base class**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models/animals.py",
  "config": {
    "base_class": "Animal",
    "child_classes": [
      "Dog",
      "Cat"
    ],
    "abstract_methods": [
      "make_sound"
    ],
    "extract_from": {
      "Dog": {
        "properties": [
          "name",
          "legs"
        ],
        "methods": [
          "move",
          "eat"
        ]
      },
      "Cat": {
        "properties": [
          "name",
          "legs"
        ],
        "methods": [
          "move",
          "eat"
        ]
      }
    }
  },
  "dry_run": false
}
```

Performs actual extraction. Creates backup automatically. Returns backup_uuid for restoration if needed.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Run update_indexes or ensure project is registered in database

- **FILE_NOT_FOUND**: file_path='nonexistent.py'. Provide valid file path relative to root_dir or absolute path

- **EXTRACT_SUPERCLASS_PREVIEW_ERROR**: Error: Child class 'NonExistentClass' not found
Error: Multiple inheritance conflict: Dog already inherits from Pet. Use list_cst_blocks command to discover all classes and their structure. Ensure all child classes exist. Check for existing inheritance relationships.

- **EXTRACT_SUPERCLASS_ERROR**: Syntax error in generated code, validation failed. Check error message for details. Backup was created - use restore_backup_file if needed. Review configuration and try again with dry_run=true first.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database for given root_dir | Run update_indexes or ensure project is registered |
| `FILE_NOT_FOUND` | File path doesn't exist or is not accessible | Provide valid file path relative to root_dir or ab |
| `EXTRACT_SUPERCLASS_PREVIEW_ERROR` | Configuration validation failed. Common causes:
- Child clas | Use list_cst_blocks command to discover all classe |
| `EXTRACT_SUPERCLASS_ERROR` | Extraction operation failed during execution | Check error message for details. Backup was create |

## Best practices

- Always use dry_run=true first to preview changes
- Use list_cst_blocks command to discover class structure before creating config
- Ensure common methods/properties have identical signatures across child classes
- Use abstract_methods for methods that differ in implementation
- Test extraction result with dry_run before applying
- Save backup_uuid for easy restoration if needed

---
