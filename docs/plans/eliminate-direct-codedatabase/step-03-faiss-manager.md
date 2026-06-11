# Step 03: faiss_manager.py — remove CodeDatabase from type signatures

## Target file
`code_analysis/core/faiss_manager.py` (401 lines)

## Architecture check
`FaissIndexManager` is used by vectorization worker which passes `DatabaseClient`.
Path: Worker → DatabaseClient → RPCServer → RPCHandlers(self.driver) → SpecificDriver
Type signatures must reflect only `DatabaseClient`. ✅

## Depends on: steps 01 and 02 (both completed first)

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Line | node_id |
|---------|------|---------|
| `from typing import Union` | 24 | `7bd5ed45-b967-4c9e-a9bc-74d260ade343` |
| `from .database import CodeDatabase` | 26 | `0f5093b2-d65a-4a3d-a0e2-00bb4edf2ffe` |
| `check_index_sync` FunctionDef | 310-341 | `884c1e19-ccfb-4cf9-9893-d232cfe1ec81` |
| `rebuild_from_database` FunctionDef | 343-366 | `7517ddc0-f616-49f3-b84c-3f0299a705df` |

**Note on Union import:** In this file `Union` is imported on its own line (`from typing import Union`)
separately from the main typing import (`from typing import Any, Dict, List, Optional, Tuple` on line 20).
All usages of `Union` in this file are exclusively `Union[CodeDatabase, DatabaseClient]` — there are
no other Union usages. It is safe to delete the `from typing import Union` import entirely after
removing the CodeDatabase references.

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/core/faiss_manager.py")
```

### 1. Remove CodeDatabase import (line 26)
**Before:** `from .database import CodeDatabase`
**After:** DELETE this line

```json
{"action": "delete", "node_id": "0f5093b2-d65a-4a3d-a0e2-00bb4edf2ffe"}
```

### 2. Remove Union import (line 24)
**Before:** `from typing import Union`
**After:** DELETE this line

Do this after step 1. Once CodeDatabase is gone, Union has no remaining uses.

```json
{"action": "delete", "node_id": "7bd5ed45-b967-4c9e-a9bc-74d260ade343"}
```

### 3. Change `check_index_sync` signature (line 312)
**Before:**
```python
    database: Union[CodeDatabase, DatabaseClient],
```
**After:**
```python
    database: DatabaseClient,
```

Replace the whole `check_index_sync` FunctionDef (node_id `884c1e19`) with the updated version:

```json
{"action": "replace", "node_id": "884c1e19-ccfb-4cf9-9893-d232cfe1ec81", "code_lines": [
    "def check_index_sync(",
    "    self: \"FaissIndexManager\",",
    "    database: DatabaseClient,",
    "    project_id: str,",
    ") -> Tuple[bool, Dict[str, Any]]:",
    "    \"\"\"",
    "    Check synchronization between database and FAISS index.",
    "",
    "    Verifies that all vector_id values from database exist in FAISS index.",
    "    If any mismatch is found, returns False with details.",
    "",
    "    Args:",
    "        self: Instance.",
    "        database: DatabaseClient — universal driver interface (RPC client).",
    "        project_id: Project ID to check.",
    "",
    "    Returns:",
    "        Tuple of (is_synced: bool, details: dict).",
    "    \"\"\"",
    "    if self.index is None:",
    "        return False, {",
    "            \"error\": \"FAISS index is not initialized\",",
    "            \"db_vector_count\": 0,",
    "            \"index_vector_count\": 0,",
    "        }",
    "    id_map = getattr(self.index, \"id_map\", None)",
    "    return check_index_sync_impl(",
    "        int(self.index.ntotal),",
    "        id_map,",
    "        database,",
    "        project_id,",
    "    )"
]}
```

### 4. Change `rebuild_from_database` signature (line 345)
**Before:**
```python
    database: Union[CodeDatabase, DatabaseClient],
```
**After:**
```python
    database: DatabaseClient,
```

Replace the whole `rebuild_from_database` FunctionDef (node_id `7517ddc0`):

```json
{"action": "replace", "node_id": "7517ddc0-f616-49f3-b84c-3f0299a705df", "code_lines": [
    "async def rebuild_from_database(",
    "    self: \"FaissIndexManager\",",
    "    database: DatabaseClient,",
    "    svo_client_manager: Optional[Any] = None,",
    "    project_id: Optional[str] = None,",
    ") -> int:",
    "    \"\"\"",
    "    Rebuild FAISS index from database.",
    "",
    "    If project_id is provided, rebuilds index for that project only.",
    "    If project_id is None, rebuilds index for all projects (legacy mode).",
    "",
    "    Args:",
    "        self: Instance.",
    "        database: DatabaseClient — universal driver interface (RPC client).",
    "        svo_client_manager: Optional SVOClientManager to get embeddings if missing.",
    "        project_id: Optional project ID to filter by.",
    "",
    "    Returns:",
    "        Number of vectors loaded.",
    "    \"\"\"",
    "    return await rebuild_from_database_impl(",
    "        self, database, svo_client_manager, project_id",
    "    )"
]}
```

## Validation sequence
1. `lint_code(file_path="code_analysis/core/faiss_manager.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`

## Risk: LOW
Pure type signature changes. No logic change. Depends on steps 01, 02.
