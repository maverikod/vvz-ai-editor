# restore_database

**Command name:** `restore_database`  
**Class:** `RestoreDatabaseFromConfigMCPCommand`  
**Source:** `code_analysis/commands/database_restore_mcp_commands.py`  
**Category:** database_restore

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The restore_database command rebuilds a SQLite database by sequentially indexing all configured directories. It implements a complete recovery workflow: backup existing database, recreate fresh database, then index all configured directories into the same database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Loads and parses config file (JSON)
3. Extracts directory list from config (code_analysis.dirs or code_analysis.worker.watch_dirs)
4. Resolves all directories to absolute paths
5. If dry_run=True, returns plan without executing
6. Stops all workers to prevent concurrent access
7. Creates automatic backup of existing database
8. Recreates database file from scratch (fresh schema)
9. Clears corruption marker
10. Sequentially indexes each configured directory
11. Returns summary with statistics

Config File Format:
- JSON file (typically config.json)
- Looks for directories in:
  1. code_analysis.dirs (array of directory paths)
  2. code_analysis.worker.watch_dirs (array of directory paths)
- Directories can be absolute or relative to config file location
- Empty directories are skipped

Indexing Process:
- Each directory is processed sequentially
- Python files are discovered recursively
- Each file is analyzed and indexed into database
- Project ID is created/retrieved for each directory
- Statistics are collected per directory and total

Statistics Collected:
- files_total: Total Python files discovered
- files_processed: Successfully indexed files
- errors: Files with analysis errors
- syntax_errors: Files with syntax errors
- classes: Total classes indexed
- functions: Total functions indexed
- methods: Total methods indexed
- imports: Total imports indexed

Use cases:
- Rebuild database after corruption
- Restore database from configuration
- Re-index all projects from scratch
- Migrate database to new structure
- Recover from database loss
- Initialize database for new setup

Important notes:
- ⚠️ DESTRUCTIVE: Existing database is recreated (all data lost)
- Automatic backup is created before recreation
- All workers are stopped during restore
- Process is sequential (one directory at a time)
- Use dry_run=True to preview plan without executing
- This is a long-running operation (use_queue=True)
- Directories are indexed into same database (separated by project_id)

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `config_file` | string | No | Path to JSON config file (absolute or relative to server config directory). Default: `"config.json"`. |
| `max_lines` | integer | No | Maximum lines per file threshold (for reporting). Default: `400`. |
| `dry_run` | boolean | No | If True, only resolve dirs and show plan; do not recreate DB or index. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `plan`: (see example)
- `workers_stopped`: Result of stopping workers
- `db_backup_paths`: List of created backup file paths
- `dirs_processed`: List of per-directory statistics. Each contains:
- root_dir: Directory path
- project_id: Project UUID
- files_discovered: Number of Python files found
- files_processed: Successfully indexed files
- errors: Files with errors
- syntax_errors: Files with syntax errors
- status: Processing status (or 'skipped' with reason)
- `totals`: (see example)
- `message`: Human-readable success message
- `dry_run`: True if dry_run mode (only present if True)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CONFIG_NOT_FOUND, INVALID_CONFIG, NO_DIRS, RESTORE_DATABASE_ERROR (and others).

---

## Examples

### Correct usage

**Preview restore plan without executing**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "config_file": "config.json",
  "dry_run": true
}
```

Shows which directories will be indexed without modifying database.

**Restore database from config**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "config_file": "config.json"
}
```

Rebuilds database by indexing all directories from config. This is a long-running operation.

**Restore with custom config file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "config_file": "/path/to/custom_config.json"
}
```

Uses custom config file instead of default config.json.

### Incorrect usage

- **CONFIG_NOT_FOUND**: Config file not found. Verify config_file path is correct. Ensure file exists and is readable.

- **INVALID_CONFIG**: Config file is not valid JSON object. Check config file format. Must be valid JSON with object structure.

- **NO_DIRS**: No directories found in config. Add directories array to config file:
- code_analysis.dirs: ["/path/to/dir1", "/path/to/dir2"]
- OR code_analysis.worker.watch_dirs: ["/path/to/dir1"]

- **RESTORE_DATABASE_ERROR**: Error during restore operation. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `CONFIG_NOT_FOUND` | Config file not found | Verify config_file path is correct. Ensure file ex |
| `INVALID_CONFIG` | Config file is not valid JSON object | Check config file format. Must be valid JSON with  |
| `NO_DIRS` | No directories found in config | Add directories array to config file:
- code_analy |
| `RESTORE_DATABASE_ERROR` | Error during restore operation |  |

## Best practices

- ⚠️ WARNING: This operation destroys all existing database data
- Use dry_run=True first to preview the restore plan
- Ensure config file contains correct directory paths
- Verify all directories exist and are accessible
- This is a long-running operation - use queue for execution
- Check totals.files_processed to verify indexing success
- Review dirs_processed to see per-directory statistics
- Use backup_database manually before restore for extra safety

---
