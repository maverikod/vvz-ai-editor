# unmark_deleted_file

**Command name:** `unmark_deleted_file`  
**Class:** `UnmarkDeletedFileMCPCommand`  
**Source:** `code_analysis/commands/file_management_mcp_commands.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The unmark_deleted_file command unmarks a file as deleted and restores it from the version directory back to its original location. This is a recovery operation that moves files back from the version directory to the project directory.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Searches for file in database by path or original_path
5. Retrieves file record with original_path and version_dir
6. If dry_run=True:
   - Shows what would be restored without actually restoring
7. If dry_run=False:
   - Moves file from version_dir back to original_path
   - Clears original_path and version_dir columns
   - Sets deleted=0, updates updated_at
   - File will be processed again by file watcher
8. Returns restoration information

Recovery Process:
- File is moved from version directory to original location
- Database record is updated (deleted=0)
- File watcher will detect and process the restored file
- All file data (AST, CST, chunks) is preserved

Use cases:
- Recover accidentally deleted files
- Restore files from version directory
- Undo file deletion

Important notes:
- File must have original_path in database (cannot restore if missing)
- File must exist in version directory
- Original location must be writable
- Use dry_run=True to preview restoration

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `file_path` | string | **Yes** | File path (current in version_dir or original_path) |
| `dry_run` | boolean | No | If True, only show what would be restored Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `restored`: Whether file was restored (True) or would be restored (dry_run)
- `file_path`: File path that was processed
- `original_path`: Original path where file will be restored
- `version_dir`: Version directory where file currently is
- `dry_run`: Whether this was a dry run
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, NO_ORIGINAL_PATH, FILE_EXISTS_AT_TARGET, UNMARK_ERROR (and others).

---

## Examples

### Correct usage

**Preview file restoration (dry run)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py",
  "dry_run": true
}
```

Shows what would be restored without actually restoring the file.

**Restore deleted file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Restores src/main.py from version directory back to original location.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FILE_NOT_FOUND**: file_path='src/main.py' but file not in database. Verify file path is correct and file exists in database.

- **NO_ORIGINAL_PATH**: File was deleted but original_path is missing. File cannot be restored without original_path. Use repair_database to fix database integrity.

- **FILE_EXISTS_AT_TARGET**: original_path already has a file on disk. Delete or rename the existing file at the target path before restoring.

- **UNMARK_ERROR**: File move error, permission denied, or database error. Check file permissions, verify version directory exists, ensure original location is writable.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FILE_NOT_FOUND` | File not found in database | Verify file path is correct and file exists in dat |
| `NO_ORIGINAL_PATH` | File has no original_path, cannot restore | File cannot be restored without original_path. Use |
| `FILE_EXISTS_AT_TARGET` | Target path already exists in project; restore would overwri | Delete or rename the existing file at the target p |
| `UNMARK_ERROR` | General error during file restoration | Check file permissions, verify version directory e |

## Best practices

- Use dry_run=True first to preview restoration
- Verify file exists in version directory before restoring
- Ensure original location is writable
- File will be automatically processed by file watcher after restoration
- Use repair_database if original_path is missing

---
