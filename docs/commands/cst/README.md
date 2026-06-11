# CST (Concrete Syntax Tree) Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

> **MCP / AI agents:** do **not** use this block for editing project files.  
> Use **[file_editing/](../file_editing/)** — `universal_file_preview` → `open` → (`universal_file_search` optional, Python XPath) → `edit` → `write` → `close`.

CST commands stay registered for **server development, scripts, and tests**. They operate on in-memory `tree_id` sessions separate from the universal edit session.

## Commands → File Mapping

| MCP Command Name   | Class                     | Source File                              |
|--------------------|---------------------------|------------------------------------------|
| get_file_lines     | GetFileLinesCommand        | `commands/get_file_lines_command.py`     |
| cst_load_file      | CSTLoadFileCommand        | `commands/cst_load_file_command.py`      |
| cst_save_tree      | CSTSaveTreeCommand        | `commands/cst_save_tree_command.py`      |
| cst_reload_tree    | CSTReloadTreeCommand      | `commands/cst_reload_tree_command.py`    |
| cst_find_node      | CSTFindNodeCommand        | `commands/cst_find_node_command.py`      |

**AI agents:** for XPath on an **open edit-session** tree, use [`universal_file_search`](../file_editing/universal_file_search.md) (`session_id`), not `cst_find_node` (`tree_id`).

| cst_get_node_info  | CSTGetNodeInfoCommand     | `commands/cst_get_node_info_command.py`  |
| cst_get_node_by_range| CSTGetNodeByRangeCommand| `commands/cst_get_node_by_range_command.py`|
| cst_get_node_at_line| CSTGetNodeAtLineCommand  | `commands/cst_get_node_at_line_command.py`|
| cst_modify_tree    | CSTModifyTreeCommand      | `commands/cst_modify_tree_command.py`    |
| cst_apply_buffer   | CSTApplyBufferCommand     | `commands/cst_apply_buffer_command.py` |
| cst_create_file    | CSTCreateFileCommand     | `commands/cst_create_file_command.py`    |
| cst_convert_and_save| CSTConvertAndSaveCommand| `commands/cst_convert_and_save_command.py`|
| list_cst_blocks    | ListCSTBlocksCommand      | `commands/list_cst_blocks_command.py`    |
| query_cst          | QueryCSTCommand           | `commands/query_cst_command.py`          |

Registration: `code_analysis/hooks.py` (`register_auto_import_module`).

## AI editing path

See [file_editing/PYTHON_EDIT_SEMANTICS.md](../file_editing/PYTHON_EDIT_SEMANTICS.md) for how the universal sidecar path applies the same CST modifier (header-only replace, batch rules).

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.

Legacy workflow guide (redirect): [CST_WORKFLOW_GUIDE.md](../../CST_WORKFLOW_GUIDE.md).
