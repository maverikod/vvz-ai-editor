# Commands Index: Command → File → Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Related documentation

- **Detailed guide:** [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md) — main entry point: purpose, arguments, return format, and examples for all commands, with links to per-command docs.
- **Per-command files:** Each command has a **dedicated file** `docs/commands/<block>/<command_name>.md` (see tables below).
- **File editing (primary):** [commands/file_editing/](commands/file_editing/) — universal preview/open/edit/write/close workflow.

## How to use this guide

- **Quick lookup:** MCP command name → class → source file → docs block (tables below).
- **Per-command detailed guide:** Each command doc file contains:
  - **Purpose (предназначение)** — what the command does
  - **Arguments (аргументы)** — parameters, types, required/optional
  - **Returned data (возвращаемые данные)** — success/error format and examples
  - **Examples** — correct and incorrect usage
- **Block index:** In each block, `COMMANDS.md` lists all commands with links to these per-command files.
- **Code indices:** `code_analysis/method_index.yaml`, `code_analysis/code_map.yaml` for class/method lookup.

---

## File editing — universal workflow (`docs/commands/file_editing/`)

| Command | Class | Source File |
|---------|-------|-------------|
| universal_file_preview | UniversalFilePreviewCommand | commands/universal_file_preview_command.py |
| universal_file_open | UniversalFileOpenCommand | commands/universal_file_edit/open_command.py |
| universal_file_search | UniversalFileSearchCommand | commands/universal_file_edit/search_command.py |
| universal_file_edit | UniversalFileEditCommand | commands/universal_file_edit/edit_command.py |
| universal_file_write | UniversalFileWriteCommand | commands/universal_file_edit/write_command.py |
| universal_file_close | UniversalFileCloseCommand | commands/universal_file_edit/close_command.py |

Docs: [README.md](commands/file_editing/README.md), [WORKFLOW.md](commands/file_editing/WORKFLOW.md), [PYTHON_EDIT_SEMANTICS.md](commands/file_editing/PYTHON_EDIT_SEMANTICS.md).

---

## AST (`docs/commands/ast/`)

| Command             | Class                     | Source File                          |
|---------------------|---------------------------|--------------------------------------|
| get_ast             | GetASTMCPCommand          | commands/ast/get_ast.py              |
| search_ast_nodes    | SearchASTNodesMCPCommand  | commands/ast/search_nodes.py        |
| ast_statistics      | ASTStatisticsMCPCommand   | commands/ast/statistics.py           |
| list_project_files  | ListProjectFilesMCPCommand| commands/ast/list_files.py          |
| get_code_entity_info| GetCodeEntityInfoMCPCommand| commands/ast/entity_info.py         |
| list_code_entities  | ListCodeEntitiesMCPCommand| commands/ast/list_entities.py       |
| get_imports         | GetImportsMCPCommand      | commands/ast/imports.py             |
| find_dependencies   | FindDependenciesMCPCommand| commands/ast/dependencies.py        |
| get_entity_dependencies | GetEntityDependenciesMCPCommand | commands/ast/entity_dependencies.py |
| get_entity_dependents   | GetEntityDependentsMCPCommand   | commands/ast/entity_dependencies.py |
| get_class_hierarchy | GetClassHierarchyMCPCommand| commands/ast/hierarchy.py          |
| find_usages         | FindUsagesMCPCommand      | commands/ast/usages.py              |
| export_graph        | ExportGraphMCPCommand     | commands/ast/graph.py               |

---

## Backup (`docs/commands/backup/`)

| Command              | Class                     | Source File                  |
|----------------------|---------------------------|------------------------------|
| list_backup_files    | ListBackupFilesMCPCommand | commands/backup_mcp_commands.py |
| list_backup_versions | ListBackupVersionsMCPCommand | (same)                    |
| restore_backup_file  | RestoreBackupFileMCPCommand | (same)                    |
| delete_backup       | DeleteBackupMCPCommand   | (same)                        |
| clear_all_backups   | ClearAllBackupsMCPCommand | (same)                       |

---

## Code Mapper (`docs/commands/code_mapper/`)

| Command                | Class                          | Source File                          |
|------------------------|--------------------------------|--------------------------------------|
| update_indexes         | UpdateIndexesMCPCommand        | commands/code_mapper_mcp_command.py   |
| list_long_files        | ListLongFilesMCPCommand        | commands/code_mapper_mcp_commands.py |
| list_errors_by_category| ListErrorsByCategoryMCPCommand | (same)                               |

---

## Code Quality (`docs/commands/code_quality/`)

| Command       | Class               | Source File                      |
|---------------|---------------------|----------------------------------|
| format_code   | FormatCodeCommand   | commands/code_quality_commands.py |
| lint_code     | LintCodeCommand     | (same)                           |
| type_check_code| TypeCheckCodeCommand| (same)                           |

---

## CST (`docs/commands/cst/`) — internal / developer APIs

