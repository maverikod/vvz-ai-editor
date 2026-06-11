# clear_all_backups

**Command name:** `clear_all_backups`  
**Class:** `ClearAllBackupsMCPCommand`  
**Source:** `code_analysis/commands/backup_mcp_commands.py`  
**Category:** backup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The clear_all_backups command permanently removes ALL backups and backup history from the project. It deletes all backup files from old_code/ directory and clears the backup index. This is a destructive operation that cannot be undone.

Operation flow:
1. Validates root_dir exists and is a directory
2. Initializes BackupManager for the project
3. Ensures old_code/ directory exists (creates if needed)
4. Deletes all files in old_code/ directory except index.txt
5. Clears backup index by saving empty index to index.txt
6. Returns success message

Clearing Behavior:
- ALL backup files are permanently deleted
- Backup index is cleared (all entries removed)
- old_code/ directory structure is preserved (directory not deleted)
- index.txt file is reset to empty state
- Operation cannot be undone
- No backups remain after this operation

Use cases:
- Clean up project by removing all backup history
- Free up disk space by deleting all backups
- Reset backup system for a fresh start
- Remove backups before archiving or sharing project
- Clean up after successful project completion

Important notes:
- This operation is DESTRUCTIVE and PERMANENT
- ALL backups are deleted - no way to restore files after this
- Use with extreme caution - ensure backups are not needed
- Consider backing up old_code/ directory before clearing if needed
- After clearing, no files can be restored from backup history
- old_code/ directory is not deleted, only its contents

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
- `message`: Human-readable success message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CLEAR_BACKUPS_ERROR (and others).

---

## Examples

### Correct usage

**Clear all backups from project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Permanently deletes all backup files and clears backup history. Use with caution - operation cannot be undone.

**Clean up backups in current directory**
```json
{
  "root_dir": "."
}
```

Removes all backups from the current working directory's project. Frees up disk space but loses all backup history.

### Incorrect usage

- **CLEAR_BACKUPS_ERROR**: Error during backup clearing. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `CLEAR_BACKUPS_ERROR` | Error during backup clearing |  |

## Best practices

- ⚠️ WARNING: This operation is permanent and cannot be undone
- Verify no backups are needed before clearing
- Consider backing up old_code/ directory before clearing if you might need it
- Use this command only when you're certain backups are no longer needed
- After clearing, restore_backup_file will not work (no backups exist)
- Use list_backup_files first to see what will be deleted
- Consider using delete_backup for selective cleanup instead
- Use this for project cleanup or before archiving/sharing

---
