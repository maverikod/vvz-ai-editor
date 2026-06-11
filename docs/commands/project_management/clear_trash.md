# clear_trash

**Command name:** `clear_trash`  
**Class:** `ClearTrashMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Permanently delete all contents of the trash directory. All direct children of trash_dir are removed: directories (recursively) and files (including service files such as .projectid, lock files). Optionally use dry_run to only report what would be removed without deleting.

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dry_run` | boolean | No | If True, only list what would be removed without deleting. Default: False. |
| `trash_dir` | string | No | Path to trash directory. If omitted, uses trash_dir from server config. |

---

## Returned data

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True (or False if some removals failed; see `errors`)
- `removed_count`: Number of items removed (directories and files; or that would be removed if dry_run)
- `removed`: List of names removed (directories and files)
- `dry_run`: Whether this was a dry run
- `trash_dir`: Path to trash directory
- `errors`: List of error strings (if any removal failed)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CLEAR_TRASH_ERROR, CLEAR_TRASH.

---

## Examples

**Preview what would be removed (dry run)**
```json
{
  "dry_run": true
}
```

**Permanently clear all trash**
```json
{}
```

---

## Related commands

- `list_trashed_projects` — list folders in trash before clearing
- `permanently_delete_from_trash` — permanently delete one folder from trash
