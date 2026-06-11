# delete_backup

**Command name:** `delete_backup`  
**Class:** `DeleteBackupMCPCommand`  
**Source:** `code_analysis/commands/backup_mcp_commands.py`  
**Category:** backup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The delete_backup command permanently removes a specific backup from the backup system. It deletes both the backup file from old_code/ directory and removes the entry from the backup index.

Operation flow:
1. Validates root_dir exists and is a directory
2. Initializes BackupManager for the project
3. Loads backup index from old_code/index.txt
4. Verifies backup_uuid exists in index
5. Locates backup file using UUID and file path from index
6. Deletes backup file from old_code/ directory (if exists)
7. Removes entry from backup index
8. Saves updated index to disk
9. Returns success message

Deletion Behavior:
- Backup file is permanently deleted from filesystem
- Backup entry is removed from index
- Operation cannot be undone
- If backup file is missing but index entry exists, index is still cleaned
- Other backups for the same file are not affected

Use cases:
- Remove old backup versions to save disk space
- Clean up specific backup after successful restoration
- Remove corrupted or invalid backups
- Manage backup storage by deleting unnecessary versions

Important notes:
- Deletion is permanent and cannot be undone
- Only the specified backup is deleted, other versions remain
- If backup file is already missing, only index entry is removed
- Use list_backup_versions to find backup UUIDs
- Consider disk space implications before deleting backups

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `backup_uuid` | string | **Yes** | UUID of backup to delete |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `message`: Human-readable success message with backup UUID
- `backup_uuid`: UUID of deleted backup

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** DELETE_BACKUP_ERROR (and others).

---

## Examples

### Correct usage

**Delete a specific backup version**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
}
```

Permanently deletes the backup identified by UUID. Use list_backup_versions to find the UUID first.

**Remove old backup to free disk space**
```json
{
  "root_dir": ".",
  "backup_uuid": "223e4567-e89b-12d3-a456-426614174001"
}
```

Deletes an old backup version that is no longer needed, freeing up disk space while keeping other versions.

### Incorrect usage

- **DELETE_BACKUP_ERROR**: Error during backup deletion. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `DELETE_BACKUP_ERROR` | Error during backup deletion |  |

## Best practices

- Use list_backup_versions first to identify which backup to delete
- Verify backup UUID is correct before deletion (operation is permanent)
- Consider keeping at least one backup version for important files
- Delete old backups to manage disk space, but keep recent ones
- After deletion, backup cannot be restored - ensure it's not needed
- If unsure, use list_backup_versions to see all available versions first
- Deletion only affects the specified backup, other versions remain safe

---
