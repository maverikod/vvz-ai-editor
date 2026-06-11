# delete_unwatched_projects

**Command name:** `delete_unwatched_projects`  
**Class:** `DeleteUnwatchedProjectsMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The delete_unwatched_projects command deletes only ORPHANED project records from the database: projects whose root_path does not exist on disk or is invalid. It does NOT delete projects that exist on disk but are outside the current watched directories (those are kept; reason exists_on_disk_but_not_in_watch_dirs). File-operating commands work only within watched directories; this command only cleans DB records for projects that no longer have a valid root on disk.

Operation flow:
1. Gets watched directories from config or parameter
2. Discovers all projects in watched directories using project discovery
3. Gets all projects from database
4. For each DB project: invalid path or server root protected; root_path not exists -> marked for deletion (orphaned); root exists and in discovered list -> kept; root exists but not in discovered list -> KEPT (exists_on_disk_but_not_in_watch_dirs).
5. If dry_run=True: reports what would be deleted/kept; no actual deletion
6. If dry_run=False: deletes only marked (orphaned) project data via clear_project_data
7. Returns deletion summary

Protection:
- Server root directory is always protected from deletion
- Projects that exist on disk but are not in watch_dirs are KEPT (no file operations outside watched dirs)
- Only orphaned DB records (root_path missing/invalid) are deleted

Use cases: Remove orphaned project records from database (root moved or deleted on disk); maintain database cleanliness.

Important notes:
- This operation is PERMANENT and cannot be undone
- Always use dry_run=True first to preview what will be deleted
- Use with extreme caution

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `watched_dirs` | array | No | Optional list of watched directory paths. If not provided, will be read from config.json (code_analysis.worker.watch_dirs). |
| `dry_run` | boolean | No | If True, only show what would be deleted without actually deleting. Default: False. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Whether operation was successful (True if no errors)
- `dry_run`: Whether this was a dry run
- `deleted_count`: Number of projects deleted (or would be deleted)
- `kept_count`: Number of projects kept
- `projects_deleted`: List of projects that were deleted. Each contains:
- project_id: Project UUID
- root_path: Project root path
- name: Project name
- reason: Reason for deletion (not_discovered_in_watch_dirs, invalid_path)
- `projects_kept`: List of projects that were kept. Each contains:
- project_id: Project UUID
- root_path: Project root path
- name: Project name
- reason: Reason for keeping (discovered_in_watch_dirs, server_root_protected)
- `discovery_errors`: List of errors during project discovery (if any)
- `errors`: List of errors during deletion (if any)
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** NO_WATCHED_DIRS, DELETE_UNWATCHED_PROJECTS_ERROR (and others).

---

## Examples

### Correct usage

**Preview deletion (dry run)**
```json
{
  "root_dir": "/home/user/projects/code_analysis",
  "dry_run": true
}
```

Shows which projects would be deleted and which would be kept. Safe to run to preview deletion.

**Delete unwatched projects using config**
```json
{
  "root_dir": "/home/user/projects/code_analysis"
}
```

Deletes only orphaned project records (root_path missing on disk) using config. WARNING: This is permanent and cannot be undone.

**Delete unwatched projects with explicit watched_dirs**
```json
{
  "root_dir": "/home/user/projects/code_analysis",
  "watched_dirs": [
    "/home/user/projects",
    "/var/lib/projects"
  ]
}
```

Deletes only orphaned project records (root_path missing on disk); watched_dirs override config. Overrides config.json watched_dirs.

### Incorrect usage

- **NO_WATCHED_DIRS**: watched_dirs not provided and not in config.json. Provide watched_dirs parameter or configure code_analysis.worker.watch_dirs in config.json.

- **DELETE_UNWATCHED_PROJECTS_ERROR**: Database error, project discovery error, or deletion failure. Check database integrity, verify watched directories exist, ensure project discovery works. Use dry_run=True first.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `NO_WATCHED_DIRS` | No watched directories found | Provide watched_dirs parameter or configure code_a |
| `DELETE_UNWATCHED_PROJECTS_ERROR` | General error during deletion | Check database integrity, verify watched directori |

## Best practices

- ALWAYS use dry_run=True first to preview what will be deleted
- Verify watched_dirs are correct before deletion
- Backup database before deleting projects
- This operation is permanent - double-check before proceeding
- Server root directory is automatically protected
- Review projects_kept and projects_deleted lists carefully
- Check discovery_errors to identify project discovery issues

---
