# universal_file_preview

**Command:** `universal_file_preview`  
**Class:** `UniversalFilePreviewCommand`  
**Source:** `code_analysis/commands/universal_file_preview_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Read-only structured view of any supported project file. Returns navigable blocks with stable **`node_ref`** values used by `universal_file_edit`.

- Does **not** modify disk, database, or edit sessions (except loading draft state when `session_id` is passed).
- Works **without** an edit session for initial inspection.
- Supported: `.py`, `.json`, `.yaml`, `.yml`, `.md`, `.txt`, `.rst`, `.adoc`, `.jsonl`, `.ndjson`.

**Workflow:** Step 2 after open (or one-shot read before open). See [WORKFLOW.md](WORKFLOW.md).

Two modes:

- **Workspace draft** — pass `session_id` (CA id) after `universal_file_open`; reads current draft.
- **One-shot** — omit open; `project_id` + `file_path` only; CA `download_without_lock` (read-only, no lock).

If the file is already open but `session_id` is omitted → `OPEN_FILE_USE_WORKSPACE_PREVIEW`.

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID from `list_projects` |
| `file_path` | string | **Yes** | Project-relative path; no globs |
| `node_ref` | string | No | Drill-down target from a prior response; omit for file root |
| `session_id` | string | No | CA session id — after open, preview **draft**; optional on one-shot read |
| `selector` | string or array | No | Slice blocks: `"0:5"`, `"-3:"`, or explicit block ids |
| `preview_lines` | integer | No | Max blocks at root (default 20) |
| `full_text_max_lines` | integer | No | Python: return full source as one block when file is shorter (default 200) |

Schema source: `get_schema()` on the command class.

---

## node_ref format

| File type | node_ref example | Used in edit as |
|-----------|------------------|-----------------|
| Python | `a1b2c3d4-…` (UUID) | `node_id` |
| JSON/YAML | `/database/host` | `json_pointer` |
| Markdown | `intro.setup` | `node_ref` |
| Plain text | `"3"` (line index) | `node_ref` or `start_line = int(node_ref) + 1` |

---

## Returned data

### Success

- `blocks[]` — navigable children with `node_ref`, labels, kinds
- `focus` — current node metadata; `focus.text` — rendered snippet or diff when draft ≠ disk (Python session)
- `can_expand`, pagination hints per handler

### Error

Common codes: `FILE_NOT_FOUND`, `PARSE_ERROR`, `UNKNOWN_NODE_REF`, `SESSION_NOT_FOUND`.

---

## Examples

**Root preview**

```json
{"project_id": "<uuid>", "file_path": "src/service.py"}
```

**Drill into class**

```json
{
  "project_id": "<uuid>",
  "file_path": "src/service.py",
  "node_ref": "<class-uuid-from-blocks>"
}
```

**Preview draft during edit session**

```json
{
  "project_id": "<uuid>",
  "file_path": "src/service.py",
  "session_id": "<from-open>",
  "node_ref": "<method-uuid>"
}
```

---

## When to use preview vs session search

| Task | Command |
|------|---------|
| Outline / drill-down one level | `universal_file_preview` (optional `node_ref`) |
| XPath / CSTQuery over whole session tree | `universal_file_search` (requires `session_id`, Python sidecar) |
| Project-wide text or symbol lookup | `fulltext_search`, `fs_grep` — then open file and search/preview |

---

## Best practices

- **Python sidecar:** `node_ref` from preview or search is stable across sibling batch edits; re-preview or re-search after full parent replace or failed ops.
- **Text format:** line slugs/indices go stale after each edit — re-preview with `session_id` before the next line-targeted op.
- Do not use `fulltext_search` line numbers as edit coordinates — they target the index, not the draft.
- For live schema and metadata: `help(command="universal_file_preview")`.

---

## See also

- [universal_file_search.md](universal_file_search.md)
- [universal_file_open.md](universal_file_open.md)
- [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)
