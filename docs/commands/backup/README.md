# Backup Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for file backup: list files/versions, restore, delete, clear all.

## Commands → File Mapping

| MCP Command Name   | Class                     | Source File (single module)     |
|--------------------|---------------------------|----------------------------------|
| list_backup_files  | ListBackupFilesMCPCommand | `commands/backup_mcp_commands.py`|
| list_backup_versions| ListBackupVersionsMCPCommand | (same)                        |
| restore_backup_file| RestoreBackupFileMCPCommand | (same)                       |
| delete_backup      | DeleteBackupMCPCommand    | (same)                           |
| clear_all_backups  | ClearAllBackupsMCPCommand | (same)                           |

All commands inherit from `BaseMCPCommand`; registration: `code_analysis/hooks.py` (backup block).

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
