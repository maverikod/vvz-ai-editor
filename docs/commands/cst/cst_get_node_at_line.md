# cst_get_node_at_line

**Command name:** `cst_get_node_at_line`  
**Class:** `CSTGetNodeAtLineCommand`  
**Source:** `code_analysis/commands/cst_get_node_at_line_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Return the **node spanning a given line** and its **parent** in one response. Reduces round-trips (otherwise: cst_get_node_by_range + cst_get_node_info with include_parent).

- Input: `tree_id`, `line` (1-based). Optional: `include_code`.
- Uses existing `find_node_by_range(tree_id, line, line)` and `get_node_parent(tree_id, node_id)`.
- Response: `node` (metadata dict), `parent` (metadata dict or null if root). With `include_code=True`, node and parent include code snippet.
- If no node for line: clear error (NODE_NOT_FOUND, INVALID_LINE, INVALID_RANGE).

**References:** Concept §6.6 "Node + parent in one call" in [CST_CONCEPT_AND_PIPELINE.md](../../cst_concept/CST_CONCEPT_AND_PIPELINE.md); gap analysis Option C.

---

## Arguments

| Parameter      | Type    | Required | Description                                  |
|----------------|---------|----------|----------------------------------------------|
| `tree_id`      | string  | **Yes**  | Tree ID from cst_load_file.                  |
| `line`         | integer | **Yes**  | Line number (1-based).                       |
| `include_code`  | boolean | No       | Include code snippet for node and parent. Default: false. |

**Schema:** `additionalProperties: false`.

---

## Returned data

### Success

- `success`: true
- `tree_id`: Tree ID
- `line`: Requested line
- `node`: Node metadata (node_id, type, kind, name, qualname, start/end line/col, etc.; optional `code` if include_code)
- `parent`: Parent node metadata or null (module root has no parent); optional `code` if include_code

### Error codes

- **INVALID_LINE** — line < 1
- **NODE_NOT_FOUND** — No node at that line or tree/node metadata missing
- **INVALID_RANGE** — ValueError from range finder (e.g. invalid tree)
- **CST_GET_NODE_AT_LINE_ERROR** — Other failure
