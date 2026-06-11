# delete_project

**Command name:** `delete_project`  
**Class:** `DeleteProjectMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The delete_project command completely removes a project and all its data from the database. Optionally, it can also delete the project directory and version files from disk. This is a destructive operation that cannot be undone.

Operation flow:
1. Resolves database path from server configuration (config.json)
2. Opens database connection
3. Validates project_id exists in database and retrieves project information
4. Retrieves project information and statistics
5. If dry_run=True:
   - Returns statistics about what would be deleted
   - Shows what would be deleted from disk (if delete_from_disk=True)
   - Does not perform actual deletion
6. If dry_run=False:
   a. Deletes all project data from database first (while project dir still exists)
   b. If delete_from_disk=True:
      * Moves project root directory to trash (recycle bin); does NOT permanently delete
      * Permanently deletes version directory for this project ({version_dir}/{project_id}/)
      * Continues even if move/delete fails (errors are logged)
   c. Database deletion:
      * All files and their associated data (classes, functions, methods, imports, usages)
      * All chunks and removes from FAISS vector index
      * All duplicates
      * All AST trees
      * All CST trees
      * The project record itself
7. Returns deletion summary

Deleted Data (Database):
- Files: All file records and metadata
- Code entities: All classes, functions, methods
- Imports: All import records
- Usages: All usage records
- Chunks: All code chunks and vector indexes
- Duplicates: All duplicate records
- AST/CST: All AST and CST trees
- Project record: The project itself

Disk (if delete_from_disk=True):
- Project root directory: Moved to trash (recycle bin), not permanently deleted. Use list_trashed_projects / permanently_delete_from_trash / clear_trash to manage.
- Version directory: Permanently removed ({version_dir}/{project_id}/)
  Trash directory is typically 'data/trash' (config: code_analysis.storage.trash_dir)

Use cases:
- Remove projects that are no longer needed (database only)
- Completely remove projects including files from disk
- Clean up test projects
- Free up database and disk space
- Remove orphaned projects

Important notes:
- This operation is PERMANENT and cannot be undone
- Always use dry_run=True first to preview what will be deleted
- By default (delete_from_disk=False), only database records are deleted
- If delete_from_disk=True, project files and version directory are also deleted
- Disk deletion errors are logged but do not stop database deletion
- All related data is cascaded and removed from database
- Use with extreme caution, especially with delete_from_disk=True

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID v4). Required. The project identifier to delete. Can be obtained from list_projects command. |
| `dry_run` | boolean | No | If True, only show what would be deleted without actually deleting. Default: False. Default: `false`. |
| `delete_from_disk` | boolean | No | If True, move project root directory to trash (recycle bin) and delete version directory. If False, only delete from database. Default: False. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Whether deletion was successful (always True for dry_run)
- `dry_run`: Whether this was a dry run
- `project_id`: Project UUID that was deleted (or would be deleted)
- `project_name`: Project name
- `root_path`: Project root path
- `files_count`: Number of files that were deleted
- `chunks_count`: Number of chunks that were deleted
- `delete_from_disk`: Whether disk deletion was requested
- `version_dir`: Version directory path (if delete_from_disk=True)
- `disk_deletion_errors`: List of disk deletion errors (if any)
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, DATABASE_ERROR, DELETE_PROJECT_ERROR (and others).

---

## Examples

### Correct usage

**Preview deletion (dry run)**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "dry_run": true
}
```

Shows statistics about what would be deleted without actually deleting. Safe to run to preview deletion. Always use this first before actual deletion.

**Delete project from database only**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7"
}
```

Permanently deletes project and all its data from database. Project files on disk are NOT deleted. WARNING: This is permanent and cannot be undone.

**Delete project from database and move to trash**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "delete_from_disk": true
}
```

Deletes project from database and moves project directory to trash (recycle bin). Version directory is permanently deleted. Use list_trashed_projects to see trashed items; permanently_delete_from_trash or clear_trash to remove from disk permanently.

### Incorrect usage

- **PROJECT_NOT_FOUND**: project_id='550e8400-e29b-41d4-a716-446655440000' but project not in database. Verify project exists. Run list_projects to see all projects and their IDs. Ensure the project_id is correct and the project is registered in the database.

- **CONFIG_NOT_FOUND**: config.json missing or invalid. Ensure config.json exists and is valid JSON. The configuration file is required to resolve database path.

- **DATABASE_ERROR**: Database locked, corrupted, or permission denied. Check database integrity, ensure it's not locked by another process, verify file permissions, or run repair_sqlite_database if corrupted

- **DELETE_PROJECT_ERROR**: Database error, cascade deletion failure, or permission denied. Check database integrity, ensure database is not locked, verify file permissions. Use dry_run=True first to identify issues.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project with specified project_id not found in database | Verify project exists. Run list_projects to see al |
| `CONFIG_NOT_FOUND` | Server configuration file (config.json) not found or cannot  | Ensure config.json exists and is valid JSON. The c |
| `DATABASE_ERROR` | Failed to open or query the database | Check database integrity, ensure it's not locked b |
| `DELETE_PROJECT_ERROR` | General error during project deletion | Check database integrity, ensure database is not l |

## Best practices

- ALWAYS use dry_run=True first to preview what will be deleted
- Verify project_id is correct before deletion - use list_projects to get project IDs
- Backup database before deleting important projects
- This operation is permanent - double-check before proceeding
- By default, project files on disk are NOT deleted, only database records
- Use list_projects to verify project exists and get correct project_id before deletion
- Database path is automatically resolved from server configuration, no root_dir needed

---
