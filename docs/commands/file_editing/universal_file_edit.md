# universal_file_edit

**Command:** `universal_file_edit`  
**Class:** `UniversalFileEditCommand`  
**Source:** `code_analysis/commands/universal_file_edit/edit_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Apply a batch of mutation operations to the **in-memory draft** of an open session. The canonical file on disk is **not** modified.

**Workflow step 3.** Operation shape must match `format_group` from open and `node_ref` format from preview or `universal_file_search`. See [WORKFLOW.md](WORKFLOW.md) and [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (schema consistency) |
| `session_id` | string | **Yes** | From `universal_file_open` |
| `operations` | array | **Yes** | One or more ops; shape depends on format group |

Supported `type` values: `replace`, `insert`, `delete`.

---

## Operation shapes by format_group

### sidecar (Python)

| type | Key fields |
|------|------------|
| replace | `node_id`, `code_lines` (preferred) or `code` |
| insert | `parent_node_id` + `position` (`first`/`last`), **or** `target_node_id` + `position` (`before`/`after`) |
| delete | `node_id` |

- `node_id` = stable UUID from `universal_file_preview` (`node_ref` in preview response).
- Prefer **`code_lines`** (array of strings) for multi-line Python.
- One batch may target **siblings** (e.g. two methods, nested functions under the same parent) — `stable_id` is preserved; re-preview between those ops is not required.
- Do not combine **ancestor + descendant** in one batch → `NESTED_BATCH_FORBIDDEN` (split calls or edit only the outer node).
- Re-preview when an op failed, after full replace of a container, or when drill-down targets are unknown.

### tree-temp (JSON/YAML)

| type | Key fields |
|------|------------|
| replace | `json_pointer`, `value` |
| insert | `parent_json_pointer`, `key` or `index`, `value`; append via `/-` suffix |
| delete | `json_pointer` |

Pass preview `node_ref` in **`json_pointer`**, not `node_id`.

### text

| type | Key fields |
|------|------------|
| replace | `node_ref` + `content`, **or** `start_line`, `end_line`, `content` |
| insert | `node_ref` / `position` / `content`; `position: "last"` to append |
| delete | `node_ref` or line range |

When both `node_ref` and lines are present, **`node_ref` wins**.  
Optional: `anchor_head`, `anchor_tail` — reject op if draft lines no longer match.

---

## Returned data

### Success

- `updated: true` when draft changed (sidecar/tree-temp)
- `line_count` for text format

### Error

| Code | Meaning |
|------|---------|
| `SESSION_NOT_FOUND` | Invalid or expired session_id |
| `STALE_NODE_ID` / `UNKNOWN_NODE_REF` | Re-run preview with session_id |
| `NESTED_BATCH_FORBIDDEN` | Parent and child node in same Python batch — split the batch |
| `PARSE_ERROR` | Replacement code does not parse |
| `ANCHOR_MISMATCH` | Text anchors do not match draft |

---

## Examples

**Replace Python method body**

```json
{
  "project_id": "<uuid>",
  "session_id": "<session>",
  "operations": [
    {
      "type": "replace",
      "node_id": "<method-uuid>",
      "code_lines": [
        "def process(self, value: int) -> str:",
        "    \"\"\"Process value.\"\"\"",
        "    return str(value)"
      ]
    }
  ]
}
```

**Signature-only replace (body preserved)** — see [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md):

```json
{
  "operations": [
    {
      "type": "replace",
      "node_id": "<function-uuid>",
      "code_lines": ["def process(self, value: int) -> str: pass"]
    }
  ]
}
```

The trailing `pass` in the snippet is parse scaffolding only; the existing body is kept.

**Insert after sibling**

```json
{
  "operations": [
    {
      "type": "insert",
      "target_node_id": "<existing-def-uuid>",
      "position": "after",
      "code_lines": ["def helper() -> None:", "    pass"]
    }
  ]
}
```

**YAML replace**

```json
{
  "operations": [
    {"type": "replace", "json_pointer": "/timeout", "value": 60}
  ]
}
```

**Batch: insert + replace sibling methods**

```json
{
  "operations": [
    {
      "type": "insert",
      "target_node_id": "<alpha-method-uuid>",
      "position": "after",
      "code_lines": ["", "def gamma(self) -> bool:", "    return True"]
    },
    {
      "type": "replace",
      "node_id": "<beta-method-uuid>",
      "code_lines": ["def beta(self) -> int:", "    return 42"]
    }
  ]
}
```

---

## Best practices

- Preview once before the first edit to collect `node_ref` values; for Python XPath use `universal_file_search` on the same `session_id`.
- Re-run `universal_file_preview` or `universal_file_search` after a failed op, after full replace of a parent node, or before text line-targeted edits.
- Do not combine parent and child node targets in one Python batch — use separate calls.
- Commit via `universal_file_write`, then `universal_file_close`.

---

## See also

- [universal_file_search.md](universal_file_search.md)
- [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)
- [universal_file_write.md](universal_file_write.md)
