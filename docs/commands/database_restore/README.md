# Database Restore Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Command to restore (rebuild) database by sequentially indexing directories from config.

## Commands → File Mapping

| MCP Command Name   | Class                          | Source File                            |
|--------------------|---------------------------------|----------------------------------------|
| restore_database   | RestoreDatabaseFromConfigMCPCommand| `commands/database_restore_mcp_commands.py`|

Inherits from `BaseMCPCommand`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for schema, parameters, and behavior.
