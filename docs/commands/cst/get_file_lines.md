# get_file_lines

**Command name:** `get_file_lines`  
**Class:** `GetFileLinesCommand`  
**Source:** `code_analysis/commands/get_file_lines_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Return raw file lines in a range **without parsing** (no LibCST). Use when the file has syntax errors and cannot be loaded as a CST tree, or when only a line range is needed (e.g. "show lines around error").

- Input: `project_id`, `file_path`, `start_line`, `end_line` (1-based, inclusive).
- Path is resolved via project (same as other CST commands).
- Response: `lines` (list of strings), `start_line`, `end_line`, `file_path`, `total_lines`.
- Missing file or invalid range (e.g. start_line > end_line) returns a clear error code.

**References:** [CST_COMMANDS_GAP_ANALYSIS.md](../../analysis/CST_COMMANDS_GAP_ANALYSIS.md) (Option A — Raw lines).

---

## Arguments

| Parameter     | Type    | Required | Description                                |
|---------------|---------|----------|--------------------------------------------|
| `project_id`  | string  | **Yes**  | Project ID (UUID4).                        |
| `file_path`   | string  | **Yes**  | File path relative to project root.       |
| `start_line`  | integer | **Yes**  | Start line (1-based, inclusive).            |
| `end_line`    | integer | **Yes**  | End line (1-based, inclusive).              |

**Schema:** `additionalProperties: false`.

---

## Returned data

### Success

- `success`: true
- `file_path`: Requested file path
- `start_line`, `end_line`: Actual range returned (clamped to file)
- `lines`: List of line strings (no newlines)
- `total_lines`: Total lines in file

### Error codes

- **INVALID_RANGE** — start_line > end_line or line numbers < 1
- **FILE_NOT_FOUND** — File does not exist at resolved path
- **VALIDATION_ERROR** — Project/path validation failed
- **GET_FILE_LINES_ERROR** — Other failure
