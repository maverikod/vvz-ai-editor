# format_code

**Command name:** `format_code`  
**Class:** `FormatCodeCommand`  
**Source:** `code_analysis/commands/code_quality_commands.py`  
**Category:** code_quality

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The format_code command formats Python code using Black, the uncompromising code formatter. It automatically reformats code to follow Black's style guide, which enforces consistent formatting across the codebase.

Operation flow:
1. Validates file_path exists and is a file
2. Reads file content from disk
3. Attempts to format using Black library API (format_str)
4. If Black library not available, falls back to subprocess execution
5. Compares formatted content with original
6. If content changed, writes formatted content back to file
7. Returns success status

Formatting Behavior:
- Black enforces consistent code style (line length, quotes, spacing, etc.)
- Default line length is 88 characters
- Code is reformatted in-place (file is modified)
- If file is already formatted, no changes are made
- Black is opinionated and makes minimal formatting decisions

Black Features:
- Automatic code formatting
- Consistent style across codebase
- Handles string quotes, line breaks, indentation
- Preserves code semantics (only formatting changes)
- Fast and reliable formatting

Use cases:
- Format code before committing
- Ensure consistent code style
- Automate code formatting in workflows
- Fix formatting issues after manual edits
- Prepare code for code review

Important notes:
- File is modified in-place (original formatting is lost)
- Black is opinionated - it makes formatting decisions automatically
- If file is already formatted, operation succeeds with no changes
- Requires Black to be installed (as library or CLI tool)
- Falls back to subprocess if library API unavailable

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | **Yes** | Path to Python file (relative to project root if project_id given, else absolute). |
| `project_id` | string | No | Optional project UUID. If provided, file_path is relative to project root and DB is updated after format. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path`: Path to formatted file
- `formatted`: Always True on success
- `message`: Human-readable success message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_NOT_FOUND, NOT_A_FILE, FORMATTING_FAILED, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Format a Python file**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py"
}
```

Formats main.py using Black. File is modified in-place if formatting changes are needed.

**Format file in current directory**
```json
{
  "file_path": "./code_analysis/commands/backup_mcp_commands.py"
}
```

Formats backup_mcp_commands.py. Relative paths are resolved from current working directory.

### Incorrect usage

- **FILE_NOT_FOUND**: file_path='/path/to/nonexistent.py'. Verify file path is correct and file exists

- **NOT_A_FILE**: file_path='/path/to/directory'. Ensure path points to a file, not a directory

- **FORMATTING_FAILED**: Black formatting failed. 

- **INTERNAL_ERROR**: Unexpected exception in formatting logic. Check logs for details, verify file permissions

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_NOT_FOUND` | File does not exist | Verify file path is correct and file exists |
| `NOT_A_FILE` | Path is not a file (e.g., directory) | Ensure path points to a file, not a directory |
| `FORMATTING_FAILED` | Black formatting failed |  |
| `INTERNAL_ERROR` | Internal error during formatting | Check logs for details, verify file permissions |

## Best practices

- Run format_code before committing code to ensure consistent style
- Use format_code after manual code edits to fix formatting
- Format code before running lint_code to avoid style-related lint errors
- If formatting fails, check for syntax errors first
- Black is opinionated - accept its formatting decisions
- Consider using format_code in pre-commit hooks
- Format code regularly to maintain consistency

---
