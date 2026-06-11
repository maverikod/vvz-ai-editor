# delete_file

**Command name:** `delete_file`  
**Class:** `DeleteFileMCPCommand`  
**Source:** `code_analysis/commands/file_management_mcp_commands.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The delete_file command marks a file as deleted (soft delete) and moves it to file trash. The file is removed from the project directory and stored under `trash_dir/{project_id}/...`. It can be restored later with `unmark_deleted_file`.

Operation flow:
1. Resolves project root and opens database connection
2. Resolves trash_dir from config (code_analysis.storage.trash_dir)
3. Normalizes file_path against project root
4. Marks file as deleted in DB and moves it to trash
5. Sets deleted=1, stores original_path; file is no longer in project tree

Use cases:
- Remove a file from the project without permanent loss
- Clean up obsolete files (e.g. restored duplicate that was replaced by a package)
- File can be restored with unmark_deleted_file

Important notes:
- trash_dir must be configured in config.json (code_analysis.storage.trash_dir)
- file_path is relative to project root (e.g. ai_admin/commands/foo.py)
- File must exist in the project and be registered in the database

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `file_path` | string | **Yes** | File path relative to project root (e.g. ai_admin/commands/foo.py). |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True if file was found and marked deleted
- `file_path`: The file path that was processed
- `message`: Status message

### Error

- **FILE_NOT_FOUND**: File not found in project (not in database or path invalid).
- **DELETE_FILE_CONFIG_ERROR**: trash_dir not configured in config.json.
- **DELETE_FILE_ERROR**: General error (e.g. database, permissions).

---

## Related commands

| Command | Description |
|---------|-------------|
| unmark_deleted_file | Restore one file from trash |
| list_deleted_files | List deleted files (path in trash, original_path) |
| cleanup_deleted_files | Permanently remove deleted file records and physical files |
