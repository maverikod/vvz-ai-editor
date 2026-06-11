# backup_database

**Command name:** `backup_database`  
**Class:** `BackupDatabaseMCPCommand`  
**Source:** `code_analysis/commands/database_integrity_mcp_commands.py`  
**Category:** database_integrity

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The backup_database command creates filesystem backups of a project's SQLite database file and its sidecar files (WAL, SHM, journal). This is a safety measure before destructive operations like repair.

Operation flow:
1. Resolves database path from server config (one shared DB for all projects)
2. Determines backup directory (default: backup_dir from server config)
3. Creates timestamped backups of database file
4. Creates backups of sidecar files if present (-wal, -shm, -journal)
5. Returns list of created backup file paths

Backup Files:
- Main database file: code_analysis.db.corrupt-backup.TIMESTAMP
- WAL file (if present): code_analysis.db-wal.corrupt-backup.TIMESTAMP
- SHM file (if present): code_analysis.db-shm.corrupt-backup.TIMESTAMP
- Journal file (if present): code_analysis.db-journal.corrupt-backup.TIMESTAMP
- Timestamp format: YYYYMMDD-HHMMSS

Sidecar Files:
- WAL (Write-Ahead Logging): Transaction log for SQLite
- SHM (Shared Memory): Shared memory file for WAL mode
- Journal: Rollback journal (if not in WAL mode)
- These files are critical for database consistency

Use cases:
- Create backup before repair operations
- Preserve database state before destructive changes
- Create recovery point for database restoration
- Backup before major database operations
- Safety measure before corruption repair

Important notes:
- Backups are created with timestamp in filename
- Multiple backups can coexist (each has unique timestamp)
- Only existing files are backed up (missing sidecars are skipped)
- Backup directory is created if it doesn't exist
- Original files are not modified (read-only operation)
- Use restore_database to restore from backup

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | No | Optional; ignored. DB path from server config. |
| `backup_dir` | string | No | Optional directory for backup files (default: backup_dir from server config). |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `db_path`: Path to shared database file (from server config)
- `backup_dir`: Directory where backups were created
- `backup_paths`: List of created backup file paths. Includes:
- Database file backup
- Sidecar file backups (if present)
- `count`: Number of backup files created

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** BACKUP_DATABASE_ERROR (and others).

---

## Examples

### Correct usage

**Backup database to custom location**
```json
{
  "backup_dir": "/backups/code_analysis"
}
```

Creates backups in specified directory instead of default.

### Incorrect usage

- **BACKUP_DATABASE_ERROR**: Error during backup creation. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `BACKUP_DATABASE_ERROR` | Error during backup creation |  |

## Best practices

- Run backup_database before repair_sqlite_database
- Use backup_database before any destructive database operations
- Store backups in separate directory for safety
- Keep multiple backups with different timestamps
- Verify backup_paths list after backup creation
- Use restore_database to restore from backup if needed
- Backup is automatically created by repair command, but manual backup is safer

---
