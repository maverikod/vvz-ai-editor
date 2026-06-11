# list_long_files

**Command name:** `list_long_files`  
**Class:** `ListLongFilesMCPCommand`  
**Source:** `code_analysis/commands/code_mapper_mcp_commands.py`  
**Category:** code_mapper

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_long_files command lists all files in a project that exceed the maximum line limit. This is equivalent to old code_mapper functionality for finding oversized files. Large files are harder to maintain and may need to be split into smaller modules.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Queries files table for project files
5. Filters files where lines > max_lines
6. Returns list of files exceeding the threshold

Use cases:
- Identify files that need to be split
- Monitor file size compliance
- Find oversized files before refactoring
- Enforce file size limits

Important notes:
- Uses line count from database (updated during indexing)
- Default threshold is 400 lines (project standard)
- Files are sorted by line count (descending)
- Equivalent to code_mapper functionality

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `max_lines` | integer | No | Maximum lines threshold (default: 400) Default: `400`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `long_files`: List of files exceeding max_lines. Each entry contains:
- path: File path
- lines: Number of lines in file
- Additional file metadata from database
- `count`: Number of long files found
- `max_lines`: Maximum lines threshold used

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, LIST_LONG_FILES_ERROR (and others).

---

## Examples

### Correct usage

**List files exceeding 400 lines (default)**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Lists all files in project exceeding 400 lines (default threshold).

**List files exceeding custom threshold**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "max_lines": 500
}
```

Lists all files exceeding 500 lines.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **LIST_LONG_FILES_ERROR**: Database error or invalid parameters. Check database integrity, verify parameters, ensure project has been indexed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `LIST_LONG_FILES_ERROR` | General error during file listing | Check database integrity, verify parameters, ensur |

## Best practices

- Use default max_lines=400 to follow project standards
- Run this command regularly to monitor file sizes
- Use split_file_to_package to split large files
- Combine with comprehensive_analysis for complete code quality overview

---
