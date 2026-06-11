# file_structure

**Command name:** `file_structure`  
**Class:** `FileStructureCommand`  
**Source:** `code_analysis/commands/file_structure_command.py`  
**Category:** refactor

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

The file_structure command returns a hierarchical view of a Python file: top-level classes with their first-level methods, and optionally top-level functions. For each class, method, and function it returns `start_line`, `end_line`, and `line_count`. This supports refactoring (split_class, extract_superclass, split_file_to_package) by showing which classes or methods are large.

Operation flow:
1. Resolves project root from project_id
2. Resolves file_path (relative to project root)
3. Validates file is .py and exists
4. Reads and parses source with LibCST
5. Walks module body: collects top-level functions and classes
6. For each class, collects direct method definitions (first level only; no nested classes/functions)
7. Computes line_count as end_line - start_line + 1 for each item
8. Returns classes (with nested methods) and optionally functions

Use cases:
- Before split_class: see which class is large and how methods are distributed
- Before extract_superclass: see which classes share large methods
- Before split_file_to_package: see classes/functions and their sizes to assign to modules
- General: quick overview of file layout and size per class/method

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `file_path` | string | **Yes** | Path to Python file (relative to project root). Must be .py. |
| `include_functions` | boolean | No | If true (default), include top-level functions. If false, only classes and their methods. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: true
- `file_path`: Requested file path (relative to project root)
- `classes`: List of class objects. Each has:
  - `name`: class name
  - `start_line`, `end_line`: 1-based inclusive range
  - `line_count`: end_line - start_line + 1
  - `methods`: list of method objects, each with `name`, `start_line`, `end_line`, `line_count`
- `functions`: List of top-level function objects (empty if include_functions=false). Each has `name`, `start_line`, `end_line`, `line_count`.

### Error

- **Shape:** `ErrorResult` with `code`, `message`, and optional `details`.
- **Possible codes:**
  - `INVALID_FILE` — not a .py file.
  - `FILE_NOT_FOUND` — file does not exist.
  - `FILE_STRUCTURE_SYNTAX_ERROR` — file contains Python syntax errors. The message describes the error and location (e.g. "Syntax error at line 5, column 3: ..."). `details` includes `line`, `column` (1-based), and `parser_message` for the full parser output.
  - `FILE_STRUCTURE_ERROR` — other errors (e.g. file not valid UTF-8, or internal error). For encoding: message asks to save the file as UTF-8; `details` includes `error_type: "encoding"` and `reason`.

---

## Examples

### Get full file structure (classes + methods + functions)

```json
{
  "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
  "file_path": "src/core/handlers.py"
}
```

### Get only classes and methods

```json
{
  "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
  "file_path": "src/core/handlers.py",
  "include_functions": false
}
```

### Example success response

```json
{
  "data": {
    "success": true,
    "file_path": "src/core/handlers.py",
    "classes": [
      {
        "name": "UserManager",
        "start_line": 20,
        "end_line": 150,
        "line_count": 131,
        "methods": [
          {
            "name": "__init__",
            "start_line": 21,
            "end_line": 30,
            "line_count": 10
          },
          {
            "name": "authenticate",
            "start_line": 32,
            "end_line": 85,
            "line_count": 54
          }
        ]
      }
    ],
    "functions": [
      {
        "name": "create_guest_user",
        "start_line": 5,
        "end_line": 18,
        "line_count": 14
      }
    ]
  }
}
```

### Example error response (syntax error)

When the file has a syntax error, the server returns a user-friendly message and location:

```json
{
  "code": "FILE_STRUCTURE_SYNTAX_ERROR",
  "message": "Syntax error at line 5, column 3: expected one of ...",
  "details": {
    "file_path": "src/foo.py",
    "error_type": "syntax",
    "line": 5,
    "column": 3,
    "parser_message": "Syntax Error @ 5:3. ..."
  }
}
```

### Example error response (encoding)

When the file is not valid UTF-8:

```json
{
  "code": "FILE_STRUCTURE_ERROR",
  "message": "The file could not be read as UTF-8. Please save the file with UTF-8 encoding and try again.",
  "details": {
    "file_path": "src/foo.py",
    "error_type": "encoding",
    "reason": "'utf-8' codec can't decode byte 0xff in position 10: ..."
  }
}
```

---

## See also

- [list_cst_blocks](../cst/list_cst_blocks.md) — stable block IDs for editing
- [split_class](split_class.md), [extract_superclass](extract_superclass.md), [split_file_to_package](split_file_to_package.md) — refactor commands that benefit from file_structure
