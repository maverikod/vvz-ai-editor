# list_trashed_projects

**Command name:** `list_trashed_projects`  
**Class:** `ListTrashedProjectsMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

List projects that have been moved to trash (recycle bin). Returns direct children of trash_dir that are directories; folder names are parsed to extract original_name and deleted_at when they match the format name plus timestamp (e.g. MyProject_2025-01-29T14-30-00Z).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| trash_dir | string | No | Path to trash directory. If omitted, uses trash_dir from server config (StoragePaths). Default: data/trash relative to config. |

---

## Returned data

### Success

- **Shape:** SuccessResult with data object.
- success: True
- items: List of folder_name, original_name, deleted_at, path
- trash_dir: Path to trash directory
- count: Number of items

### Error

- **Shape:** ErrorResult with code and message.
- **Possible codes:** LIST_TRASH_ERROR, LIST_TRASHED_PROJECTS_ERROR.

---

## Examples

**List trashed projects (default trash_dir)**
```json
{}
```

**List trashed projects (custom trash_dir)**
```json
{
  "trash_dir": "/var/lib/code_analysis/trash"
}
```

---

## Related commands

- delete_project with delete_from_disk=true moves project to trash
- permanently_delete_from_trash permanently delete one folder from trash
- clear_trash permanently delete all contents of trash
