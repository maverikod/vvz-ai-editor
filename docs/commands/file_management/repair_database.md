# repair_database

**Command name:** `repair_database`  
**Class:** `RepairDatabaseMCPCommand`  
**Source:** `code_analysis/commands/file_management_mcp_commands.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The repair_database command repairs database integrity by restoring correct file status based on actual file presence in the project directory and version directory. It synchronizes the database with the actual file system state.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Resolves version_dir path (relative to root_dir if not absolute)
5. For each file in database:
   - Checks if file exists in project directory
   - Checks if file exists in version directory
   - Updates database status accordingly
6. Repair actions:
   - If file exists in project directory: Remove deleted flag (deleted=0)
   - If file exists in versions but not in project: Set deleted flag (deleted=1)
   - If file doesn't exist anywhere: Restore from CST nodes:
     * Place file in versions directory
     * Add to project files if not marked for deletion
7. If dry_run=True:
   - Lists files that would be repaired
   - Shows repair actions without making changes
8. If dry_run=False:
   - Performs actual repairs
   - Updates database records
   - Restores files from CST if needed
9. Returns repair statistics

Repair Actions:
- Restore deleted flag: Files in project directory should not be marked deleted
- Set deleted flag: Files in versions but not in project should be marked deleted
- Restore from CST: Files missing from filesystem can be restored from CST nodes

Use cases:
- Fix database inconsistencies after manual file operations
- Restore correct file status after file system changes
- Recover files from CST nodes
- Synchronize database with file system state

Important notes:
- Always use dry_run=True first to preview repairs
- Restores files from CST nodes if they don't exist in filesystem
- Updates database to match actual file system state
- version_dir defaults to 'data/versions' if not specified

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `version_dir` | string | No | Version directory for deleted files (default: data/versions) Default: `"data/versions"`. |
| `dry_run` | boolean | No | If True, only show what would be repaired Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `repaired_files`: List of files that were repaired. Each entry contains:
- path: File path
- action: Repair action (restore_deleted_flag, set_deleted_flag, restore_from_cst)
- status: File status after repair
- `total_repaired`: Total number of files repaired
- `dry_run`: Whether this was a dry run
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, REPAIR_DATABASE_ERROR (and others).

---

## Examples

### Correct usage

**Preview database repairs (dry run)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "dry_run": true
}
```

Lists all files that would be repaired, showing repair actions without actually making changes.

**Repair database integrity**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Repairs database integrity by synchronizing file status with actual file system. Restores files from CST if needed.

**Repair with custom version directory**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "version_dir": "custom/versions"
}
```

Repairs database using custom version directory for deleted files.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **REPAIR_DATABASE_ERROR**: Database error, file access error, or CST restoration failure. Check database integrity, verify file permissions, ensure version directory exists. Use dry_run=True first to identify issues.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `REPAIR_DATABASE_ERROR` | General error during database repair | Check database integrity, verify file permissions, |

## Best practices

- Always use dry_run=True first to preview what would be repaired
- Run this command after manual file system operations
- Use to fix database inconsistencies
- Files can be restored from CST nodes if missing from filesystem
- Regular repairs help maintain database integrity

---
