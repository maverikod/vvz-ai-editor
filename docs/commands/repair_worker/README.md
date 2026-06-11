# Repair Worker Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for repair worker process: start, stop, status.

## Commands → File Mapping

| MCP Command Name   | Class                      | Source File                          |
|--------------------|----------------------------|--------------------------------------|
| start_repair_worker| StartRepairWorkerMCPCommand | `commands/repair_worker_mcp_commands.py`|
| stop_repair_worker | StopRepairWorkerMCPCommand  | (same)                               |
| repair_worker_status| RepairWorkerStatusMCPCommand| (same)                               |

Core: `core/repair_worker_management.py` (or similar). Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
