# CST Workflow Guide (superseded)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

> **This guide is obsolete for MCP / AI editing.**

Use the universal file workflow instead:

| Doc | Content |
|-----|---------|
| [commands/file_editing/WORKFLOW.md](commands/file_editing/WORKFLOW.md) | Full open → edit → write → close lifecycle |
| [commands/file_editing/PYTHON_EDIT_SEMANTICS.md](commands/file_editing/PYTHON_EDIT_SEMANTICS.md) | Signature-only replace, insert/delete, batch rules, session tree search |
| [AI_TOOL_USAGE_RULES.md](AI_TOOL_USAGE_RULES.md) §2 | AI model rules |
| [standards/FILE_EDIT_WORKFLOW.yaml](standards/FILE_EDIT_WORKFLOW.yaml) | Mandatory lifecycle |

**Do not use** for editing: `cst_load_file` → `cst_modify_tree` → `cst_save_tree`, `query_cst`, `cst_apply_buffer`, `write_project_text_lines`, `replace_file_lines`.

---

## Internal CST APIs (server developers)

CST commands remain registered for tooling and tests. Per-command reference: [commands/cst/](commands/cst/).

| Task | Internal command |
|------|------------------|
| Batch tree edits in memory | `cst_load_file` → `cst_modify_tree` → `cst_save_tree` |
| XPath on loaded tree (`tree_id`) | `cst_find_node` — legacy; AI agents use `universal_file_search` in edit session |
| Selector-based single patch | `query_cst`, `cst_apply_buffer` |
| Header-only vs full replace flag | `cst_modify_tree` op field `replace_all_child_nodes` — see [cst_modify_tree.md](commands/cst/cst_modify_tree.md) |
| File with syntax errors (no parse) | Universal edit session opens in line fallback, or fix minimal range then reopen |

Historical analysis: [reports/CST_USABILITY_IMPROVEMENTS.md](reports/CST_USABILITY_IMPROVEMENTS.md).
