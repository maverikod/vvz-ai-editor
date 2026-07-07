"""
Detailed editor workflow guide returned by the ``info`` command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

GUIDE_VERSION = "1.0"

EDITOR_INFO_MARKDOWN = """\
# AI Editor — file edit guide (thin-server)

## Architecture

AI Editor is a **thin MCP server** between the agent and **Code Analysis Server (CA)**:

- The agent obtains `session_id` from CA **`session_create`** and passes the same id to every `universal_file_*` call.
- `universal_file_open` **does not** generate `session_id`; it echoes the CA id.
- Existing files are **locked** on open and **unlocked** on close.
- New files opened with `create=true` stay as a local draft until the first commit.
- The editor keeps a **workspace draft** under `{workspace_root}/{session_id}/`.
- Changes reach CA **only** on `universal_file_write` with `write_mode=commit`.
- `universal_file_edit` mutates the draft only; CA canonical bytes are unchanged until commit.

## Registered commands

| Command | Role |
|---------|------|
| `health` | Server liveness and dependency checks |
| `info` | This guide (detailed workflow) |
| `universal_file_open` | Existing file: CA lock + download; new file: local draft |
| `universal_file_preview` | Read-only navigation; `node_ref` from draft or one-shot CA read |
| `universal_file_edit` | Apply operations to draft |
| `universal_file_write` | Preview diff or commit (validate → CA upload) |
| `universal_file_close` | CA unlock + workspace cleanup (always) |

**Not registered** in the thin server: legacy CST/save commands and session git/undo helpers. Use `universal_file_search` (Python) or preview drill-down for navigation.

## Lifecycle (edit one file)

```
CA: session_create  →  session_id

universal_file_open(project_id, file_path, session_id)
universal_file_preview(project_id, file_path, session_id)   # repeat after text edits
universal_file_edit(project_id, session_id, operations)       # repeat preview↔edit
universal_file_write(..., write_mode=preview)
universal_file_write(..., write_mode=commit)
universal_file_close(project_id, session_id)                  # always, including abort
```

### Step 0 — CA session

```
session_create  →  { "session_id": "<uuid>" }
list_projects   →  project_id (if unknown)
```

### Step 1 — open

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "file_path": "src/example.py",
  "session_id": "<ca-session-id>"
}
```

Response highlights: `format_group`, `draft_path`, `multi_file_bundle`.

- Existing file: CA `lock_file_and_download` is mandatory; lock failure is an open error.
- New file: `create=true`, `initial_content` (required for `.py`); no CA registration/lock happens until write commit.
- Unknown extension (e.g. `Makefile`, `.env`): pass `format_group` (`sidecar` / `tree-temp` / `text`) to force a handler; omitting it returns `UNKNOWN_FORMAT`.

Errors: `FILE_ALREADY_OPEN`, `OPEN_ERROR`, `SESSION_NOT_FOUND`, `UNKNOWN_FORMAT`.

### Step 2 — preview

**After open (workspace draft):**

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "file_path": "src/example.py",
  "session_id": "<ca-session-id>",
  "node_ref": ""
}
```

- Read-only; **no** flake8/mypy/docstring validation.
- Each block has `node_ref` for drill-down (marked-tree: **integer short_id**; see format table).
- If file is open but `session_id` omitted → `OPEN_FILE_USE_WORKSPACE_PREVIEW`.

**One-shot (file not open):** omit `session_id`; uses CA `download_without_lock`.

### Step 3 — edit

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "session_id": "<ca-session-id>",
  "operations": [
    {
      "type": "replace",
      "node_id": "5",
      "code_lines": [
        "def hello() -> str:",
        "    \"\"\"Say hello.\"\"\"",
        "    return \"hello\""
      ]
    }
  ]
}
```

Draft changes only. Origin snapshot and CA file unchanged.

### Step 4 — write preview

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "session_id": "<ca-session-id>",
  "file_path": "src/example.py",
  "write_mode": "preview"
}
```

Returns unified `diff`. No validation, no CA upload.

