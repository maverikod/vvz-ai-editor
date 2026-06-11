# permanently_delete_from_trash

**Command name:** `permanently_delete_from_trash`  
**Class:** `PermanentlyDeleteFromTrashMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Permanently delete one project folder from trash (recycle bin). The folder is removed from disk; this cannot be undone. The folder name must be a direct child of trash_dir (no path separators or `..` allowed).

**Execution:** Runs via queue (`use_queue=True`). Use `queue_get_job_status` with the returned `job_id` to monitor progress. Database cleanup is done in one transaction with batched DELETEs (`execute_batch`); then the folder and FAISS index are removed from disk.

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `trash_folder_name` | string | **Yes** | Name of the trashed folder to delete (e.g. `MyProject_2025-01-29T14-30-00Z`). Must be a direct child of trash_dir. |
| `trash_dir` | string | No | Path to trash directory. If omitted, uses trash_dir from server config. |

---

## Returned data

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True
- `message`: Confirmation message
- `trash_folder_name`: Name of the folder that was deleted

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_PATH, NOT_FOUND, NOT_DIRECTORY, DELETE_ERROR, PERMANENTLY_DELETE_FROM_TRASH_ERROR.

---

## Examples

**Permanently delete one folder from trash**
```json
{
  "trash_folder_name": "MyProject_2025-01-29T14-30-00Z"
}
```

---

## Related commands

- `list_trashed_projects` — list folders in trash to get folder_name
- `clear_trash` — permanently delete all contents of trash
