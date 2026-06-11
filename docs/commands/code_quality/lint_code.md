# lint_code

**Command name:** `lint_code`  
**Class:** `LintCodeCommand`  
**Source:** `code_analysis/commands/code_quality_commands.py`  
**Category:** code_quality

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The lint_code command lints Python code using Flake8, a tool that checks code style, programming errors, and complexity. It identifies issues like unused imports, undefined variables, style violations, and more.

Operation flow:
1. Validates file_path exists and is a file
2. Attempts to lint using Flake8 library API
3. If Flake8 library not available or fails, falls back to subprocess
4. Collects all linting errors and warnings
5. Returns success status and list of errors

Linting Behavior:
- Checks code style (PEP 8 compliance)
- Detects programming errors (undefined names, unused imports, etc.)
- Checks code complexity
- Default max line length is 88 characters
- Can ignore specific error codes via ignore parameter
- File is not modified (read-only analysis)

Flake8 Error Categories:
- E: PEP 8 errors (indentation, whitespace, etc.)
- W: PEP 8 warnings (line length, etc.)
- F: Pyflakes errors (undefined names, unused imports, etc.)
- C: McCabe complexity warnings
- N: Naming convention violations

Use cases:
- Check code quality before committing
- Find programming errors (undefined variables, unused imports)
- Enforce code style standards
- Identify code complexity issues
- Validate code in CI/CD pipelines

Important notes:
- File is not modified (linting is read-only)
- Returns list of all errors found
- success=True means no errors found
- success=False means errors were found (check errors list)
- Can ignore specific error codes if needed
- Requires Flake8 to be installed
- PYTHONPATH is sanitized to avoid import conflicts

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | **Yes** | Path to Python file to lint. If project_id is provided, relative to project root. |
| `project_id` | string | No | Optional project UUID. If provided, file_path is relative to project root. |
| `ignore` | array | No | List of flake8 error codes to ignore. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path`: Path to linted file
- `success`: True if no errors found, False if errors found
- `error`: Error message if linting failed (None if successful)
- `errors`: List of error strings. Each error follows format: file_path:line:column: error_code error_message
- `error_count`: Number of errors found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_NOT_FOUND, NOT_A_FILE, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Lint a Python file**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py"
}
```

Lints main.py and returns all errors found. Check success field and errors list in response.

**Lint with ignored error codes**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py",
  "ignore": [
    "E501",
    "W503"
  ]
}
```

Lints main.py but ignores line length (E501) and line break before operator (W503) errors.

**Check code quality before commit**
```json
{
  "file_path": "./code_analysis/commands/backup_mcp_commands.py"
}
```

Lints backup_mcp_commands.py to find any code quality issues before committing changes.

### Incorrect usage

- **FILE_NOT_FOUND**: file_path='/path/to/nonexistent.py'. Verify file path is correct and file exists

- **NOT_A_FILE**: file_path='/path/to/directory'. Ensure path points to a file, not a directory

- **INTERNAL_ERROR**: Unexpected exception in linting logic. Check logs for details, verify file permissions

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_NOT_FOUND` | File does not exist | Verify file path is correct and file exists |
| `NOT_A_FILE` | Path is not a file (e.g., directory) | Ensure path points to a file, not a directory |
| `INTERNAL_ERROR` | Internal error during linting | Check logs for details, verify file permissions |

## Best practices

- Run lint_code after format_code to check for remaining issues
- Fix all errors before committing code
- Use ignore parameter sparingly - only for legitimate cases
- Check error_count field to quickly see if issues exist
- Review errors list to understand what needs fixing
- Run lint_code in CI/CD pipelines to enforce code quality
- Address F errors (Pyflakes) first - they indicate real bugs
- Use ignore for style preferences, not for hiding real issues

---
