# type_check_code

**Command name:** `type_check_code`  
**Class:** `TypeCheckCodeCommand`  
**Source:** `code_analysis/commands/code_quality_commands.py`  
**Category:** code_quality

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

Static type checking with mypy. Validates file_path, optional config_file; auto-detects pyproject.toml in parent dirs. Always runs mypy on the single target file (never package-wide). Repo-root config is skipped. Read-only; returns success and list of errors. ignore_errors=True treats errors as warnings.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | **Yes** | Path to Python file to type check. If project_id is provided, relative to project root. |
| `project_id` | string | No | Optional project UUID. If provided, file_path is relative to project root. |
| `config_file` | string | No | Optional path to mypy config file (e.g. pyproject.toml). |
| `ignore_errors` | boolean | No | If True, treat errors as warnings. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path`: Path to type-checked file
- `config_file`: Path to mypy config file used (None if auto-detected or not found)
- `success`: True if no type errors found (or ignore_errors=True), False if type errors found and ignore_errors=False
- `error`: Error message if type checking failed (None if successful)
- `errors`: List of type error strings. Each error follows format: file_path:line:column: error_type: error_message
- `error_count`: Number of type errors found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_NOT_FOUND, NOT_A_FILE, CONFIG_NOT_FOUND, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Type check a Python file**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py"
}
```

Type checks main.py using auto-detected mypy config. Returns all type errors found for that file only.

**Type check with explicit config**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py",
  "config_file": "/home/user/projects/my_project/pyproject.toml"
}
```

Type checks main.py using specified mypy config file. Result is still for the single file only.

**Type check with errors as warnings**
```json
{
  "file_path": "./code_analysis/commands/backup_mcp_commands.py",
  "ignore_errors": true
}
```

Type checks file but treats errors as warnings. Returns success=True even if errors found (errors still in list).

### Incorrect usage

- **FILE_NOT_FOUND**: file_path='/path/to/nonexistent.py'. Verify file path is correct and file exists

- **NOT_A_FILE**: file_path='/path/to/directory'. Ensure path points to a file, not a directory

- **CONFIG_NOT_FOUND**: config_file='/path/to/missing/pyproject.toml'. Verify config file path is correct and file exists

- **INTERNAL_ERROR**: Unexpected exception in type checking logic. Check logs for details, verify file permissions and mypy installation

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_NOT_FOUND` | File does not exist | Verify file path is correct and file exists |
| `NOT_A_FILE` | Path is not a file (e.g., directory) | Ensure path points to a file, not a directory |
| `CONFIG_NOT_FOUND` | Config file specified but not found | Verify config file path is correct and file exists |
| `INTERNAL_ERROR` | Internal error during type checking | Check logs for details, verify file permissions an |

## Best practices

- Run type_check_code after adding type hints to validate them
- Fix all type errors before committing code
- Use ignore_errors=True for gradual type checking adoption
- Check error_count field to quickly see if issues exist
- Review errors list to understand type issues
- Run type_check_code in CI/CD pipelines to enforce type safety
- Use config_file for project-specific mypy settings
- This command always checks a single file; result set is scoped to that file

---
