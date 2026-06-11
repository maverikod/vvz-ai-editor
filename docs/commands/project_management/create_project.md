# create_project

**Command name:** `create_project`  
**Class:** `CreateProjectMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The create_project command creates or registers a new project in the system. It validates prerequisites, creates a projectid file with UUID4 identifier, and registers the project in the database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Gets or creates watch_dir_id for watched_dir:
   - Searches for existing watch_dir by normalized path
   - If found: Uses existing watch_dir_id
   - If not found: Creates new watch_dir and watch_dir_path entries
4. Validates watched_dir exists and is a directory
5. Checks if watched_dir contains projectid file (raises error if found)
6. Validates project_dir exists and is a directory
7. Checks if project_dir is already registered in database:
   - If registered: Updates watch_dir_id if needed, returns existing project info (already_existed=True)
   - If not registered: Continues to creation
8. Checks if projectid file exists in project_dir:
   - If exists and valid: Registers in database using existing ID with watch_dir_id
   - If exists but invalid: Recreates projectid file
   - If not exists: Creates new projectid file with UUID4
9. Registers project in database with watch_dir_id
10. Returns project information including watch_dir_id

Project ID File Format:
The projectid file is created in JSON format:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "description": "Human readable description"
}

Validation Rules:
- watched_dir must exist and be a directory
- watched_dir must NOT contain projectid file
- project_dir must exist and be a directory
- project_dir must NOT be already registered in database (unless projectid exists)
- description is optional (defaults to project directory name)

Return Values:
- project_id: UUID4 identifier of the project
- already_existed: True if project was already registered, False if newly created
- description: Project description (from file if existed, or provided)
- old_description: Previous description if projectid file was recreated
- watch_dir_id: UUID4 identifier of the watch directory (project is linked to this watch_dir)
- message: Status message

Use cases:
- Register a new project for code analysis
- Register an existing project that has projectid file but not in database
- Create a new project from scratch
- Re-register a project after database cleanup

Option use_existing_dir (default false = old behaviour):
- use_existing_dir=false (default): if the project directory already exists and is not registered, the command fails with PROJECT_DIR_EXISTS (same as before this option existed).
- use_existing_dir=true: if the project directory already exists, the command creates only the projectid file (id + description) in that directory and registers the project in the database. Use this to register an existing folder without creating a new directory.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `watch_dir_id` | string | **Yes** | Watch directory ID (UUID4) from watch_dirs table. Must exist in database. Required. |
| `project_name` | string | **Yes** | Name of project subdirectory to create in watch_dir. Required. Must be a valid directory name. |
| `description` | string | **Yes** | Human-readable description of the project. Required. |
| `project_id` | string | No | Optional project ID (UUID4). If not provided, will be generated automatically. |
| `use_existing_dir` | boolean | No | Optional. Default false (old behaviour: fail with PROJECT_DIR_EXISTS if directory exists). If true: when project directory already exists, create only projectid file and register. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Whether operation was successful (always True)
- `project_id`: UUID4 identifier of the project
- `already_existed`: Whether project was already registered (True) or newly created (False)
- `description`: Project description (from file if existed, or provided)
- `old_description`: Previous description if projectid file was recreated, empty otherwise
- `watch_dir_id`: UUID4 identifier of the watch directory (project is linked to this watch_dir)
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** WATCHED_DIR_NOT_FOUND, WATCHED_DIR_NOT_DIRECTORY, PROJECTID_EXISTS_IN_WATCHED_DIR, PROJECT_DIR_NOT_FOUND, PROJECT_DIR_NOT_DIRECTORY, PROJECT_DIR_EXISTS, PROJECTID_WRITE_ERROR, DATABASE_REGISTRATION_ERROR, WATCH_DIR_ERROR, CREATE_PROJECT_ERROR (and others).

---

## Examples

### Correct usage

**Register existing directory (use_existing_dir=true)**
```json
{
  "watch_dir_id": "550e8400-e29b-41d4-a716-446655440001",
  "project_name": "vast_srv",
  "description": "AI Admin",
  "use_existing_dir": true
}
```

When the folder watch_dir/vast_srv already exists, creates projectid file with description and registers the project without failing with PROJECT_DIR_EXISTS.

**Create new project**
```json
{
  "root_dir": "/home/user/projects/tools/code_analysis",
  "watched_dir": "/home/user/projects/test_data",
  "project_dir": "/home/user/projects/test_data/my_project",
  "description": "My new project for testing"
}
```

Creates a new project in /home/user/projects/test_data/my_project. Creates projectid file with UUID4 and registers in database.

**Register existing project with projectid file**
```json
{
  "root_dir": "/home/user/projects/tools/code_analysis",
  "watched_dir": "/home/user/projects/test_data",
  "project_dir": "/home/user/projects/test_data/existing_project"
}
```

Registers an existing project that already has projectid file. Uses existing project ID from file.

**Get existing project info**
```json
{
  "root_dir": "/home/user/projects/tools/code_analysis",
  "watched_dir": "/home/user/projects/test_data",
  "project_dir": "/home/user/projects/test_data/registered_project"
}
```

If project is already registered in database, returns existing project info without creating new projectid file.

### Incorrect usage

- **WATCHED_DIR_NOT_FOUND**: watched_dir='/path/to/missing'. Verify watched directory path exists and is accessible.

- **WATCHED_DIR_NOT_DIRECTORY**: watched_dir='/path/to/file.txt'. Ensure watched_dir points to a directory, not a file.

- **PROJECTID_EXISTS_IN_WATCHED_DIR**: watched_dir='/path' contains projectid file. Watched directory should not contain projectid file. Use a parent directory as watched_dir, or remove projectid file if not needed.

- **PROJECT_DIR_NOT_FOUND**: project_dir='/path/to/missing'. Verify project directory path exists and is accessible.

- **PROJECT_DIR_NOT_DIRECTORY**: project_dir='/path/to/file.txt'. Ensure project_dir points to a directory, not a file.

- **PROJECT_DIR_EXISTS**: project_name='vast_srv' but test_data/vast_srv already exists. Pass use_existing_dir=true to register the existing directory.

- **PROJECTID_WRITE_ERROR**: Permission denied or disk full. Check file permissions, ensure directory is writable, verify disk space is available.

- **DATABASE_REGISTRATION_ERROR**: Database locked, constraint violation, or connection error. Check database integrity, ensure database is not locked, verify database connection is working.

- **WATCH_DIR_ERROR**: Error during watch_dir lookup or creation. Check database connection and permissions. Verify watched_dir path is valid.

- **CREATE_PROJECT_ERROR**: Unexpected error in validation or creation process. Check error message for specific details and resolve accordingly.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `WATCHED_DIR_NOT_FOUND` | Watched directory does not exist | Verify watched directory path exists and is access |
| `WATCHED_DIR_NOT_DIRECTORY` | Watched path is not a directory | Ensure watched_dir points to a directory, not a fi |
| `PROJECTID_EXISTS_IN_WATCHED_DIR` | Watched directory already contains projectid file | Watched directory should not contain projectid fil |
| `PROJECT_DIR_NOT_FOUND` | Project directory does not exist | Verify project directory path exists and is access |
| `PROJECT_DIR_NOT_DIRECTORY` | Project path is not a directory | Ensure project_dir points to a directory, not a fi |
| `PROJECT_DIR_EXISTS` | Project directory already exists and use_existing_dir was no | Pass use_existing_dir=true to register the existin |
| `PROJECTID_WRITE_ERROR` | Failed to write projectid file | Check file permissions, ensure directory is writab |
| `DATABASE_REGISTRATION_ERROR` | Failed to register project in database | Check database integrity, ensure database is not l |
| `WATCH_DIR_ERROR` | Failed to get or create watch_dir for watched_dir | Check database connection and permissions. Verify  |
| `CREATE_PROJECT_ERROR` | General error during project creation | Check error message for specific details and resol |

## Best practices

- Ensure watched_dir exists and does not contain projectid file
- Project will be automatically linked to watched_dir via watch_dir_id
- If watch_dir doesn't exist in database, it will be created automatically
- Use descriptive project descriptions for better organization
- If project already has projectid file, it will be used (not recreated)
- If project is already registered, command updates watch_dir_id if needed and returns existing info
- Always check already_existed flag to know if project was created or already existed
- watch_dir_id is returned in response and can be used for CST commands

---
