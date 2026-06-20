# universal_file_open

**Command:** `universal_file_open`  
**Class:** `UniversalFileOpenCommand`  
**Source:** `ai_editor/commands/universal_file_edit/open_command.py`  
**Category:** universal_file_edit

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Lock a project file on Code Analysis Server (CA), download bytes into the editor workspace, and start an in-memory edit session.

**Workflow step 1** (after CA `session_create`). See [WORKFLOW.md](WORKFLOW.md).

Returns **`format_group`** (`sidecar` | `tree-temp` | `text`), `draft_path`, and `multi_file_bundle`.

**`session_id` is required input** — the CA id from `session_create`. Open echoes it; it does not generate a new id.

On open:

- CA: `lock_file_and_download` (existing file) or `upload_create_and_lock` (`create=True`).
- Workspace: origin snapshot + draft under `{workspace_root}/{session_id}/`.
- Unparseable structured files may open in line-based fallback (`is_invalid: true`).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID |
| `file_path` | string | **Yes** | Project-relative path |
| `session_id` | string | **Yes** | CA session id from `session_create` |
| `create` | boolean | No | Create file on CA if missing (default false) |
| `initial_content` | string | No | Required for new `.py`; optional for JSON/YAML/text |

---

## Returned data

### Success

- `session_id` — echo of CA session id
- `format_group` — determines operation shape in `universal_file_edit`
- `file_path`, `session_dir`, `draft_path`, `available_operations`
- `multi_file_bundle` — open files in this CA session
- `is_invalid`, `fallback_reason`, `warning` when parse fallback applies

### Error

`FILE_ALREADY_OPEN`, `OPEN_ERROR`, `PARSE_ERROR`, `UNKNOWN_FORMAT`, `SESSION_NOT_FOUND`, …

---

## Examples

**Open existing file**

```json
{
  "project_id": "<uuid>",
  "file_path": "pkg/module.py",
  "session_id": "<ca-session-create-id>"
}
```

**Create new Python module**

```json
{
  "project_id": "<uuid>",
  "file_path": "pkg/new_module.py",
  "session_id": "<ca-session-create-id>",
  "create": true,
  "initial_content": "\"\"\"New module.\"\"\"\n"
}
```

---

## Next steps

1. `universal_file_preview(..., session_id)` — obtain `node_ref` values from draft  
2. `universal_file_edit` — apply operations  
3. `universal_file_write` — preview then commit  
4. `universal_file_close` — always

Schema source: `help(server_id="ai-editor-server", command="universal_file_open")`.