> **MCP agents:** edit files via [file_editing/](commands/file_editing/) only. CST commands remain registered for tooling and server development; do not use `cst_load_file` → `cst_modify_tree` → `cst_save_tree` as the editing workflow.

| Command             | Class                     | Source File                              |
|---------------------|---------------------------|------------------------------------------|
| cst_load_file       | CSTLoadFileCommand        | commands/cst_load_file_command.py         |
| cst_save_tree       | CSTSaveTreeCommand        | commands/cst_save_tree_command.py         |
| cst_reload_tree     | CSTReloadTreeCommand      | commands/cst_reload_tree_command.py       |
| cst_find_node       | CSTFindNodeCommand        | commands/cst_find_node_command.py         |
| cst_get_node_info   | CSTGetNodeInfoCommand     | commands/cst_get_node_info_command.py    |
| cst_get_node_by_range| CSTGetNodeByRangeCommand  | commands/cst_get_node_by_range_command.py |
| cst_modify_tree     | CSTModifyTreeCommand      | commands/cst_modify_tree_command.py       |
| cst_apply_buffer    | CSTApplyBufferCommand     | commands/cst_apply_buffer_command.py      |
| cst_create_file     | CSTCreateFileCommand     | commands/cst_create_file_command.py       |
| cst_convert_and_save | CSTConvertAndSaveCommand  | commands/cst_convert_and_save_command.py  |
| list_cst_blocks     | ListCSTBlocksCommand      | commands/list_cst_blocks_command.py       |
| query_cst           | QueryCSTCommand           | commands/query_cst_command.py             |

---

## Database Integrity (`docs/commands/database_integrity/`)

| Command                     | Class                              | Source File                              |
|-----------------------------|------------------------------------|------------------------------------------|
| get_database_corruption_status| GetDatabaseCorruptionStatusMCPCommand| commands/database_integrity_mcp_commands.py |
| backup_database             | BackupDatabaseMCPCommand           | (same)                                    |
| repair_sqlite_database      | RepairSQLiteDatabaseMCPCommand    | (same)                                    |

---

## Database Restore (`docs/commands/database_restore/`)

| Command          | Class                              | Source File                            |
|------------------|------------------------------------|----------------------------------------|
| restore_database | RestoreDatabaseFromConfigMCPCommand| commands/database_restore_mcp_commands.py |

---

## File Management (`docs/commands/file_management/`)

Lifecycle, trash, DB repair — **not** primary content editing. For read/write file content use [file_editing/](commands/file_editing/).

| Command              | Class                        | Source File                            |
|----------------------|-----------------------------|----------------------------------------|
| cleanup_deleted_files| CleanupDeletedFilesMCPCommand| commands/file_management_mcp_commands.py |
| delete_file         | DeleteFileMCPCommand         | (same)                                 |
| list_deleted_files   | ListDeletedFilesMCPCommand  | (same)                                 |
| unmark_deleted_file  | UnmarkDeletedFileMCPCommand | (same)                                 |
| restore_deleted_files| RestoreDeletedFilesMCPCommand| (same)                                |
| collapse_versions    | CollapseVersionsMCPCommand  | (same)                                 |
| repair_database      | RepairDatabaseMCPCommand   | (same)                                 |
| read_project_text_file | ReadProjectTextFileCommand | `commands/read_project_text_file_command.py` |
| write_project_text_lines | WriteProjectTextLinesCommand | `commands/write_project_text_lines_command.py` |

---

## Log Viewer (`docs/commands/log_viewer/`)

| Command                   | Class                           | Source File                          |
|---------------------------|----------------------------------|--------------------------------------|
| view_worker_logs          | ViewWorkerLogsMCPCommand         | commands/log_viewer_mcp_commands.py  |
| list_worker_logs          | ListWorkerLogsMCPCommand         | (same)                               |
| list_logs                 | ListLogsMCPCommand               | (same)                               |
| rotate_worker_logs        | RotateWorkerLogsMCPCommand       | (same)                               |
| rotate_all_logs           | RotateAllLogsMCPCommand          | (same)                               |
| analyze_timing_bottlenecks| AnalyzeTimingBottlenecksMCPCommand| (same)                              |

---

## Project Management (`docs/commands/project_management/`)

