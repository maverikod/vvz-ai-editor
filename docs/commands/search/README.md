# Search Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for fulltext and structural search: fulltext search, list class methods, find classes.

**Overview of all search types (fulltext, semantic, AST, CST, usages, etc.):** [SEARCH_TYPES.md](../SEARCH_TYPES.md).

## Commands → File Mapping

| MCP Command Name   | Class                    | Source File                        |
|--------------------|--------------------------|------------------------------------|
| fulltext_search    | FulltextSearchMCPCommand  | `commands/search_mcp_commands.py`   |
| list_class_methods | ListClassMethodsMCPCommand| (same)                             |
| find_classes       | FindClassesMCPCommand    | (same)                             |

Internal: `SearchCommand` in `commands/search.py`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
