# Database Integrity Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for database integrity and repair: corruption status, backup database, repair SQLite.

## Commands → File Mapping

| MCP Command Name              | Class                              | Source File                            |
|-------------------------------|------------------------------------|----------------------------------------|
| get_database_corruption_status| GetDatabaseCorruptionStatusMCPCommand| `commands/database_integrity_mcp_commands.py`|
| backup_database               | BackupDatabaseMCPCommand           | (same)                                  |
| repair_sqlite_database        | RepairSQLiteDatabaseMCPCommand     | (same)                                  |

All commands inherit from `BaseMCPCommand`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
