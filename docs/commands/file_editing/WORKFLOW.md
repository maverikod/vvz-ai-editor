# Universal file edit workflow

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

```
universal_file_preview     # optional before open; navigation / node_ref discovery
universal_file_open        # session_id + format_group
universal_file_search      # optional; XPath on session CST tree (Python sidecar)
universal_file_edit        # repeat; draft only
universal_file_write       # preview diff
universal_file_write       # commit (sidecar/text) OR write_mode=commit (tree-temp)
universal_file_close       # always, including abort without commit
format_code / lint_code / type_check_code   # Python after commit
```

`universal_file_edit` **never** writes the canonical file. Disk changes happen only on **`universal_file_write` commit**.

## Format groups

Returned by `universal_file_open` as `format_group`:

| format_group | Extensions | Draft artefact | Preview `node_ref` | Edit address field |
|--------------|------------|----------------|--------------------|--------------------|
| **sidecar** | `.py`, `.pyi`, `.pyw` | `<file>.cst_sidecar` | CST stable UUID | `node_id` |
| **tree-temp** | `.json`, `.yaml`, `.yml`, `.jsonl`, `.ndjson` | `<file>.draft` + in-memory tree | JSON Pointer, e.g. `/timeout` | `json_pointer` (not `node_id`) |
| **text** | `.md`, `.txt`, `.rst`, `.adoc`, … | `<file>.draft` | MD: slug path (`intro.setup`); plain: zero-based line index (`"3"`) | `node_ref` or `start_line`/`end_line` |

## Preview with an open session

After `universal_file_open`, pass the same `session_id` to `universal_file_preview`:

- Reads the **current draft** (not stale on-disk source).
- **Python (sidecar):** `node_ref` (`stable_id`) is preserved across sibling ops in one batch; re-preview when targets are unknown, an op failed, or after full replace of a container.
- **Text:** line numbers and section slugs go stale after each edit — re-preview before the next line-targeted op.
- For Python with unsaved edits, `focus.text` may show a unified diff (committed → draft); drill-down focus shows a slice for that node only.

## Search session tree (optional, Python sidecar)

**Command:** [`universal_file_search`](universal_file_search.md)

Use after `universal_file_open` when you need **XPath / CSTQuery** over the **session draft CST tree** — not project-wide search.

| | `universal_file_preview` | `universal_file_search` |
|--|--------------------------|-------------------------|
| Scope | One focus node + children | Whole tree under session |
| Query | Manual drill-down by `node_ref` | CSTQuery selector (`query`) |
| Requires session | Optional | **Required** (`session_id`) |
| Formats | All supported | Python sidecar only |

Example:

```json
{
  "project_id": "<uuid>",
  "session_id": "<from open>",
  "query": "//FunctionDef[name='process_data']",
  "include_code": true
}
```

Use `matches[].node_ref` as `node_id` in `universal_file_edit`. Does **not** replace `fulltext_search` / `fs_grep` for locating files in the project.

## Operation shapes (summary)

### sidecar (Python)

```json
{
  "type": "replace",
  "node_id": "<uuid-from-preview-or-search>",
  "code_lines": ["def foo(x: int) -> str:", "    return str(x)"]
}
```

Insert at module level: `parent_node_id: "__root__"`, `position: "first"` | `"last"`.  
Insert relative to sibling: `target_node_id`, `position: "before"` | `"after"`.  
Batch may include multiple **sibling** targets (methods, nested functions).  
Do not combine **parent + child** in one batch (`NESTED_BATCH_FORBIDDEN`).

See [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md) for signature-only replace.

### tree-temp (JSON/YAML)

```json
{"type": "replace", "json_pointer": "/database/host", "value": "localhost"}
{"type": "insert", "parent_json_pointer": "/items/-", "value": {"id": 1}}
```

Append to array: parent pointer ending in `/-` (RFC 6901 sentinel).

### text

Prefer `node_ref` from preview over raw line numbers.

```json
{"type": "replace", "node_ref": "intro.setup", "content": "## Setup\n\nUpdated.\n"}
```

Plain text line replace (1-based, inclusive):

```json
{"type": "replace", "start_line": 10, "end_line": 12, "content": "New paragraph.\n"}
```

**Line numbers go stale after each edit.** Re-preview with `session_id` before the next line-targeted op, or use `anchor_head` + `anchor_tail` (five non-whitespace chars from first/last line of range).

## Write (two-phase)

### tree-temp

Explicit modes on every call:

- `write_mode: "preview"` — diff only
- `write_mode: "commit"` — backup + atomic write

Preview before commit is **mandatory** ([FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)).

### sidecar / text

PID lockfile on canonical file:

1. First `universal_file_write` → unified diff, lockfile created
2. Second call (same session, lock valid) → backup + commit

Alternatively, tree-temp-style `write_mode` may be accepted where implemented — check `help(universal_file_write)`.

## Parse-error fallback

If a structured file cannot be parsed on open, the session opens with `is_invalid: true` and **line-based** editing until a successful commit restores structural editing.

## Discovery before edit

Use read-only search to find `file_path`:

- `fulltext_search` — exact tokens / symbol names (indexed)
- `semantic_search` — meaning-based (vectors)
- `fs_grep` — regex on disk

Then `universal_file_preview` or `universal_file_search` (open Python session) for edit targets — search hits are not substitutes for `node_ref`.

## Sessions

- One active edit session per file until `universal_file_close`.
- `session_id` is **invalid after server restart** — call `universal_file_open` again.
- Not the same as client `session_create` / `session_open_file` (DB-persisted locks).

## Related docs

- Per-command: [COMMANDS.md](COMMANDS.md)
- AI rules: [AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md)
- Spec: [source_spec.md](../../plans/2026-05-16-universal-file-edit/source_spec.md)
