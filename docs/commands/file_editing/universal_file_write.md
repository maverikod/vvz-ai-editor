# universal_file_write

**Command:** `universal_file_write`  
**Class:** `UniversalFileWriteCommand`  
**Source:** `ai_editor/commands/universal_file_edit/write_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Compare workspace draft (canonical export) to origin snapshot, show a unified diff, and optionally **commit** to Code Analysis Server.

**Workflow steps 4a–4b.** Always call `write_mode=preview` before `write_mode=commit` ([FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)).

---

## Write modes

| write_mode | Effect |
|------------|--------|
| `preview` (default) | Unified diff only; **no** validation; **no** CA upload |
| `commit` | Pre-write validation → CA upload when content differs; `unchanged=true` when equal (no CA RPC) |

### Pre-write validation (commit only)

For Python and structured files: serialize to temp → quality tools (black-parseable, flake8, Ruff, mypy) → handler validator (docstrings, JSON/YAML parse). On failure: `VALIDATION_ERROR`; origin and draft unchanged.

### Sidecar legacy (`.py`, `write_mode` omitted)

Two-phase PID lockfile: first call → preview + lock; second call (same server PID) → commit. Prefer explicit `write_mode=preview` then `commit`.

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (CA upload) |
| `session_id` | string | **Yes** | CA session id |
| `file_path` | string | Conditional | Required when session has multiple open files |
| `write_mode` | string | No | `preview` (default) or `commit` |
| `format_python` | boolean | No | Run black on export before diff/upload |
| `verify_after_upload` | boolean | No | Read-back from CA after successful upload |

---

## Returned data

### Success (preview)

- `phase`: `preview`
- `has_changes`, `diff`
- `uploaded`: false

### Success (commit)

- `phase`: `committed`
- `unchanged`, `uploaded`, `has_changes`, `diff`
- Optional `ca_verify` when `verify_after_upload=true`

### Error

`VALIDATION_ERROR`, `UPSTREAM_UPLOAD_FAILED`, `SESSION_NOT_FOUND`, `SESSION_FILE_PATH_REQUIRED`, `WRITE_FAILED`

---

## Examples

**Preview diff**

```json
{
  "project_id": "<uuid>",
  "session_id": "<ca-session-id>",
  "file_path": "pkg/module.py",
  "write_mode": "preview"
}
```

**Commit to CA**

```json
{
  "project_id": "<uuid>",
  "session_id": "<ca-session-id>",
  "file_path": "pkg/module.py",
  "write_mode": "commit"
}
```

---

## Related

- [WORKFLOW.md](WORKFLOW.md)
- [universal_file_close.md](universal_file_close.md) — always call after commit or abort

Schema source: `help(server_id="ai-editor-server", command="universal_file_write")`.
