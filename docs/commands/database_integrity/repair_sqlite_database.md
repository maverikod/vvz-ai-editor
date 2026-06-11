# repair_sqlite_database

**Command name:** `repair_sqlite_database`  
**Class:** `RepairSQLiteDatabaseMCPCommand`  
**Source:** `code_analysis/commands/database_integrity_mcp_commands.py`  
**Category:** database_integrity

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The repair_sqlite_database command repairs a corrupted SQLite database by backing it up and recreating it from scratch. This is a destructive operation that removes all data from the database.

Operation flow:
1. Resolves database path from server config (one shared DB for all projects)
2. If force=False, checks if only marker clearing is needed
3. If force=False and DB is healthy, clears marker only
4. If force=False and DB is corrupted, requires force=True
5. If force=True, stops all workers
6. Creates automatic backup of database and sidecars
7. Recreates database file from scratch (empty schema)
8. Clears corruption marker
9. Returns repair result with next steps

Repair Modes:
- Non-destructive (force=False): Only clears marker if DB is healthy
  - Useful when marker was set due to transient errors
  - Does not recreate database
  - Safe operation, no data loss
- Destructive (force=True): Backs up and recreates database
  - All database data is lost
  - Creates fresh empty database
  - Requires explicit confirmation (force=True)

Worker Management:
- All workers are stopped before repair
- Prevents concurrent access during repair
- Workers can be restarted after repair

After Repair:
- Database is empty (fresh schema)
- Corruption marker is cleared
- Must run update_indexes to rebuild indexes
- All project data must be re-indexed

Use cases:
- Repair corrupted database
- Clear corruption marker after manual recovery
- Recover from database corruption
- Reset database to clean state
- Fix database integrity issues

Important notes:
- ⚠️ DESTRUCTIVE: All database data is lost when force=True
- Automatic backup is created before recreation
- Must run update_indexes after repair to rebuild data
- Use force=False to clear marker without data loss
- Workers are stopped automatically during repair

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | No | Optional; ignored. DB path from server config. |
| `force` | boolean | No | Must be true to perform destructive repair. Default: `false`. |
| `backup_dir` | string | No | Optional directory for backups (default: backup_dir from server config). |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `db_path`: Path to shared database file (from server config)
- `backup_dir`: Directory where backups were created
- `workers_stopped`: Result of stopping workers
- `repair`: (see example)
- `marker_cleared`: True if corruption marker was cleared
- `next_step`: Recommended next action (usually 'Run update_indexes')
- `mode`: Repair mode (only present if force=False and marker cleared)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CONFIRM_REQUIRED, REPAIR_SQLITE_ERROR (and others).

---

## Examples

### Correct usage

**Clear marker without data loss**
```json
{
  "force": false
}
```

Clears corruption marker if database is healthy. No data loss, safe operation.

**Repair corrupted database**
```json
{
  "force": true
}
```

Backs up and recreates shared database. All data is lost. Must run update_indexes after repair.

**Repair with custom backup location**
```json
{
  "force": true,
  "backup_dir": "/backups/code_analysis"
}
```

Repairs database and stores backup in custom location.

### Incorrect usage

- **CONFIRM_REQUIRED**: Force confirmation required. Set force=True to confirm destructive operation. If you only need to clear marker, ensure DB is healthy and use force=False.

- **REPAIR_SQLITE_ERROR**: Error during repair. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `CONFIRM_REQUIRED` | Force confirmation required | Set force=True to confirm destructive operation. I |
| `REPAIR_SQLITE_ERROR` | Error during repair |  |

## Best practices

- ⚠️ WARNING: force=True destroys all database data
- Run backup_database manually before repair for extra safety
- Use force=False first to clear marker if DB is healthy
- After repair, immediately run update_indexes to rebuild data
- Check repair.repaired field to confirm database was recreated
- Verify backup_paths list to ensure backup was created
- Use restore_database if you need to restore from backup
- Stop workers manually if automatic stop fails

---
