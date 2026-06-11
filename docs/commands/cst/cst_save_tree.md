# cst_save_tree

**Command name:** `cst_save_tree`  
**Class:** `CSTSaveTreeCommand`  
**Source:** `code_analysis/commands/cst_save_tree_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_save_tree command saves a CST tree to a file with full atomicity guarantees. If any error occurs during the save process, all changes are rolled back and the file is restored from backup.

Operation flow:
1. Gets project from database using project_id
2. Validates project is linked to watch directory
3. Gets watch directory path from database
4. Forms absolute path: watch_dir_path / project_name / file_path
5. Validates original file (if exists) through compile()
6. Creates backup via BackupManager (mandatory if file exists)
7. Generates source code from CST tree
8. Writes to temporary file
9. Validates temporary file (compile, syntax check)
10. Begins database transaction
11. Atomically replaces file via os.replace()
12. Updates database (add_file, update_file_data_atomic)
13. Commits database transaction
14. Creates git commit (if commit_message provided)
15. On any error: rolls back transaction and restores from backup

Atomicity Guarantees:
- File is either completely updated or completely unchanged
- Database is either completely updated or rolled back
- No intermediate states are possible
- Backup is automatically restored on any error

Error Handling:
- If validation fails: operation stops before any changes
- If file write fails: transaction rolled back, backup restored
- If database update fails: transaction rolled back, backup restored
- If git commit fails: file and database are already saved (non-critical)

Use cases:
- Save modified CST tree to file
- Persist refactoring changes
- Apply code transformations
- Batch file updates with rollback safety

Important notes:
- All operations are atomic (either all succeed or all fail)
- Backup is created before any changes
- Database transaction ensures consistency
- File system operation (os.replace) is atomic on most filesystems
- Git commit is optional and non-critical (file is already saved)

Recommended AI workflow:
1. Use cst_modify_tree for in-memory changes
2. Save with cst_save_tree
3. Run format_code/lint_code/type_check_code on the saved file
4. Run update_indexes after a batch of file changes

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target file path (relative to project root) |
| `validate` | boolean | No | Whether to validate file before saving. Default true. Set false for controlled incremental edits (for example docstring-only pass), then run format_code/lint_code/type_check_code explicitly. Default:  |
| `backup` | boolean | No | Whether to create backup Default: `true`. |
| `commit_message` | string | No | Optional git commit message |
| `auto_reload` | boolean | No | Automatically reload tree from file after save (keeps tree_id valid). Recommended for AI flows that perform multiple sequential edits. Default: `true`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `file_path`: Path to saved file
- `file_id`: File ID in database
- `backup_uuid`: UUID of created backup (if backup was created)
- `update_result`: Result from update_file_data_atomic

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CST_SAVE_ERROR (and others).

---

## Examples

### Correct usage

**Save tree with default options**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py"
}
```

Saves tree to file with validation and backup enabled by default. Absolute path is formed as: watch_dir_path / project_name / src/main.py. File is validated, backup is created, and database is updated atomically. If any step fails, all changes are rolled back.

**Save without validation**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "validate": false
}
```

Saves tree without validation. Use with caution. Backup is still created, and database is updated. Useful when you're certain the code is valid.

**Save without backup**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "backup": false
}
```

Saves tree without creating backup. Use with caution - no automatic rollback if database update fails. File is still saved atomically, but backup won't be available.

**Save with git commit**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "commit_message": "Refactor: update main function"
}
```

Saves tree and creates git commit with specified message. Git commit is non-critical - if it fails, file and database are already saved. Useful for tracking changes in version control.

**Save to new file**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/new_file.py"
}
```

Saves tree to a new file. No backup is created (file doesn't exist). File is created, validated, and added to database atomically. If any step fails, file is not created.

### Incorrect usage

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct and project exists in database

- **CST_SAVE_ERROR**: Error during save operation. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct and project exists in |
| `CST_SAVE_ERROR` | Error during save operation |  |

## Best practices

- Always use validate=True (default) unless you're certain code is valid
- Always provide project_id - it is required and used to form absolute path
- Ensure project is linked to watch directory before using this command
- Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')
- Always use backup=True (default) for safety
- Save tree immediately after modifications to avoid memory issues
- Check return value to ensure save was successful
- Use commit_message for version control integration

---
