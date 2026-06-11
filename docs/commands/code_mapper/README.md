# Code Mapper Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for code indexing and code-mapper reports: update indexes, list long files, list errors by category.

## Commands → File Mapping

| MCP Command Name      | Class                        | Source File                          |
|-----------------------|------------------------------|--------------------------------------|
| update_indexes        | UpdateIndexesMCPCommand      | `commands/code_mapper_mcp_command.py`|
| list_long_files       | ListLongFilesMCPCommand      | `commands/code_mapper_mcp_commands.py`|
| list_errors_by_category| ListErrorsByCategoryMCPCommand| (same)                             |

Internal (non-MCP) commands: `ListLongFilesCommand`, `ListErrorsByCategoryCommand` in `commands/code_mapper_commands.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
