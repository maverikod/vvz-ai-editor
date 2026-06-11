# list_projects

**Command name:** `list_projects`  
**Class:** `ListProjectsMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_projects command retrieves all projects from the database and returns for each project: project id, watch_dir (observed directory path), and project directory name, plus root_path, comment, watch_dir_id, updated_at.

Parameters: Only watched_dir_id (optional). Database path is from server config only.

Operation flow:
1. Opens database from server configuration (config.json)
2. If watched_dir_id is provided, filters projects by watched_dir_id
3. For each project, resolves watch_dir path from watch_dir_paths table
4. Returns list with id, watch_dir (path), name (project dir name), and other metadata

Use cases:
- Discover all projects and get project_id for other commands
- Get watch_dir path and project directory name per project
- Filter projects by watched directory

Important: Each project always includes id, watch_dir (path or None), and name.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `watched_dir_id` | string | No | Optional watched directory identifier (UUID4). If provided, only projects from this watched directory will be returned. If not provided, all projects from all watched directories are returned. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `projects`: List of project dictionaries. Each project always includes:
- id: Project UUID (string)
- watch_dir: Watched directory absolute path (string, or None if not linked)
- name: Project directory name (string, may be None)
Additional fields: root_path, comment, watch_dir_id, updated_at.
- `count`: Number of projects found (integer)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CONFIG_NOT_FOUND, DATABASE_NOT_FOUND, DATABASE_ERROR, INVALID_WATCHED_DIR_ID (and others).

---

## Examples

### Correct usage

**List projects from specific watched directory**
```json
{
  "watched_dir_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Lists only projects that belong to the specified watched directory. Useful for filtering projects by their watch directory location.

### Incorrect usage

- **CONFIG_NOT_FOUND**: config.json missing or invalid. Ensure config.json exists and is valid JSON. The configuration file is required to resolve database path.

- **DATABASE_NOT_FOUND**: Database path from config.json points to non-existent file. Ensure the database file exists at the configured path. You may need to run update_indexes or restore_database first to create the database.

- **DATABASE_ERROR**: Database locked, corrupted, or permission denied. Check database integrity, ensure it's not locked by another process, verify file permissions, or run repair_sqlite_database if corrupted

- **INVALID_WATCHED_DIR_ID**: watched_dir_id='invalid-uuid' or watched_dir_id not in watch_dirs table. Verify the watched_dir_id is a valid UUID4 and exists in the watch_dirs table. Use list_projects without filter first to see available projects and their watch_dir_id values.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `CONFIG_NOT_FOUND` | Server configuration file (config.json) not found or cannot  | Ensure config.json exists and is valid JSON. The c |
| `DATABASE_NOT_FOUND` | Database file not found at the path resolved from configurat | Ensure the database file exists at the configured  |
| `DATABASE_ERROR` | Failed to open or query the database | Check database integrity, ensure it's not locked b |
| `INVALID_WATCHED_DIR_ID` | watched_dir_id provided but not found in database | Verify the watched_dir_id is a valid UUID4 and exi |

---
