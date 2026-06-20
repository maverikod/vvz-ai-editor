"""
Presentation tiers for AI Editor thin-server workflow.

- SERVER_LIST_DESCRIPTION: proxy ``list_servers`` card (brief).
- SERVER_HELP_DESCRIPTION: OpenAPI / server-level ``help`` (enough to start).
- WORKFLOW_STEPS_TEXT: one-line list embedded in command metadata.
- WORKFLOW_BRIEF_HELP: same lifecycle block (alias for help tier).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

# Brief card in MCP Proxy list_servers.
SERVER_LIST_DESCRIPTION = (
    "Thin MCP server: edit project files (.py, JSON/YAML, Markdown, text) via "
    "Code Analysis Server lock/upload. Lifecycle: open → preview → edit → write → close. "
    "Call `info` for the full guide; `help(command=...)` for parameter schemas."
)

# Server-level help (OpenAPI tool_info) — enough for a model to start working.
SERVER_HELP_DESCRIPTION = """\
Thin MCP server for universal file editing via Code Analysis Server (CA).

### Quick start (edit one file)

0. **CA** `session_create` → `session_id` (you supply this on every step; `open` does not create it).
1. `universal_file_open(project_id, file_path, session_id)` — lock on CA, workspace draft.
2. `universal_file_preview(project_id, file_path, session_id)` — get `node_ref` targets from draft.
3. `universal_file_edit(project_id, session_id, operations)` — mutate draft only.
4. `universal_file_write(..., write_mode=preview)` — diff only (no validation, no CA upload).
5. `universal_file_write(..., write_mode=commit)` — validate, then upload to CA if changed.
6. `universal_file_close(project_id, session_id)` — always (unlock CA, cleanup workspace).

**Multi-file session:** pass `file_path` on edit / write / close when more than one file is open.

**Read-only without open:** `universal_file_preview(project_id, file_path)` — one-shot CA read.

**Full guide (examples, format groups, errors):** command `info`.

**Per-command parameters:** `help(server_id="ai-editor-server", command="universal_file_open")`.

### MCP Proxy
- `list_projects` → `project_id`
- `call_server(server_id="ai-editor-server", copy_number=1, command="<name>", params={...})`
- Project-relative `file_path` only; do not pass host `root_dir`.
"""

WORKFLOW_BRIEF_HELP = SERVER_HELP_DESCRIPTION

WORKFLOW_STEPS_TEXT = (
    "universal file edit workflow:\n"
    "  0. CA session_create → session_id (agent supplies on every step)\n"
    "  1. universal_file_open(project_id, file_path, session_id) — CA lock+download; workspace draft\n"
    "  2. universal_file_preview(project_id, file_path, session_id) — node_ref from draft\n"
    "  3. universal_file_edit(project_id, session_id, operations) — draft only\n"
    "  4. universal_file_write(..., write_mode=preview) — diff only\n"
    "  5. universal_file_write(..., write_mode=commit) — validate then CA upload\n"
    "  6. universal_file_close(project_id, session_id) — always\n"
    "  Full guide: command info\n"
)
