# cst_reload_tree

**Command name:** `cst_reload_tree`  
**Class:** `CSTReloadTreeCommand`  
**Source:** `code_analysis/commands/cst_reload_tree_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_reload_tree command reloads a CST tree from its file on disk, updating the existing tree in memory. The tree_id remains the same, so all references to the tree remain valid. This is useful after saving a tree to file or when the file has been modified externally.

Operation flow:
1. Validates tree_id exists in memory
2. Reads file from disk (using file_path stored in tree)
3. Parses source using LibCST
4. Updates tree module in place
5. Rebuilds node index and metadata
6. Returns updated tree_id and node metadata

Key differences from cst_load_file:
- Keeps the same tree_id (no new tree is created)
- Updates existing tree in memory
- All references to tree_id remain valid
- Useful for synchronizing tree with file after save

Use cases:
- Reload tree after cst_save_tree to sync with file
- Update tree after external file modifications
- Refresh tree metadata after file changes
- Maintain tree_id across file reloads

Important notes:
- Tree_id remains the same after reload
- All node_ids may change if file structure changed
- Tree is updated in place, not replaced
- File must exist and be valid Python code

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID to reload |
| `node_types` | array | No | Optional filter by node types (e.g., ['FunctionDef', 'ClassDef']) |
| `max_depth` | integer | No | Optional maximum depth for node filtering |
| `include_children` | boolean | No | Whether to include children information in metadata Default: `true`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Same tree_id (unchanged)
- `file_path`: Path to reloaded file
- `nodes`: List of updated node metadata dictionaries
- `total_nodes`: Total number of nodes returned
- `reloaded`: Always True

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** TREE_NOT_FOUND, FILE_NOT_FOUND, CST_RELOAD_ERROR (and others).

---

## Examples

### Correct usage

**Reload tree after save**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Reloads tree from file after saving. Tree_id remains the same, so you can continue using it with other commands. Useful after cst_save_tree to sync tree with saved file.

**Reload with filters**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_types": [
    "FunctionDef",
    "ClassDef"
  ]
}
```

Reloads tree but returns metadata only for functions and classes. Full tree is still updated, but metadata is filtered.

### Incorrect usage

- **TREE_NOT_FOUND**: Tree does not exist in memory. Use cst_load_file to load file into tree first

- **FILE_NOT_FOUND**: File does not exist on disk. Verify file exists at the path stored in tree

- **CST_RELOAD_ERROR**: Error during tree reload. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `TREE_NOT_FOUND` | Tree does not exist in memory | Use cst_load_file to load file into tree first |
| `FILE_NOT_FOUND` | File does not exist on disk | Verify file exists at the path stored in tree |
| `CST_RELOAD_ERROR` | Error during tree reload |  |

## Best practices

- Use after cst_save_tree to sync tree with saved file
- Use when file has been modified externally
- Tree_id remains the same, so all references remain valid
- All node_ids may change if file structure changed
- Use filters to reduce metadata size when only specific types are needed

---
