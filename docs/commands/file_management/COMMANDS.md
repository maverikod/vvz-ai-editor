# File Management Commands — Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Content editing:** [file_editing/](../file_editing/) — not the commands below marked *legacy*.

Each command is described in a separate file: purpose, arguments, return format, and examples.

| Command | Description | Doc |
|---------|-------------|-----|
| cleanup_deleted_files | Remove deleted file records from DB | [cleanup_deleted_files.md](cleanup_deleted_files.md) |
| delete_file | Mark file as deleted and move to trash (soft delete) | [delete_file.md](delete_file.md) |
| list_deleted_files | List deleted files (path in trash, original_path) | [FILE_TRASH.md](FILE_TRASH.md) |
| unmark_deleted_file | Restore one file from trash | [unmark_deleted_file.md](unmark_deleted_file.md) |
| restore_deleted_files | Restore many files (batch; pre-check: no target exists) | [FILE_TRASH.md](FILE_TRASH.md) |
| collapse_versions | Collapse/prune old file versions | [collapse_versions.md](collapse_versions.md) |
| repair_database | Logical repair of project DB | [repair_database.md](repair_database.md) |
| read_project_text_file | **Legacy** read — use `universal_file_preview` | [read_project_text_file.md](read_project_text_file.md) |
| write_project_text_lines | **Legacy** line replace — use universal edit session | [write_project_text_lines.md](write_project_text_lines.md) |

See [README.md](README.md) for block overview.
