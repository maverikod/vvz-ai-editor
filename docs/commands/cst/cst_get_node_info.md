# cst_get_node_info

**Command name:** `cst_get_node_info`  
**Class:** `CSTGetNodeInfoCommand`  
**Source:** `code_analysis/commands/cst_get_node_info_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_get_node_info command retrieves detailed information about a specific node in a CST tree. It can return node metadata, children, parent, and code snippet.

Operation flow:
1. Validates tree_id exists
2. Validates node_id exists in tree
3. Retrieves node metadata
4. Optionally retrieves children (with limit)
5. Optionally retrieves parent
6. Returns combined information

Information Available:
- Node metadata: type, kind, name, qualname, position, children_count
- Code snippet: full source code of the node (if include_code=True)
- Children: list of child nodes with metadata (if include_children=True)
- Parent: parent node metadata (if include_parent=True)

Use cases:
- Get full information about a node before modification
- Analyze node structure and relationships
- Inspect code before making changes
- Understand node context (parent, children)

Important notes:
- Tree must be loaded first with cst_load_file
- Node must exist in tree (use cst_find_node to find nodes)
- Children and parent are optional (reduce response size if not needed)
- max_children limits number of children returned

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `node_id` | string | **Yes** | Node ID |
| `include_code` | boolean | No | Whether to include code snippet Default: `false`. |
| `include_children` | boolean | No | Whether to include full children information Default: `false`. |
| `include_parent` | boolean | No | Whether to include parent node information Default: `false`. |
| `max_children` | integer | No | Maximum number of children to return (if include_children=True) |
| `children_depth` |  | No | Depth of descendants when include_children=True: integer 0=full subtree, 1=direct only, 2+=N levels; or string 'direct' (same as 1), 'recursive' (same as 0). Default: `1`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID
- `node`: Node metadata dictionary
- `children`: List of child node metadata (if include_children=True)
- `children_count`: Number of children returned (if include_children=True)
- `parent`: Parent node metadata (if include_parent=True)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** NODE_NOT_FOUND, CST_GET_NODE_ERROR (and others).

---

## Examples

### Correct usage

**Get basic node information**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "function:main:FunctionDef:10:0-25:0"
}
```

Gets basic metadata for the node (type, name, position, etc.). No code, children, or parent information included.

**Get node with code snippet**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "function:main:FunctionDef:10:0-25:0",
  "include_code": true
}
```

Gets node metadata and full source code. Useful for inspecting code before modification.

**Get node with children**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "class:MyClass:ClassDef:10:0-100:0",
  "include_children": true
}
```

Gets node metadata and all children. Useful for analyzing structure of classes or functions.

**Get node with limited children**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "class:MyClass:ClassDef:10:0-100:0",
  "include_children": true,
  "max_children": 10
}
```

Gets node metadata and first 10 children. Useful for large classes with many methods.

**Get node with parent**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "method:my_method:FunctionDef:20:0-30:0",
  "include_parent": true
}
```

Gets node metadata and parent node. Useful for understanding context (e.g., which class contains a method).

### Incorrect usage

- **NODE_NOT_FOUND**: Node does not exist in tree. Verify node_id is correct. Use cst_load_file to get node_ids or cst_find_node to find nodes.

- **CST_GET_NODE_ERROR**: Error during node information retrieval. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `NODE_NOT_FOUND` | Node does not exist in tree | Verify node_id is correct. Use cst_load_file to ge |
| `CST_GET_NODE_ERROR` | Error during node information retrieval |  |

## Best practices

- Use include_code=True only when code is needed (reduces response size)
- Use include_children=True only when children information is needed
- Use max_children to limit response size for nodes with many children
- Tree must be loaded first with cst_load_file
- Use cst_find_node to find nodes before getting their information
- Node_id can be obtained from cst_load_file or cst_find_node results

---
