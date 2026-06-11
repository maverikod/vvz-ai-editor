# cst_modify_tree

> **MCP AI editing:** use [`universal_file_edit`](../file_editing/universal_file_edit.md) instead.  
> This command is for **internal** in-memory `tree_id` workflows (`cst_load_file` → … → `cst_save_tree`).

**Command name:** `cst_modify_tree`  
**Class:** `CSTModifyTreeCommand`  
**Source:** `code_analysis/commands/cst_modify_tree_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_modify_tree command modifies a CST tree with atomic operations. All operations in a batch are validated before being applied. If any operation fails, all changes are rolled back and the tree remains unchanged.

Operation flow:
1. Validates tree_id exists
2. Validates all operations (checks node_ids, code syntax)
3. If all valid, applies all operations atomically
4. Validates modified module (compiles it)
5. Updates tree in memory
6. Returns success with operations_applied count

Supported Operations:
- replace: Replace a node with new code
  - Requires: exactly one of (node_id or selector), and (code or code_lines). If selector: tree_id required; optional match_index (default 0), replace_all.
- insert: Insert a new node
  - Requires: (parent_node_id OR target_node_id), code, position ('before' or 'after')
  - parent_node_id: Insert at beginning/end of parent's body
  - target_node_id: Insert before/after specific target node
- delete: Delete a node
  - Requires: exactly one of (node_id or selector). If selector: tree_id required; optional match_index, replace_all.

Atomicity:
- All operations are validated before any are applied
- If any operation fails validation, none are applied
- If module validation fails after applying operations, tree is rolled back
- Tree remains unchanged if any error occurs

Use cases:
- Batch modifications to code structure
- Refactoring operations
- Code transformations
- Multiple related changes in one operation

Important notes:
- Operations are applied in order.
- Use cst_save_tree to persist changes to file.
- Tree modifications are in-memory until saved.
- All operations must be valid for any to be applied.

Recommended AI workflow:
1. cst_load_file
2. cst_modify_tree with preview=true
3. cst_modify_tree with preview=false
4. cst_save_tree (persist to disk)
5. format_code/lint_code/type_check_code for the changed file

**For MCP agents:** use [universal file workflow](../file_editing/WORKFLOW.md) instead of the steps above.

### Header-only vs full replace (ClassDef / FunctionDef)

When `replace_all_child_nodes` is **false** (default) and replacement text is a **single non-empty line** with no indented body lines, the server patches only the **header** (signature / class line) and preserves body and docstring.

Force full node replacement:

- Send multi-line replacement including body, **or**
- Set `replace_all_child_nodes: true` on the replace operation.

Same inference applies to `universal_file_edit` (no explicit flag) — see [PYTHON_EDIT_SEMANTICS.md](../file_editing/PYTHON_EDIT_SEMANTICS.md).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `replace_all_child_nodes` | boolean | No | When true, always full replace for ClassDef/FunctionDef (default false) |

Batch behaviour:
When you send multiple replace or delete operations in one request, each node is resolved in the current module by its position (from metadata). So the second and later operations see the tree after previous ops are applied; you can replace or delete several nodes in one call. Use one batch for related changes.

Insert — parent_node_id:
Must be a container node: Module, FunctionDef, or ClassDef (not the body node IndentedBlock). Use __root__ for module-level insert. To insert into a function body, use the function's node_id (FunctionDef from cst_find_node), not its IndentedBlock child.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `preview` | boolean | No | Preview mode: show changes without applying (default: false). Recommended first step for AI models before write operations. |
| `operations` | array | **Yes** | List of operations to apply atomically |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID (same as input)
- `operations_applied`: Number of operations successfully applied

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_OPERATION, CST_MODIFY_ERROR, SELECTOR_NO_MATCH, SELECTOR_PARSE_ERROR (and others).

---

## Examples

### Correct usage

**Replace a function (by node_id)**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "replace",
      "node_id": "function:old_function:FunctionDef:10:0-20:0",
      "code": "def new_function():\n    return 'updated'"
    }
  ]
}
```

Replaces old_function with new_function. The code must be valid Python syntax. Operation is atomic - if code is invalid, tree remains unchanged.

**Replace by selector (no prior cst_find_node)**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "replace",
      "selector": "ImportFrom[module='.task_status']",
      "code_lines": [
        "from ..task_status import TaskStatus"
      ]
    }
  ]
}
```

Replaces the first ImportFrom matching the selector. Use match_index for Nth match; replace_all to replace all matches.

**Delete a statement**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "delete",
      "node_id": "smallstmt:Pass:15:4-15:8"
    }
  ]
}
```

Deletes a pass statement. Node must exist in tree. If node_id is invalid, operation fails and tree remains unchanged.

**Insert statement before existing code**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "insert",
      "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
      "code": "    logger.info('Starting processing')",
      "position": "before"
    }
  ]
}
```

Inserts a logging statement at the beginning of process_data function. Position 'before' means it will be inserted before existing function body. Parent node must exist and be a container (function, class, etc.).

**Insert statement after existing code**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "insert",
      "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
      "code": "    logger.info('Processing complete')",
      "position": "after"
    }
  ]
}
```

Inserts a logging statement at the end of process_data function. Position 'after' means it will be inserted after existing function body.

### Incorrect usage

- **INVALID_OPERATION**: Invalid operation parameters. Check operation parameters:
- For replace: exactly one of node_id or selector; code or code_lines required
- For delete: exactly one of node_id or selector
- For insert: (parent_node_id OR target_node_id) must be provided, code must be valid Python, position must be 'before' or 'after'
All operations in a batch are validated before any are applied.

- **CST_MODIFY_ERROR**: Error during tree modification. 

- **SELECTOR_NO_MATCH**: Selector matched no nodes. Check selector and tree content; use query_cst to test selector.

- **SELECTOR_PARSE_ERROR**: Invalid selector syntax. Fix selector string; see CSTQuery selector syntax.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_OPERATION` | Invalid operation parameters | Check operation parameters:
- For replace: exactly |
| `CST_MODIFY_ERROR` | Error during tree modification |  |
| `SELECTOR_NO_MATCH` | Selector matched no nodes | Check selector and tree content; use query_cst to  |
| `SELECTOR_PARSE_ERROR` | Invalid selector syntax | Fix selector string; see CSTQuery selector syntax. |

## Best practices

- Validate all operations before calling cst_modify_tree
- Use batch operations for related changes (atomicity)
- Test code syntax before using in replace/insert operations
- Use cst_load_file or query_cst to get valid node_ids
- Operations are applied in order - consider dependencies
- Use cst_save_tree to persist changes to file
- Tree modifications are in-memory until saved
- If any operation fails, all operations are rolled back

---
