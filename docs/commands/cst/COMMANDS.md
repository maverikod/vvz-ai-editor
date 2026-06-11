# CST Commands — Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

> **MCP AI editing:** use [file_editing/](../file_editing/) instead of CST tree commands.

Each command is described in a separate file: purpose, arguments, return format, and examples.

| Command | Description | Doc |
|---------|-------------|-----|
| get_file_lines | Raw file lines in range (no parsing) | [get_file_lines.md](get_file_lines.md) |
| cst_load_file | Load file into CST tree | [cst_load_file.md](cst_load_file.md) |
| cst_save_tree | Save CST tree to file (atomic) | [cst_save_tree.md](cst_save_tree.md) |
| cst_reload_tree | Reload CST tree from file | [cst_reload_tree.md](cst_reload_tree.md) |
| cst_find_node | Find nodes in CST tree | [cst_find_node.md](cst_find_node.md) |
| cst_get_node_info | Detailed info about a node | [cst_get_node_info.md](cst_get_node_info.md) |
| cst_get_node_by_range | Node ID for a line range | [cst_get_node_by_range.md](cst_get_node_by_range.md) |
| cst_get_node_at_line | Node at line + parent in one call | [cst_get_node_at_line.md](cst_get_node_at_line.md) |
| cst_modify_tree | Modify CST tree (atomic ops) | [cst_modify_tree.md](cst_modify_tree.md) |
| cst_apply_buffer | Apply buffered code via CST replace-ops | (see server `help`; same selector shapes as tree workflow) |
| cst_create_file | Create new Python file with docstring | [cst_create_file.md](cst_create_file.md) |
| cst_convert_and_save | Convert source to CST, save to DB | [cst_convert_and_save.md](cst_convert_and_save.md) |
| list_cst_blocks | List CST blocks for file/tree | [list_cst_blocks.md](list_cst_blocks.md) |
| query_cst | Run CST query (selector) on tree | [query_cst.md](query_cst.md) |

See [README.md](README.md) for block overview.
