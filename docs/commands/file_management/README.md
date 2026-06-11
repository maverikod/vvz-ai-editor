# File Management Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for **file lifecycle** (delete, trash, restore, DB repair, version collapse) and legacy line-oriented text I/O.

**Editing file content:** use **[file_editing/](../file_editing/)** — not `read_project_text_file` / `write_project_text_lines`.

See [FILE_TRASH.md](FILE_TRASH.md) for file-level trash layout and behaviour (mark, restore, pre-check, permanent delete).

## Commands → File Mapping

| MCP Command Name     | Class                         | Source File                            |
|----------------------|-------------------------------|----------------------------------------|
| cleanup_deleted_files| CleanupDeletedFilesMCPCommand | `commands/file_management_mcp_commands.py`|
| list_deleted_files   | ListDeletedFilesMCPCommand   | (same)                                 |
| unmark_deleted_file  | UnmarkDeletedFileMCPCommand  | (same)                                 |
| restore_deleted_files| RestoreDeletedFilesMCPCommand| (same)                                 |
| collapse_versions    | CollapseVersionsMCPCommand   | (same)                                 |
| repair_database      | RepairDatabaseMCPCommand     | (same)                                 |
| read_project_text_file | ReadProjectTextFileCommand | `commands/read_project_text_file_command.py` |
| write_project_text_lines | WriteProjectTextLinesCommand | `commands/write_project_text_lines_command.py` |

Legacy text read/write commands remain for compatibility; they are **not** the MCP editing path. See deprecation notes in each command doc.

Internal commands: `CleanupDeletedFilesCommand`, `CollapseVersionsCommand`, `RepairDatabaseCommand`, `UnmarkDeletedFileCommand` in `commands/file_management.py`. All MCP commands inherit from `BaseMCPCommand`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
