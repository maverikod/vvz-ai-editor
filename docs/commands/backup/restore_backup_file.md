# restore_backup_file

**Command name:** `restore_backup_file`  
**Class:** `RestoreBackupFileMCPCommand`  
**Source:** `code_analysis/commands/backup_mcp_commands.py`  
**Category:** backup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The restore_backup_file command restores a file from a backup copy stored in the old_code directory. It can restore a specific backup version by UUID or automatically restore the latest version if no UUID is provided.

Operation flow:
1. Validates root_dir exists and is a directory
2. Initializes BackupManager for the project
3. Loads backup index from old_code/index.txt
4. Searches for backups matching the file_path
5. If backup_uuid provided, finds that specific backup
6. If backup_uuid not provided, selects latest backup (by timestamp)
7. Verifies backup file exists in old_code/ directory
8. Creates parent directories if needed
9. Copies backup file to original location (overwrites existing file)
10. Returns success message with backup UUID used

Restoration Behavior:
- If backup_uuid specified, restores that exact version
- If backup_uuid omitted, restores latest version (newest timestamp)
- Original file is overwritten (no backup of current file is created)
- Parent directories are created automatically if missing
- File permissions and metadata are preserved from backup

Use cases:
- Undo changes and restore previous version
- Recover from accidental modifications
- Restore specific version from history
- Revert refactoring operations
- Test different file versions

Important notes:
- Original file is overwritten without creating a new backup
- If you want to preserve current file, create backup first
- File path must be relative to root_dir
- Backup file must exist in old_code/ directory
- If no backups found for file, operation fails

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Original file path (relative to project root) |
| `backup_uuid` | string | No | UUID of backup to restore (optional, uses latest if not provided) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `message`: Human-readable success message with backup UUID
- `file_path`: Path of restored file (relative to root_dir)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** RESTORE_BACKUP_ERROR (and others).

---

## Examples

### Correct usage

**Restore latest version of a file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "code_analysis/core/backup_manager.py"
}
```

Restores the most recent backup version of backup_manager.py. Useful for undoing recent changes.

**Restore specific backup version**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "code_analysis/core/backup_manager.py",
  "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
}
```

Restores a specific backup version identified by UUID. Use list_backup_versions to find the UUID.

**Restore file after failed refactoring**
```json
{
  "root_dir": ".",
  "file_path": "src/main.py"
}
```

Restores main.py to its latest backup state, effectively undoing a failed refactoring operation.

### Incorrect usage

- **RESTORE_BACKUP_ERROR**: Error during file restoration. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `RESTORE_BACKUP_ERROR` | Error during file restoration |  |

## Best practices

- Use list_backup_versions first to see available backup versions
- If unsure which version, omit backup_uuid to restore latest
- Consider creating a backup of current file before restoring (if needed)
- Use specific backup_uuid for precise version control
- Verify file after restoration to ensure it's correct
- Check related_files in backup metadata to restore related files if needed
- After restoration, file is overwritten - changes are lost

---
