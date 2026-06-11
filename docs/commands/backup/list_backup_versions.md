# list_backup_versions

**Command name:** `list_backup_versions`  
**Class:** `ListBackupVersionsMCPCommand`  
**Source:** `code_analysis/commands/backup_mcp_commands.py`  
**Category:** backup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_backup_versions command retrieves all backup versions for a specific file. It returns detailed information about each backup including UUID, timestamp, file size, line count, command that created it, and related files.

Operation flow:
1. Validates root_dir exists and is a directory
2. Initializes BackupManager for the project
3. Loads backup index from old_code/index.txt
4. Searches index for all backups matching the file_path
5. For each matching backup, verifies backup file exists
6. Calculates file size in bytes and line count
7. Extracts metadata (command, comment, related_files) from index
8. Sorts versions by timestamp (newest first)
9. Returns list of all versions with full details

Version Information:
- Each version has a unique UUID
- Timestamp shows when backup was created (from file mtime)
- size_bytes: File size in bytes
- size_lines: Number of lines in file
- command: Command that created this backup
- comment: Optional comment/message from backup creation
- related_files: List of files created/modified together

Use cases:
- View backup history for a specific file
- Compare file sizes across versions
- Find specific backup UUID for restoration
- Understand what operations created each backup
- Track file evolution over time

Important notes:
- File path must be relative to root_dir
- Versions are sorted by timestamp (newest first)
- Only backups with existing files are returned
- If no backups found, returns empty list (count: 0)
- Path matching is normalized (handles / and \ separators)

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Original file path (relative to project root) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path`: Original file path that was queried
- `versions`: List of version dictionaries. Each contains:
- uuid: Backup UUID (use this for restore_backup_file)
- timestamp: Backup creation timestamp (YYYY-MM-DDTHH-MM-SS)
- size_bytes: File size in bytes
- size_lines: Number of lines in file
- command: Command that created this backup (optional)
- comment: Optional comment from backup creation
- related_files: List of related files (optional)
- `count`: Number of backup versions found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** LIST_BACKUP_VERSIONS_ERROR (and others).

---

## Examples

### Correct usage

**List all versions of a specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "code_analysis/core/backup_manager.py"
}
```

Returns all backup versions for backup_manager.py, sorted by timestamp (newest first).

**Check backup history for a file**
```json
{
  "root_dir": ".",
  "file_path": "src/main.py"
}
```

Lists all backup versions of main.py to see its change history.

### Incorrect usage

- **LIST_BACKUP_VERSIONS_ERROR**: Invalid root_dir, missing old_code directory, corrupted index file, file_path not found, or permission errors. Verify root_dir exists, check file_path is correct and relative to root_dir, ensure old_code/index.txt is readable, check file permissions

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `LIST_BACKUP_VERSIONS_ERROR` | General error during version listing | Verify root_dir exists, check file_path is correct |

## Best practices

- Use this command before restore_backup_file to find specific backup UUID
- Compare size_bytes and size_lines to see file changes
- Check command field to understand what operation created each backup
- Use timestamp to identify newest or oldest versions
- Use related_files to find files created together in refactoring operations
- First version in list (index 0) is always the newest

---
