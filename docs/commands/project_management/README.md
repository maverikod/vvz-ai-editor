# Project Management Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for project lifecycle: create, delete, list, change project ID, delete unwatched projects.

## Commands → File Mapping

| MCP Command Name        | Class                        | Source File                              |
|-------------------------|------------------------------|------------------------------------------|
| change_project_id       | ChangeProjectIdMCPCommand    | `commands/project_management_mcp_commands.py`|
| create_project          | CreateProjectMCPCommand      | (same)                                   |
| delete_project          | DeleteProjectMCPCommand      | (same)                                   |
| delete_unwatched_projects| DeleteUnwatchedProjectsMCPCommand| (same)                                |
| list_projects           | ListProjectsMCPCommand       | (same)                                   |

Internal: `CreateProjectCommand` in `commands/project_creation.py`, `DeleteProjectCommand` in `commands/project_deletion.py`, `DeleteUnwatchedProjectsCommand` in `commands/delete_unwatched_projects_command.py`. All MCP commands inherit from `BaseMCPCommand`. Re-export in `commands/__init__.py`: ChangeProjectIdMCPCommand, ListProjectsMCPCommand.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
