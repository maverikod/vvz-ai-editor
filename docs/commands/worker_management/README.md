# Worker Management Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands to start/stop workers (file_watcher, vectorization).

## Commands → File Mapping

| MCP Command Name | Class                 | Source File                              |
|------------------|-----------------------|------------------------------------------|
| start_worker     | StartWorkerMCPCommand | `commands/worker_management_mcp_commands.py`|
| stop_worker      | StopWorkerMCPCommand  | (same)                                   |

Registration: `code_analysis/hooks.py`. Core: `core/worker_manager.py`, `core/worker_lifecycle.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
