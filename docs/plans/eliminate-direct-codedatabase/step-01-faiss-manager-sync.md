# Step 01: faiss_manager_sync.py — remove CodeDatabase, keep only DatabaseClient

## Target file
`code_analysis/core/faiss_manager_sync.py` (101 lines)

## Architecture check
This file is called from `FaissIndexManager.check_index_sync()` which is called
from vectorization worker. The worker holds a `DatabaseClient` instance.
Path: Worker → DatabaseClient → RPCServer → RPCHandlers(driver) → SQLiteDriver/PostgreSQL
The `database` parameter must always be `DatabaseClient`. ✅

## Verified node IDs (do not use line numbers alone — always re-verify via cst_load_file)

| Element | Line | node_id |
|---------|------|---------|
| `from typing import ... Union` | 8 | `eeec9742-b83c-424c-b289-7accb771056a` |
| `from .database import CodeDatabase` | 10 | `b6269e5d-9602-44a7-8fff-5a9355c82e55` |
| `check_index_sync_impl` FunctionDef | 14-101 | `1c2aa421-c79f-47d3-aa13-2b592883a527` |
| isinstance branch (If node) | **36-60** | `e094384e-da1a-4c1e-8dbf-e6ec0690c461` |

## What to change

### 1. Remove import (line 10)
**Before:** `from .database import CodeDatabase`
**After:** DELETE this line

**CST command:**
```
tree_id = cst_load_file(file_path="code_analysis/core/faiss_manager_sync.py")
# node_id verified: b6269e5d-9602-44a7-8fff-5a9355c82e55
cst_modify_tree(tree_id=tree_id, operations=[{"action": "delete", "node_id": "b6269e5d-9602-44a7-8fff-5a9355c82e55"}])
```

### 2. Remove Union from typing (line 8)
**Before:** `from typing import Any, Dict, Set, Tuple, Union`
**After:** `from typing import Any, Dict, Set, Tuple`

**Note:** In this file, `Union` is only used for `Union[CodeDatabase, DatabaseClient]` —
there are no other Union usages. It is safe to remove Union from the typing import.

**CST command:** find node `ImportFrom[module='typing']` (node_id `eeec9742-b83c-424c-b289-7accb771056a`),
replace with `code_lines`:
```json
{"action": "replace", "node_id": "eeec9742-b83c-424c-b289-7accb771056a",
 "code_lines": ["from typing import Any, Dict, Set, Tuple"]}
```

### 3. Change function signature (line 17)
**Before:** `database: Union[CodeDatabase, DatabaseClient],`
**After:** `database: DatabaseClient,`

**CST command:** Replace the whole `check_index_sync_impl` function
(FunctionDef node_id `1c2aa421-c79f-47d3-aa13-2b592883a527`) or use
`cst_find_node(search_type="xpath", query="FunctionDef[name='check_index_sync_impl']")`
and update the parameter line via `cst_modify_tree`.

### 4. Update docstring (line 29)
**Before:** `database: CodeDatabase or DatabaseClient.`
**After:** `database: DatabaseClient — universal driver interface (RPC client).`

### 5. Remove isinstance branch — keep ONLY DatabaseClient path (lines 36-60)

Verified: isinstance branch is an **If node at lines 36-60**,
node_id `e094384e-da1a-4c1e-8dbf-e6ec0690c461`.

**Before:**
```python
    if isinstance(database, DatabaseClient):
        result = database.execute(
            """
            SELECT DISTINCT vector_id
            FROM code_chunks
            WHERE project_id = ?
              AND vector_id IS NOT NULL
              AND embedding_vector IS NOT NULL
            ORDER BY vector_id
            """,
            (project_id,),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
    else:
        rows = database._fetchall(
            """
            SELECT DISTINCT vector_id
            FROM code_chunks
            WHERE project_id = ?
              AND vector_id IS NOT NULL
              AND embedding_vector IS NOT NULL
            ORDER BY vector_id
            """,
            (project_id,),
        )
```
**After:**
```python
    result = database.execute(
        """
        SELECT DISTINCT vector_id
        FROM code_chunks
        WHERE project_id = ?
          AND vector_id IS NOT NULL
          AND embedding_vector IS NOT NULL
        ORDER BY vector_id
        """,
        (project_id,),
    )
    rows = result.get("data", []) if isinstance(result, dict) else []
```

**CST command:**
```
cst_modify_tree(tree_id=tree_id, operations=[{
    "action": "replace",
    "node_id": "e094384e-da1a-4c1e-8dbf-e6ec0690c461",
    "code_lines": [
        "result = database.execute(",
        "    \"\"\"",
        "    SELECT DISTINCT vector_id",
        "    FROM code_chunks",
        "    WHERE project_id = ?",
        "      AND vector_id IS NOT NULL",
        "      AND embedding_vector IS NOT NULL",
        "    ORDER BY vector_id",
        "    \"\"\"",
        "    (project_id,),",
        ")",
        "rows = result.get(\"data\", []) if isinstance(result, dict) else []"
    ]
}])
```

## Validation sequence
1. `lint_code(file_path="code_analysis/core/faiss_manager_sync.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`

## Risk: LOW
No logic change — removing unused CodeDatabase branch. Same SQL query via DatabaseClient.
