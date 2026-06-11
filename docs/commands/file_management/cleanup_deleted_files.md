# cleanup_deleted_files

**Command name:** `cleanup_deleted_files`  
**Class:** `CleanupDeletedFilesMCPCommand`  
**Source:** `code_analysis/commands/file_management_mcp_commands.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cleanup_deleted_files command cleans up deleted files from the database. It can perform soft delete (just listing) or hard delete (permanent removal). Hard delete permanently removes files and all related data from the database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (if provided) or processes all projects
4. Retrieves deleted files from database (where deleted=1)
5. If older_than_days specified, filters files deleted more than N days ago
6. If dry_run=True:
   - Lists files that would be deleted
   - Returns statistics without making changes
7. If dry_run=False and hard_delete=False:
   - Lists deleted files (soft delete - no actual deletion)
8. If hard_delete=True:
   - Permanently deletes file record from database
   - Removes physical file from version directory
   - Removes all chunks and removes from FAISS index
   - Removes all classes, functions, methods
   - Removes all AST trees
   - Removes all vector indexes
9. Returns cleanup statistics

Delete Types:
- Soft delete (hard_delete=False): Only lists deleted files, no actual deletion
- Hard delete (hard_delete=True): Permanently removes file and all related data

Use cases:
- Clean up old deleted files
- Free up database space
- Remove files deleted more than N days ago
- Permanently remove files (use with caution)

Important notes:
- Hard delete is PERMANENT and cannot be recovered
- Always use dry_run=True first to see what would be deleted
- older_than_days helps prevent accidental deletion of recently deleted files
- If project_id is None, processes all projects
- Hard delete removes all data: file, chunks, AST, vectors, entities

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Optional project UUID (from list_projects); if omitted, all projects |
| `dry_run` | boolean | No | If True, only show what would be deleted Default: `false`. |
| `older_than_days` | integer | No | Only delete files deleted more than N days ago |
| `hard_delete` | boolean | No | If True, permanently delete (removes physical file and all DB data) Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `deleted_files`: List of files that were deleted (or would be deleted). Each entry contains file path and metadata.
- `total_files`: Total number of files processed
- `total_size`: Total size of deleted files (in bytes)
- `dry_run`: Whether this was a dry run
- `hard_delete`: Whether hard delete was performed

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CLEANUP_ERROR (and others).

---

## Examples

### Correct usage

**Preview what would be deleted (dry run)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "dry_run": true
}
```

Lists all deleted files that would be cleaned up without actually deleting. Safe to run to preview changes.

**Clean up files deleted more than 30 days ago**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "older_than_days": 30,
  "hard_delete": true
}
```

Permanently deletes files that were deleted more than 30 days ago. Useful for cleaning up old deleted files.

**Hard delete all deleted files for specific project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "hard_delete": true
}
```

Permanently deletes all deleted files for the specified project. WARNING: This is permanent and cannot be recovered.

### Incorrect usage

- **PROJECT_NOT_FOUND**: project_id='uuid' but project doesn't exist. Verify project_id is correct or omit to process all projects.

- **CLEANUP_ERROR**: Database error, file access error, or deletion failure. Check database integrity, verify file permissions, ensure files are accessible. Use dry_run=True first to identify issues.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct or omit to process al |
| `CLEANUP_ERROR` | General error during cleanup | Check database integrity, verify file permissions, |

## Best practices

- Always use dry_run=True first to preview what would be deleted
- Use older_than_days to prevent accidental deletion of recently deleted files
- Use hard_delete with caution - it's permanent and cannot be recovered
- Run this command periodically to clean up old deleted files
- Backup database before hard delete operations
- If project_id is None, processes all projects - be careful with hard_delete

---
