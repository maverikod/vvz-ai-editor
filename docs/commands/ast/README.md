# AST Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for working with Abstract Syntax Tree: query, search, statistics, entities, imports, dependencies, hierarchy, usages, graph export.

## Commands → File Mapping

| MCP Command Name       | Class                     | Source File                          |
|------------------------|---------------------------|--------------------------------------|
| get_ast                | GetASTMCPCommand          | `commands/ast/get_ast.py`            |
| search_ast_nodes       | SearchASTNodesMCPCommand  | `commands/ast/search_nodes.py`       |
| ast_statistics         | ASTStatisticsMCPCommand  | `commands/ast/statistics.py`         |
| list_project_files     | ListProjectFilesMCPCommand| `commands/ast/list_files.py`        |
| get_code_entity_info   | GetCodeEntityInfoMCPCommand| `commands/ast/entity_info.py`       |
| list_code_entities     | ListCodeEntitiesMCPCommand| `commands/ast/list_entities.py`     |
| get_imports            | GetImportsMCPCommand      | `commands/ast/imports.py`            |
| find_dependencies      | FindDependenciesMCPCommand| `commands/ast/dependencies.py`      |
| get_class_hierarchy    | GetClassHierarchyMCPCommand| `commands/ast/hierarchy.py`        |
| find_usages            | FindUsagesMCPCommand      | `commands/ast/usages.py`            |
| export_graph           | ExportGraphMCPCommand     | `commands/ast/graph.py`             |

All commands inherit from `BaseMCPCommand`; registration: `code_analysis/hooks.py` → `ast_mcp_commands`; re-export: `commands/ast/__init__.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
