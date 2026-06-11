# Worker Status Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for worker and database status: get worker status, get database status.

## Commands → File Mapping

| MCP Command Name      | Class                      | Source File                            |
|-----------------------|----------------------------|----------------------------------------|
| get_worker_status     | GetWorkerStatusMCPCommand  | `commands/worker_status_mcp_commands.py` |
| get_database_status   | GetDatabaseStatusMCPCommand| (same)                                 |

Internal: `WorkerStatusCommand`, `DatabaseStatusCommand` in `commands/worker_status.py`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
