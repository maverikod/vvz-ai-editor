# cst_get_node_by_range

**Command name:** `cst_get_node_by_range`  
**Class:** `CSTGetNodeByRangeCommand`  
**Source:** `code_analysis/commands/cst_get_node_by_range_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_get_node_by_range command finds a node that covers a specific line range. This is useful when you know the line numbers but need the node_id for modification operations.

Operation flow:
1. Validates tree_id exists
2. Validates line range (start_line <= end_line)
3. Finds node(s) covering the range
4. Returns node metadata with node_id

Search Modes:
1. Single node (all_intersecting=False, default):
   - Finds the best node covering the range
   - If prefer_exact=True: prefers node that exactly matches the range
   - If prefer_exact=False: returns smallest node that contains the range
2. All intersecting nodes (all_intersecting=True):
   - Returns all nodes that intersect with the range
   - Useful for finding multiple nodes in a range

Use cases:
 - Get node_id for a specific line range before modification
 - Find the node covering lines 136-143 for replacement
 - Discover code structure by line numbers
 - Get exact node_id when you know line numbers from error messages

Important notes:
 - Tree must be loaded first with cst_load_file
 - Line numbers are 1-based (first line is 1)
 - Returns node that contains the range, not necessarily exact match
 - Use node_id from result with cst_modify_tree

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `start_line` | integer | **Yes** | Start line (1-based, inclusive) |
| `end_line` | integer | **Yes** | End line (1-based, inclusive) |
| `prefer_exact` | boolean | No | If True, prefer node that exactly matches the range. If False, return smallest node containing the range. Default: `true`. |
| `all_intersecting` | boolean | No | If True, return all nodes that intersect with the range. If False, return single best node. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID that was searched
- `start_line`: Start line that was searched
- `end_line`: End line that was searched
- `node`: Node metadata dictionary (when all_intersecting=False)
- `nodes`: List of node metadata dictionaries (when all_intersecting=True)
- `exact_match`: Whether node exactly matches the range (when all_intersecting=False)
- `total_nodes`: Total number of nodes found (when all_intersecting=True)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** NODE_NOT_FOUND, INVALID_RANGE, CST_GET_NODE_BY_RANGE_ERROR (and others).

---

## Examples

### Correct usage

**Get node for specific line range**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "start_line": 136,
  "end_line": 143
}
```

Finds the node covering lines 136-143. Returns the best matching node (exact match preferred). Use the node_id from result for cst_modify_tree operations.

**Get smallest node containing range**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "start_line": 136,
  "end_line": 143,
  "prefer_exact": false
}
```

Finds the smallest node that contains the range 136-143. Useful when exact match doesn't exist but you want the most specific node.

**Get all nodes intersecting with range**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "start_line": 136,
  "end_line": 143,
  "all_intersecting": true
}
```

Returns all nodes that intersect with the range 136-143. Useful for discovering all code elements in a line range.

### Incorrect usage

- **NODE_NOT_FOUND**: No node found covering the range. Check that the line range is valid for the file. Use cst_load_file to see available nodes and their line ranges.

- **INVALID_RANGE**: Invalid line range. Ensure start_line <= end_line. Line numbers are 1-based.

- **CST_GET_NODE_BY_RANGE_ERROR**: Error during search. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `NODE_NOT_FOUND` | No node found covering the range | Check that the line range is valid for the file. U |
| `INVALID_RANGE` | Invalid line range | Ensure start_line <= end_line. Line numbers are 1- |
| `CST_GET_NODE_BY_RANGE_ERROR` | Error during search |  |

## Best practices

- Use this command when you know line numbers but need node_id
- Tree must be loaded first with cst_load_file
- prefer_exact=True is usually what you want (default)
- Use all_intersecting=True to discover all nodes in a range
- Line numbers are 1-based (first line is 1)
- Use node_id from result with cst_modify_tree for modifications

---
