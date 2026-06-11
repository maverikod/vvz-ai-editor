# list_backup_files

**Command name:** `list_backup_files`  
**Class:** `ListBackupFilesMCPCommand`  
**Source:** `code_analysis/commands/backup_mcp_commands.py`  
**Category:** backup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_backup_files command retrieves all unique files that have been backed up in the project's old_code directory. It returns a list of file paths along with metadata from the latest backup version for each file.

Operation flow:
1. Validates root_dir exists and is a directory
2. Initializes BackupManager for the project
3. Loads backup index from old_code/index.txt
4. Extracts unique file paths from all backup entries
5. For each file, finds the latest backup version
6. Enriches file info with command name and related_files from latest backup
7. Returns list of files with metadata

Backup System:
- Backups are stored in old_code/ directory relative to root_dir
- Each backup has a UUID and is indexed in old_code/index.txt
- Backup filename format: path_with_underscores-UUID
- Index format: UUID|File Path|Timestamp|Command|Related Files|Comment

Use cases:
- Discover all files that have been backed up
- Check which files were modified by specific commands
- Find files that were part of refactoring operations
- Audit backup history

Important notes:
- Returns unique file paths (one entry per file, not per backup)
- Each file entry includes metadata from its latest backup
- command field shows which command created the latest backup
- related_files field shows files created/modified together (e.g., from split operations)
- Empty backup directory returns empty list (count: 0)
- File paths are relative to root_dir

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `files`: List of file dictionaries. Each contains:
- file_path: Original file path (relative to root_dir)
- command: Name of command that created latest backup (optional)
- related_files: List of related files (e.g., from split operations, optional)
- `count`: Number of unique backed up files

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** LIST_BACKUP_FILES_ERROR (and others).

---

## Examples

### Correct usage

**List all backed up files in project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns all unique files that have been backed up, with metadata from their latest backup version.

**Check backups in current directory**
```json
{
  "root_dir": "."
}
```

Lists all backed up files in the current working directory's project.

### Incorrect usage

- **LIST_BACKUP_FILES_ERROR**: Invalid root_dir, missing old_code directory, corrupted index file, or permission errors. Verify root_dir exists and is accessible, check old_code/index.txt file integrity, ensure proper file permissions

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `LIST_BACKUP_FILES_ERROR` | General error during backup file listing | Verify root_dir exists and is accessible, check ol |

## Best practices

- Use this command to discover what files have been modified
- Check command field to understand what operations created backups
- Use related_files to find files created together (e.g., from splits)
- Combine with list_backup_versions to see all backup versions for a file
- Use before restore_backup_file to find available files to restore

---
