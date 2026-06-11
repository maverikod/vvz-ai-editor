# universal_file_open

**Command:** `universal_file_open`  
**Class:** `UniversalFileOpenCommand`  
**Source:** `code_analysis/commands/universal_file_edit/open_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Start an in-memory edit session for one project file. Returns **`session_id`** and **`format_group`** (`sidecar` | `tree-temp` | `text`).

**Workflow step 2.** See [WORKFLOW.md](WORKFLOW.md). Optional next step for Python: [universal_file_search.md](universal_file_search.md) (XPath on session tree).

On open:

- Deletes stale `<file>.write` lockfile and `<file>.draft` (preserves Python `.cst_sidecar`).
- Creates initial backup when the file has no backup history.
- Unparseable structured files open in line-based fallback (`is_invalid: true`).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID |
| `file_path` | string | **Yes** | Project-relative path |
| `create` | boolean | No | Create file if missing (default false) |
| `initial_content` | string | No | Required for new `.py`; optional for JSON/YAML/text |

---

## Returned data

### Success

- `session_id` — UUID for edit/write/close/preview-with-draft
- `format_group` — determines operation shape in `universal_file_edit`
- `file_path`, `handler_id`
- `is_invalid`, `fallback_reason`, `warning` when parse fallback applies

### Error

`FILE_NOT_FOUND`, `PARSE_ERROR`, `UNKNOWN_FORMAT`, `SESSION_ALREADY_OPEN`, …

---

## Examples

**Open existing Python file**

```json
{"project_id": "<uuid>", "file_path": "pkg/module.py"}
```

**Create new Python file**

```json
{
  "project_id": "<uuid>",
  "file_path": "pkg/new_module.py",
  "create": true,
  "initial_content": "\"\"\"New module.\"\"\"\n\n\ndef main() -> None:\n    pass\n"
}
```

---

## Best practices

- One session per file until `universal_file_close`.
- After server restart, `session_id` is invalid — open again.
- `session_id` here is **not** client `session_create` / `session_open_file`.

---

## See also

- [universal_file_search.md](universal_file_search.md)
- [universal_file_preview.md](universal_file_preview.md)
- [universal_file_edit.md](universal_file_edit.md)
