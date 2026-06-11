# Log Viewer Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for viewing worker logs: list worker logs, view worker logs.

## Commands → File Mapping

| MCP Command Name   | Class                    | Source File                          |
|--------------------|--------------------------|--------------------------------------|
| view_worker_logs   | ViewWorkerLogsMCPCommand | `commands/log_viewer_mcp_commands.py`|
| list_worker_logs   | ListWorkerLogsMCPCommand  | (same)                               |

Internal: `ListLogFilesCommand`, `LogViewerCommand` in `commands/log_viewer.py`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
