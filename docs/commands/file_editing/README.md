# File editing commands (universal workflow)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Canonical entry point for viewing and editing project files via MCP.**

### Documentation tiers

| Tier | Source | Purpose |
|------|--------|---------|
| List | `list_servers` card | One-line server summary |
| Help | Server OpenAPI / tool_info | Quick start (6-step chain) |
| **Info** | Command `info` | Full guide: examples, format groups, errors |

```
call_server(..., command="info", params={})
```

See [EDITOR_GUIDE.md](EDITOR_GUIDE.md) and [WORKFLOW.md](WORKFLOW.md).

Thin-server lifecycle: CA `session_create` → open → preview ↔ edit → write preview → write commit → close.

| Step | Command | Role |
|------|---------|------|
| 0 | CA `session_create` | Agent obtains `session_id` |
| — | **`info`** | Optional: load full workflow guide |
| 1 | [`universal_file_open`](universal_file_open.md) | CA lock + download → workspace draft; `format_group` |
| 2 | [`universal_file_preview`](universal_file_preview.md) | Read-only navigation; `node_ref` from draft |
| 3 | [`universal_file_edit`](universal_file_edit.md) | Mutate draft only (no CA upload) |
| 4 | [`universal_file_write`](universal_file_write.md) | `write_mode=preview` then `write_mode=commit` |
| 5 | [`universal_file_close`](universal_file_close.md) | CA unlock + workspace cleanup (always) |

Full workflow, format groups, and rules: **[WORKFLOW.md](WORKFLOW.md)**.

Python-specific replace semantics: **[PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)**.

## AI model rules (short)

- Mandatory lifecycle: [standards/FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)
- **Coder brief (machine-readable):** [standards/UNIVERSAL_FILE_EDIT_CODER.yaml](../../standards/UNIVERSAL_FILE_EDIT_CODER.yaml)
- Extended rules: [AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md) §2
- Live parameter schemas: `help(server_id="ai-editor-server", command="<name>")`

## Registered vs legacy

**Registered** (thin server): `health`, `universal_file_preview`, `universal_file_open`, `universal_file_edit`, `universal_file_write`, `universal_file_close`.

**Not registered** (legacy / optional): `universal_file_search`, `universal_file_read/save/replace/delete`, CST tree commands — do not use for the MCP edit path.

| Removed / legacy | Use instead |
|------------------|-------------|
| `cst_load_file` → `cst_modify_tree` → `cst_save_tree` | open → edit → write → close |
| `query_cst`, `list_cst_blocks`, `cst_apply_buffer` | same |
| `read_project_text_file`, `write_project_text_lines` | universal_file_preview / edit session |
| `universal_file_search` (XPath) | preview drill-down |

## Design reference

- [plans/2026-05-16-universal-file-edit/source_spec.md](../../plans/2026-05-16-universal-file-edit/source_spec.md)
- [plans/2026-05-18-tree-sidecar/source_spec.md](../../plans/2026-05-18-tree-sidecar/source_spec.md)

## Command index

See [COMMANDS.md](COMMANDS.md).
