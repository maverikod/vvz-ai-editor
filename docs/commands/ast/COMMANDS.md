# AST Commands — Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Each command is described in a separate file: purpose, arguments, return format, and examples (correct and incorrect).

| Command | Description | Doc |
|---------|-------------|-----|
| get_ast | Retrieve stored AST for a file | [get_ast.md](get_ast.md) |
| search_ast_nodes | Search AST nodes by type in project/files | [search_ast_nodes.md](search_ast_nodes.md) |
| ast_statistics | AST statistics for project or file | [ast_statistics.md](ast_statistics.md) |
| list_project_files | List `.py` files (filesystem-first); DB enrichment by path; venv skipped by default | [list_project_files.md](list_project_files.md) |
| get_code_entity_info | Detailed info about class/function/method | [get_code_entity_info.md](get_code_entity_info.md) |
| list_code_entities | List code entities in file or project | [list_code_entities.md](list_code_entities.md) |
| get_imports | Imports information from files or project | [get_imports.md](get_imports.md) |
| find_dependencies | Where classes/functions/modules are used | [find_dependencies.md](find_dependencies.md) |
| get_entity_dependencies | Dependencies of an entity by id (what it calls) | [get_entity_dependencies.md](get_entity_dependencies.md) |
| get_entity_dependents | Dependents of an entity by id (what calls it) | [get_entity_dependents.md](get_entity_dependents.md) |
| get_class_hierarchy | Class hierarchy (inheritance tree) | [get_class_hierarchy.md](get_class_hierarchy.md) |
| find_usages | Usages of methods, properties, classes, functions | [find_usages.md](find_usages.md) |
| export_graph | Export dependency/hierarchy/call graphs (JSON/DOT) | [export_graph.md](export_graph.md) |

See also [README.md](README.md) for block overview and command→file mapping.
