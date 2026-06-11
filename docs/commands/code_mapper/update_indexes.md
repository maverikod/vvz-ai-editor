# update_indexes

**Command name:** `update_indexes`  
**Class:** `UpdateIndexesMCPCommand`  
**Source:** `code_analysis/commands/code_mapper_mcp_command.py`  
**Category:** code_mapper

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The update_indexes command analyzes Python project files and updates code indexes in the SQLite database. This is a long-running command executed via queue that parses Python files, extracts code entities, and stores them in the database for fast retrieval and analysis.

Operation flow:
1. Resolves project root_path from shared database by project_id
2. Validates root_path exists and is a directory
3. Checks database integrity (if corrupted, enters safe mode)
4. Scans root_path for Python files (excludes .git, __pycache__, node_modules, data, logs). The project virtualenv (``.venv`` / ``venv``) is excluded by default. Optional server config ``code_analysis.venv_site_packages_index_allowlisted_distributions`` lists **pip distribution names** (PEP 503–normalized matching); for those distributions only, ``.py`` files declared in each wheel/sdist ``*.dist-info/RECORD`` under ``site-packages`` are included in the scan. Anything else under the venv remains skipped.
5. For each Python file:
   - Reads file content and parses AST
   - Saves AST tree to database
   - Saves CST (source code) to database
   - Extracts classes, functions, methods, imports
   - Calculates cyclomatic complexity for functions/methods
   - Stores entities in database
   - Adds content to full-text search index
   - Marks file for chunking
6. Updates progress tracker during processing
7. Returns summary statistics

Database Safety:
- Checks database integrity before starting
- If corruption detected:
  - Creates backup of database files
  - Writes corruption marker
  - Stops workers
  - Enters safe mode (only backup/restore/repair commands allowed)
- Returns error if database is in safe mode

Indexed Information:
- Files: Path, line count, modification time, docstring status
- Classes: Name, line, docstring, base classes
- Functions: Name, line, parameters, docstring, complexity
- Methods: Name, line, parameters, docstring, complexity, class context
- Imports: Module, name, type, line
- AST trees: Full AST JSON for each file
- CST trees: Full source code for each file
- Full-text search: Code content indexed for search

Use cases:
- Initial project indexing
- Re-indexing after code changes
- Updating indexes after adding new files
- Rebuilding database indexes

Important notes:
- Server commands must not write into the project ``.venv`` / ``venv`` (see ``PROJECT_VENV_WRITE_FORBIDDEN``); use project pip commands to change installed packages.
- This is a long-running command (use_queue=True)
- Progress is tracked and can be monitored via queue_get_job_status
- Skips files with syntax errors (continues with other files)
- Files are processed sequentially
- Database must not be corrupted (check integrity first)
- Excludes hidden directories and common build/cache directories

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `max_lines` | integer | No | Maximum lines per file threshold. Default: `400`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `project_id`: Project UUID
- `root_path`: Project root path that was analyzed (from database)
- `files_processed`: Number of files successfully processed
- `files_total`: Total number of files analyzed
- `files_discovered`: Total number of Python files discovered
- `errors`: Number of files with errors
- `syntax_errors`: Number of files with syntax errors
- `classes`: Total number of classes indexed
- `functions`: Total number of functions indexed
- `methods`: Total number of methods indexed
- `imports`: Total number of imports indexed
- `db_repaired`: Whether database was repaired (always False)
- `db_backup_paths`: List of backup paths (empty if no backup)
- `workers_restarted`: Dictionary of restarted workers (empty)
- `message`: Summary message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** DATABASE_CORRUPTED, INDEX_UPDATE_ERROR (and others).

---

## Examples

### Correct usage

**Update indexes for project**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Resolves project root from database by project_id, then analyzes all Python files and updates indexes. Long-running; use queue_get_job_status to check progress.

**Update indexes with custom line threshold**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "max_lines": 500
}
```

Updates indexes and uses 500 lines as threshold for long file reporting.

### Incorrect usage

- **DATABASE_CORRUPTED**: Database integrity check failed or corruption marker exists. Database is in safe mode. Run repair_sqlite_database (force=true) or restore_database from backup, then re-run update_indexes.

- **INDEX_UPDATE_ERROR**: File access error, AST parsing error, or database error. Check file permissions, verify Python files are valid, check database integrity. Syntax errors in files are skipped automatically.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `DATABASE_CORRUPTED` | Database is corrupted and in safe mode | Database is in safe mode. Run repair_sqlite_databa |
| `INDEX_UPDATE_ERROR` | General error during index update | Check file permissions, verify Python files are va |

## Best practices

- Run this command after adding new files or making significant code changes
- Use queue_get_job_status to monitor progress for large projects
- Check database integrity before running (use get_database_corruption_status)
- Run regularly to keep indexes up-to-date
- If database is corrupted, repair or restore before re-indexing
- Review error counts in results to identify problematic files
- This command is required before using most other analysis commands

---
