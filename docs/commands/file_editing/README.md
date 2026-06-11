# File editing commands (universal workflow)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Canonical entry point for viewing and editing project files via MCP.**

All supported formats (Python, JSON, YAML, Markdown, plain text, …) use one lifecycle:

| Step | Command | Role |
|------|---------|------|
| 1 | [`universal_file_preview`](universal_file_preview.md) | Read-only navigation; obtain `node_ref` targets |
| 2 | [`universal_file_open`](universal_file_open.md) | Start edit session → `session_id`, `format_group` |
| 2b | [`universal_file_search`](universal_file_search.md) | Optional; XPath on session CST tree (Python sidecar) |
| 3 | [`universal_file_edit`](universal_file_edit.md) | Mutate in-memory draft (disk unchanged) |
| 4 | [`universal_file_write`](universal_file_write.md) | Preview diff, then commit |
| 5 | [`universal_file_close`](universal_file_close.md) | Release session; reconcile sidecar/draft |

Full workflow, format groups, and rules: **[WORKFLOW.md](WORKFLOW.md)**.

Python-specific replace semantics (signature-only, docstrings, batch rules): **[PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)**.

## AI model rules (short)

- Mandatory lifecycle: [standards/FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)
- **Coder brief (machine-readable):** [standards/UNIVERSAL_FILE_EDIT_CODER.yaml](../../standards/UNIVERSAL_FILE_EDIT_CODER.yaml)
- Extended rules: [AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md) §2
- Live parameter schemas: `help(server_id="code-analysis-server", command="<name>")`

## Do not use for editing (obsolete MCP workflow)

| Removed / legacy | Use instead |
|------------------|-------------|
| `cst_load_file` → `cst_modify_tree` → `cst_save_tree` | `open` → `edit` → `write` → `close` |
| `query_cst`, `list_cst_blocks`, `cst_apply_buffer` | same |
| `cst_find_node` (legacy `tree_id` XPath) | `universal_file_search` in edit session, or preview drill-down |
| `read_project_text_file`, `write_project_text_lines` | `universal_file_preview` / universal edit session |
| `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete` | same |

CST command docs under [../cst/](../cst/) describe **internal/server developer APIs** still registered for tooling — not the MCP editing path for AI agents.

## Design reference

- [plans/2026-05-16-universal-file-edit/source_spec.md](../../plans/2026-05-16-universal-file-edit/source_spec.md) — draft models, sidecar, two-phase write
- [plans/2026-05-18-tree-sidecar/source_spec.md](../../plans/2026-05-18-tree-sidecar/source_spec.md) — sidecar + preview integration

## Command index

See [COMMANDS.md](COMMANDS.md).