### Step 5 — write commit

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "session_id": "<ca-session-id>",
  "file_path": "src/example.py",
  "write_mode": "commit"
}
```

- Existing file, equal to origin → reaffirm CA lock, then `unchanged=true`.
- Existing file, diff → pre-write validation → reaffirm CA lock → `upload_session_file_content` on success.
- New file → create/register+lock on CA atomically, then upload on success.
- Python validation: black-parseable, flake8, mypy, docstrings.
- Failure → `VALIDATION_ERROR`; fix via edit and retry.

### Step 6 — close

```json
{
  "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
  "session_id": "<ca-session-id>"
}
```

Always call, including after failed commit or cancel. Uncommitted draft is discarded.

## Format groups

| format_group | Extensions | Preview `node_ref` | Edit field |
|--------------|------------|--------------------|------------|
| sidecar | `.py`, `.pyi`, `.pyw` | **int short_id** (marked-tree) | `node_id` + `code_lines` (int string from preview or search) |
| tree-temp | `.json`, `.yaml`, `.yml`, … | **int short_id** (marked-tree) or JSON Pointer (legacy) | `node_ref` / `short_id` or `json_pointer` + `value` |
| text | `.md`, `.txt`, `.rst`, `.adoc` | int short_id (`.md`) or line index (`.txt`) | `node_ref` + `content` or `start_line`/`end_line` |
| invalid | any (parse error) | none — line pagination | line-based `content` / `start_line` |

For files with unknown or absent extensions, pass `format_group` in `universal_file_open` to override auto-detection. The parameter is ignored when the extension is already recognised.

### Python (sidecar) example — insert method

```json
{
  "type": "insert",
  "target_node_id": "3",
  "position": "after",
  "code_lines": ["", "def new_method(self) -> None:", "    pass"]
}
```

Do not combine parent + child nodes in one batch (`NESTED_BATCH_FORBIDDEN`).

### JSON/YAML example

```json
{"type": "replace", "node_ref": "3", "value": 60}
{"type": "replace", "json_pointer": "/timeout", "value": 60}
{"type": "insert", "parent_json_pointer": "/items/-", "value": {"id": 1}}
```

Marked-tree: pass int short_id as string in `node_ref`. Legacy tree-temp: use `json_pointer`.

### Text example

```json
{"type": "replace", "node_ref": "4", "content": "## Setup\\n\\nUpdated.\\n"}
{"type": "replace", "node_ref": "intro.setup", "content": "## Setup\\n\\nUpdated.\\n"}
```
```

Re-preview after each edit before the next line-targeted operation.

## Multi-file CA session

One `session_id` may hold several files. Pass `file_path` on edit / write / close when `multi_file_bundle.open_file_count > 1`.

## Parse-error fallback

If structured parse fails on open: `is_invalid=true`, line-based editing until successful commit restores structural mode.

## Error recovery

| Error | Action |
|-------|--------|
| `VALIDATION_ERROR` on commit | edit → write preview → write commit |
| `UPSTREAM_LOCK_FAILED` | lock was missing/denied; re-open or resolve the CA session/lock before retry |
| `UPSTREAM_UPLOAD_FAILED` | fix content/connectivity; retry commit or close |
| Cancel uncommitted work | `universal_file_close` without commit |
| Server restart | local bundle lost; open again |

## Forbidden

- Direct IDE/bash edits on project files when this server is available.
- `write_mode=commit` without a preceding preview in the same session.
- Reusing text line numbers after a prior edit without re-preview.
- Expecting `open` to return a new session id (use CA `session_create`).

## Documentation

