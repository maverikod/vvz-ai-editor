# universal_file_search

**Command:** `universal_file_search`  
**Class:** `UniversalFileSearchCommand`  
**Source:** `code_analysis/commands/universal_file_edit/search_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

XPath / CSTQuery search **inside one open edit-session CST tree** (Python sidecar only).

Does **not** search the project or disk. Runs selectors only on the in-memory tree bound to `session_id` from `universal_file_open` — the same draft that `universal_file_edit` mutates.

Parent workflow: [WORKFLOW.md](WORKFLOW.md).

---

## When to use

| Need | Command |
|------|---------|
| Selector over session draft tree | **universal_file_search** (this) |
| Outline / drill-down | `universal_file_preview` |
| Project-wide text | `fulltext_search`, `fs_grep` |
| Legacy CST without session | `cst_find_node`, `query_cst` |

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID |
| `session_id` | string | **Yes** | From `universal_file_open` |
| `search_type` | string | No | `xpath` (default) or `simple` |
| `query` | string | For xpath | CSTQuery selector |
| `node_type`, `name`, `qualname`, `start_line`, `end_line` | various | For simple | Combined AND filters |
| `include_code` | boolean | No | Return source per match |
| `require_one` | boolean | No | Fail unless exactly one match |
| `max_results` | integer | No | Cap returned matches |

---

## Example

```json
{
  "project_id": "<uuid>",
  "session_id": "<from universal_file_open>",
  "query": "ClassDef[name='Widget']//FunctionDef",
  "include_code": true
}
```

Use `matches[].node_ref` as `node_id` in `universal_file_edit`.

---

## Errors

| Code | Meaning |
|------|---------|
| `SESSION_NOT_FOUND` | Invalid session |
| `UNSUPPORTED_FORMAT` | Not Python sidecar / `is_invalid` session |
| `TREE_NOT_AVAILABLE` | No CST tree on session |
| `INVALID_SEARCH` | Bad parameters |
| `NoMatch` / `NonUniqueMatch` | `require_one` constraint |

---

## See also

- [universal_file_edit.md](universal_file_edit.md)
- [../cst/cst_find_node.md](../cst/cst_find_node.md) — legacy tree_id API
