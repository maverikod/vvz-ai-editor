# write_project_text_lines

> **Obsolete for MCP editing.** Use [universal_file_edit](../file_editing/universal_file_edit.md) in an edit session.  
> This command remains for legacy line-replace on **non-code** plain text only.

**Command name:** `write_project_text_lines`  
**Class:** `WriteProjectTextLinesCommand`  
**Source:** `code_analysis/commands/write_project_text_lines_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Write policy (non-code vs Python vs other source)

**Non-code plain text** — documentation, configs, etc.: replace lines in place with optional backup and DB update.

**Python / Python-ecosystem paths** (`.py`, `.pyi`, …): **`PYTHON_FILE_FORBIDDEN`** — use the [universal edit session](../file_editing/WORKFLOW.md); do not use this command for Python sources.

**Other blocked program-source suffixes:** `CODE_FILE_FORBIDDEN` (see `project_text_file_guard.py`).

The suffix check runs **before** range validation and filesystem / backup / DB work.

---

## Purpose

Replace a contiguous **1-based inclusive** line range. For non-code files: optional backup and DB update. Python and other blocked source paths are rejected (see above).

- `new_lines`: array of strings, one logical line each (no `\n` inside items); file content is rebuilt with `\n` join.
- Empty file: returns `EMPTY_FILE` (nothing to replace).

**Schema / metadata:** root-level `title`, `description`, and `examples` in `get_schema()`; optional `metadata()` on the command class for discovery (`detailed_description`, `usage_examples`, `error_codes`); `additionalProperties: false` on params.

---

## Arguments

| Parameter     | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `project_id`  | string  | **Yes**  | Project UUID. |
| `file_path`   | string  | **Yes**  | Path relative to project root. Python and other blocked source suffixes → error. |
| `start_line`  | integer | **Yes**  | Start line (1-based, inclusive), ≥ 1. |
| `end_line`    | integer | **Yes**  | End line (1-based, inclusive), ≥ 1; must be ≥ `start_line`. |
| `new_lines`   | array of string | **Yes** | Replacement lines for that range. |
| `backup`      | boolean | No       | Default `true`: backup before write. |

---

## Returned data (success)

- `success`, `file_path`, `file_id`, `backup_uuid`, range info, `update_result`, etc.

## Error codes (examples)

- `PYTHON_FILE_FORBIDDEN` — Python source paths  
- `CODE_FILE_FORBIDDEN` — other blocked program source paths  
- `INVALID_RANGE`, `FILE_NOT_FOUND`, `EMPTY_FILE`, `BACKUP_REQUIRED`, `UPDATE_FILE_DATA_ERROR`  

See command implementation and `project_text_file_guard.py` for full codes and `details`.