- Prose: `docs/commands/file_editing/WORKFLOW.md`
- Machine brief: `docs/standards/UNIVERSAL_FILE_EDIT_CODER.yaml`
- Per-command schemas: `help(command="universal_file_<name>")`
"""


def build_editor_info_payload() -> Dict[str, Any]:
    """Build structured payload for the ``info`` command."""
    lifecycle: List[Dict[str, str]] = [
        {
            "step": "0",
            "name": "CA session_create",
            "command": "session_create (Code Analysis Server)",
            "note": "Agent obtains session_id; reused on all universal_file_* calls",
        },
        {
            "step": "1",
            "name": "open",
            "command": "universal_file_open",
            "note": "CA lock + download; returns format_group, draft_path",
        },
        {
            "step": "2",
            "name": "preview",
            "command": "universal_file_preview",
            "note": "node_ref from draft; read-only; re-run after text edits",
        },
        {
            "step": "3",
            "name": "edit",
            "command": "universal_file_edit",
            "note": "operations batch; draft only",
        },
        {
            "step": "4a",
            "name": "write preview",
            "command": "universal_file_write",
            "note": "write_mode=preview; diff only",
        },
        {
            "step": "4b",
            "name": "write commit",
            "command": "universal_file_write",
            "note": "write_mode=commit; validate then CA upload",
        },
        {
            "step": "5",
            "name": "close",
            "command": "universal_file_close",
            "note": "always; unlock CA; discard uncommitted draft",
        },
    ]
    return {
        "guide_version": GUIDE_VERSION,
        "architecture": "thin-server",
        "summary": (
            "CA session_create → open → preview ↔ edit → write preview → "
            "write commit → close. session_id from CA on every step."
        ),
        "markdown": EDITOR_INFO_MARKDOWN,
        "lifecycle": lifecycle,
        "registered_commands": [
            "health",
            "info",
            "universal_file_preview",
            "universal_file_open",
            "universal_file_edit",
            "universal_file_write",
            "universal_file_close",
        ],
        "format_groups": {
            "sidecar": {
                "extensions": [".py", ".pyi", ".pyw"],
                "preview_node_ref": "integer MAP short_id (marked-tree; preview and search)",
                "edit_fields": "node_id (int short_id string from preview or search), code_lines",
                "force_hint": "pass format_group=sidecar for unknown-extension files to route via Python CST",
            },
            "tree-temp": {
                "extensions": [".json", ".yaml", ".yml", ".jsonl", ".ndjson"],
                "preview_node_ref": "integer short_id (marked-tree) or JSON Pointer (legacy)",
                "edit_fields": "node_ref/short_id or json_pointer, value",
                "force_hint": "pass format_group=tree-temp for unknown-extension files to route via JSON/YAML tree",
            },
            "text": {
                "extensions": [".md", ".txt", ".rst", ".adoc"],
                "preview_node_ref": "int short_id (.md) or zero-based line index (.txt)",
                "edit_fields": "node_ref or start_line/end_line, content",
                "force_hint": "pass format_group=text for unknown-extension files (Makefile, .env, .sh, …) to route via plain-text line editing",
            },
            "invalid_fallback": {
                "extensions": ["any on parse error"],
                "preview_node_ref": "empty — use preview_offset line pagination",
                "edit_fields": "line-based content or start_line/end_line",
            },
        },
        "examples": {
            "open": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "file_path": "src/example.py",
                "session_id": "<ca-session-id>",
            },
            "preview": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "file_path": "src/example.py",
                "session_id": "<ca-session-id>",
            },
            "edit_python_replace": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "session_id": "<ca-session-id>",
                "operations": [
                    {
                        "type": "replace",
                        "node_id": "5",
                        "code_lines": ["def f() -> str:", '    return "ok"'],
                    }
                ],
            },
            "write_preview": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "session_id": "<ca-session-id>",
                "file_path": "src/example.py",
                "write_mode": "preview",
            },
            "write_commit": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "session_id": "<ca-session-id>",
                "file_path": "src/example.py",
                "write_mode": "commit",
            },
            "close": {
                "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                "session_id": "<ca-session-id>",
            },
        },
        "docs": {
            "workflow": "docs/commands/file_editing/WORKFLOW.md",
            "coder_brief": "docs/standards/UNIVERSAL_FILE_EDIT_CODER.yaml",
            "help_hint": 'help(server_id="ai-editor-server", command="<name>")',
        },
    }
