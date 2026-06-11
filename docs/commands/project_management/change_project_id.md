# change_project_id

**Command name:** `change_project_id`  
**Class:** `ChangeProjectIdMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The change_project_id command updates the project identifier and/or description for a project. This is a critical operation that affects both the projectid file and the database. You can change project_id, description, or both in a single operation.

Operation flow:
1. Validates root_dir exists and is a directory
2. Validates new_project_id is a valid UUID v4 format
3. If old_project_id is provided, validates it matches current projectid file
4. Loads current project information from projectid file (if exists)
5. Updates projectid file in JSON format with:
   - new_project_id (always updated)
   - description (updated if provided, otherwise preserved from existing file)
6. If update_database is True, updates project record in database (if exists):
   - Updates project id (if changed)
   - Updates comment field (description) if provided

Project ID File Format:
The projectid file is stored in JSON format:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "description": "Human readable description"
}

Description Handling:
- If description parameter is provided: Updates description in both file and database
- If description parameter is not provided: Preserves existing description from projectid file
- If projectid file doesn't exist: Uses empty string as default description
- Description can be updated independently of project_id

Safety features:
- Validates new_project_id format (must be UUID v4)
- Optional old_project_id validation prevents accidental changes
- Database update is optional (can update only file)
- Preserves existing description if not explicitly provided

Important notes:
- This command modifies project identity - use with caution
- If database has existing project with old_project_id, it will be updated
- If database has no project record, only file is updated
- All future commands will use the new project_id
- Description update is optional and can be done separately from project_id change

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Current project identifier (UUID4). Project root path is resolved from database. |
| `new_project_id` | string | **Yes** | New project identifier. Must be a valid UUID v4 format (e.g., '8772a086-688d-4198-a0c4-f03817cc0e6c'). This will replace the current project_id in both the projectid file and database. |
| `old_project_id` | string | No | Optional current project_id for safety validation. If provided, must match the current project_id in projectid file. This prevents accidental changes if the projectid file was modified externally. |
| `description` | string | No | Optional new project description. If provided, updates the description in both projectid file and database. If not provided, existing description is preserved. Can be updated independently of project_ |
| `update_database` | boolean | No | If True, update the project record in the database (if exists). If False, only update the projectid file. Default: True. Default: `true`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `old_project_id`: Previous project_id from projectid file
- `new_project_id`: New project_id that was set
- `old_description`: Previous description from projectid file (if existed)
- `new_description`: New description that was set (if provided)
- `projectid_file_path`: Path to updated projectid file
- `database_updated`: Whether database was updated (True/False)
- `database_project_id`: New project_id in database (if updated)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_UUID_FORMAT, INVALID_UUID_VERSION, PROJECTID_FILE_NOT_FOUND, OLD_PROJECT_ID_MISMATCH, ROOT_DIR_NOT_FOUND, DATABASE_UPDATE_FAILED (and others).

---

## Examples

### Correct usage

**Basic usage: change project ID**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c"
}
```

Updates projectid file and database with new UUID v4 identifier. No old_project_id validation is performed.

**Safe change with old_project_id validation**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "old_project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94"
}
```

Validates that current projectid file contains old_project_id before updating. If mismatch, command fails with validation error.

**Update only file, not database**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "update_database": false
}
```

Updates only the projectid file. Database is not modified. Useful when database doesn't exist yet or you want to update file separately.

**Change both project_id and description**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "description": "Updated project description"
}
```

Updates both project_id and description in projectid file and database. Both fields are updated in a single operation.

**Update only description (keep same project_id)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "description": "New description for existing project"
}
```

Updates only the description while keeping the same project_id. Provide the current project_id as new_project_id and the new description.

### Incorrect usage

- **INVALID_UUID_FORMAT**: new_project_id='invalid-uuid'. Provide a valid UUID v4 format (e.g., '8772a086-688d-4198-a0c4-f03817cc0e6c')

- **INVALID_UUID_VERSION**: new_project_id='61d708de-e9fe-11f0-b3c3-2ba372fd1d94' (UUID v1). Generate a new UUID v4 using uuid.uuid4() or online UUID generator

- **PROJECTID_FILE_NOT_FOUND**: root_dir='/path/to/project' but projectid file missing. Ensure projectid file exists in the project root directory

- **OLD_PROJECT_ID_MISMATCH**: old_project_id='abc...' but file contains 'xyz...'. Either remove old_project_id parameter or provide the correct current value. Check current value by reading root_dir/projectid file.

- **ROOT_DIR_NOT_FOUND**: root_dir='/nonexistent/path'. Provide a valid existing directory path

- **DATABASE_UPDATE_FAILED**: Database locked, corrupted, or project record not found. Check database integrity, ensure it's not locked by another process, or set update_database=False to skip database update

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_UUID_FORMAT` | new_project_id is not a valid UUID format | Provide a valid UUID v4 format (e.g., '8772a086-68 |
| `INVALID_UUID_VERSION` | new_project_id is not UUID v4 (wrong version) | Generate a new UUID v4 using uuid.uuid4() or onlin |
| `PROJECTID_FILE_NOT_FOUND` | projectid file not found in root_dir | Ensure projectid file exists in the project root d |
| `OLD_PROJECT_ID_MISMATCH` | old_project_id provided but doesn't match current projectid  | Either remove old_project_id parameter or provide  |
| `ROOT_DIR_NOT_FOUND` | root_dir path doesn't exist or is not a directory | Provide a valid existing directory path |
| `DATABASE_UPDATE_FAILED` | Failed to update project record in database | Check database integrity, ensure it's not locked b |

---