| Command                 | Class                          | Source File                              |
|-------------------------|--------------------------------|------------------------------------------|
| change_project_id       | ChangeProjectIdMCPCommand     | commands/project_management_mcp_commands.py |
| create_project          | CreateProjectMCPCommand       | (same)                                    |
| delete_project          | DeleteProjectMCPCommand       | (same)                                    |
| delete_unwatched_projects| DeleteUnwatchedProjectsMCPCommand| (same)                                 |
| list_projects           | ListProjectsMCPCommand       | (same)                                    |
| list_watch_dirs         | ListWatchDirsMCPCommand      | (same)                                    |
| list_trashed_projects   | ListTrashedProjectsMCPCommand | (same)                                    |
| permanently_delete_from_trash | PermanentlyDeleteFromTrashMCPCommand | (same)                         |
| restore_project_from_trash    | RestoreProjectFromTrashMCPCommand    | (same)                         |
| clear_trash             | ClearTrashMCPCommand         | (same)                                    |
| run_project_script      | RunProjectScriptCommand      | commands/run_project_script_command.py     |
| run_project_module      | RunProjectModuleCommand      | commands/run_project_module_command.py     |
| project_pip_install     | ProjectPipInstallCommand     | commands/project_pip_commands.py           |
| project_pip_list        | ProjectPipListCommand        | (same)                                    |
| project_pip_show        | ProjectPipShowCommand        | (same)                                    |
| project_pip_uninstall   | ProjectPipUninstallCommand   | (same)                                    |
| project_pip_check       | ProjectPipCheckCommand       | (same)                                    |
| project_pip_search      | ProjectPipSearchCommand      | (same)                                    |

All `project_pip_*` commands **require** `project_id` (registered project); pip uses only that project’s `.venv` / `venv`. **`project_pip_install`** always runs via the job queue (`use_queue=True`); use `queue_get_job_status` with the returned `job_id`. **`project_pip_check`** also requires **`packages`**. List / show / uninstall / check / search are not queued.

---

## Refactor (`docs/commands/refactor/`)

| Command             | Class                      | Source File                        |
|---------------------|----------------------------|------------------------------------|
| file_structure      | FileStructureCommand       | commands/file_structure_command.py |
| extract_superclass  | ExtractSuperclassMCPCommand| commands/refactor_mcp_commands.py  |
| split_class         | SplitClassMCPCommand      | (same)                             |
| split_file_to_package| SplitFileToPackageMCPCommand| (same)                            |

---

## Repair Worker (`docs/commands/repair_worker/`)

| Command           | Class                      | Source File                          |
|-------------------|----------------------------|--------------------------------------|
| start_repair_worker| StartRepairWorkerMCPCommand| commands/repair_worker_mcp_commands.py |
| stop_repair_worker | StopRepairWorkerMCPCommand | (same)                               |
| repair_worker_status| RepairWorkerStatusMCPCommand| (same)                              |

---

## Search (`docs/commands/search/`)

| Command          | Class                    | Source File                        |
|------------------|--------------------------|------------------------------------|
| fulltext_search   | FulltextSearchMCPCommand | commands/search_mcp_commands.py    |
| list_class_methods| ListClassMethodsMCPCommand| (same)                            |
| find_classes     | FindClassesMCPCommand    | (same)                             |

---

## Vector (`docs/commands/vector/`)

| Command       | Class               | Source File                            |
|---------------|---------------------|----------------------------------------|
| rebuild_faiss | RebuildFaissCommand | commands/vector_commands/rebuild_faiss.py |
| revectorize   | RevectorizeCommand  | commands/vector_commands/revectorize.py  |

---

## Worker Management (`docs/commands/worker_management/`)

| Command      | Class                 | Source File                              |
|--------------|-----------------------|------------------------------------------|
| start_worker | StartWorkerMCPCommand | commands/worker_management_mcp_commands.py |
| stop_worker  | StopWorkerMCPCommand  | (same)                                   |

---

## Worker Status (`docs/commands/worker_status/`)

| Command             | Class                        | Source File                            |
|---------------------|------------------------------|----------------------------------------|
| get_worker_status   | GetWorkerStatusMCPCommand    | commands/worker_status_mcp_commands.py  |
| get_database_status | GetDatabaseStatusMCPCommand | (same)                                 |
| list_indexing_errors| ListIndexingErrorsMCPCommand| (same)                                 |

---

## Analysis (`docs/commands/analysis/`)

| Command               | Class                           | Source File                            |
|-----------------------|----------------------------------|----------------------------------------|
| analyze_complexity    | AnalyzeComplexityMCPCommand     | commands/analyze_complexity_mcp.py      |
| find_duplicates       | FindDuplicatesMCPCommand        | commands/find_duplicates_mcp.py       |
| comprehensive_analysis| ComprehensiveAnalysisMCPCommand | commands/comprehensive_analysis_mcp.py  |
| semantic_search       | SemanticSearchMCPCommand        | commands/semantic_search_mcp.py        |

---

## Miscellaneous (`docs/commands/misc/`)

| Command        | Class                | Source File                          |
|----------------|----------------------|--------------------------------------|
| check_vectors  | CheckVectorsCommand  | commands/check_vectors_command.py    |

*Removed commands: analyze_project, analyze_file, help, add_watch_dir, remove_watch_dir. Use update_indexes and comprehensive_analysis (with optional file_path) instead of analyze_project/analyze_file.*

---

Registration of all commands: `code_analysis/hooks.py` → `register_code_analysis_commands(reg)`. `code_analysis/hooks.py` → `register_code_analysis_commands(reg)`.
