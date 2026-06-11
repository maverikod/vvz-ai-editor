# Step 02: faiss_manager_rebuild.py — remove CodeDatabase, keep only DatabaseClient

## Target file
`code_analysis/core/faiss_manager_rebuild.py` (319 lines)

## Architecture check
Called from `FaissIndexManager.rebuild_from_database()` — vectorization worker context.
Worker holds `DatabaseClient`. All DB calls must go through it.
Path: Worker → DatabaseClient → RPCServer → RPCHandlers(self.driver) → SpecificDriver

## Behaviour note
In the current code, `if isinstance(database, CodeDatabase): database._execute(...)` in
`_fetch_embedding_from_svo` means embeddings are **NOT saved to DB** when `database` is
`DatabaseClient` (the production path). This is a **bug**. Replacing it with an unconditional
`database.execute(...)` is a **fix**, not a no-op — embeddings will now be properly saved.

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Lines | node_id |
|---------|-------|---------|
| `from .database import CodeDatabase` | 14 | `3d1f2d22-9e7f-484b-9ed3-5ca58a6ec80c` |
| `from typing import ... Union` | 10 | `38f2be45-42c2-4b4d-8f91-aa9c889a61b6` |
| `rebuild_from_database_impl` FunctionDef | 22-187 | `d7901d34-dbe1-45f7-98d4-56fd3cf116d8` |
| isinstance branch (DatabaseClient vs _execute) | **48-119** | `72e0650b-5671-489b-9b70-4cb0908d351c` |
| commit guard `if not isinstance(database, DatabaseClient)` | **175-179** | `adad552c-8602-4dff-9a30-9bfe36d1116c` |
| `_fetch_chunks_for_rebuild` FunctionDef | 190-227 | `9dcb50b2-d11f-4888-93fe-56c8fe53e3eb` |
| isinstance branch in `_fetch_chunks_for_rebuild` | **196-226** | `da8d88e3-3c47-460d-84a7-1045ab2ff20b` |
| `_embedding_from_chunk` FunctionDef | 230-268 | `d624c42b-b831-4e8b-a82e-7f9dc98b5872` |
| `_fetch_embedding_from_svo` FunctionDef | 271-319 | `84284227-69c4-4702-b1bb-948b2f1fa3f8` |
| `if isinstance(database, CodeDatabase): database._execute(...)` | **301-305** | `d29dfad0-5d8b-46df-81c6-37c27eb65906` |

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/core/faiss_manager_rebuild.py")
# Re-verify node IDs with cst_find_node before each modify_tree call
```

### 1. Remove import (line 14)
**Before:** `from .database import CodeDatabase`
**After:** DELETE this line

```json
{"action": "delete", "node_id": "3d1f2d22-9e7f-484b-9ed3-5ca58a6ec80c"}
```

### 2. Remove Union from typing (line 10)
**Before:** `from typing import Any, Dict, List, Optional, Tuple, Union`
**After:** `from typing import Any, Dict, List, Optional, Tuple`

Note: In this file `Union` is only used for `Union[CodeDatabase, DatabaseClient]` — no other usages.

```json
{"action": "replace", "node_id": "38f2be45-42c2-4b4d-8f91-aa9c889a61b6",
 "code_lines": ["from typing import Any, Dict, List, Optional, Tuple"]}
```

### 3. Change signature of `rebuild_from_database_impl` (line 24)
**Before:** `database: Union[CodeDatabase, DatabaseClient],`
**After:** `database: DatabaseClient,`

Replace the whole FunctionDef (`d7901d34`) or use `cst_get_node_by_range(start_line=24, end_line=24)` to find the parameter line node and replace it.

### 4. Remove isinstance branch in vector_id normalization (lines 48-119)

Keep ONLY the DatabaseClient path. Replace If node `72e0650b` with the body of the `if isinstance(database, DatabaseClient):` branch.

**After:**
```python
        if project_id:
            database.execute(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id
                    FROM code_chunks
                    WHERE project_id = ?
                      AND embedding_model IS NOT NULL
                      AND embedding_vector IS NOT NULL
                )
                UPDATE code_chunks
                SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                WHERE id IN (SELECT id FROM ranked)
                """,
                (project_id,),
            )
        else:
            database.execute(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id
                    FROM code_chunks
                    WHERE embedding_model IS NOT NULL
                      AND embedding_vector IS NOT NULL
                )
                UPDATE code_chunks
                SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                WHERE id IN (SELECT id FROM ranked)
                """,
                None,
            )
```

```json
{"action": "replace", "node_id": "72e0650b-5671-489b-9b70-4cb0908d351c", "code_lines": [
    "if project_id:",
    "    database.execute(",
    "        \"\"\"",
    "        WITH ranked AS (",
    "            SELECT",
    "                id,",
    "                (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id",
    "            FROM code_chunks",
    "            WHERE project_id = ?",
    "              AND embedding_model IS NOT NULL",
    "              AND embedding_vector IS NOT NULL",
    "        )",
    "        UPDATE code_chunks",
    "        SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)",
    "        WHERE id IN (SELECT id FROM ranked)",
    "        \"\"\"",
    "        (project_id,),",
    "    )",
    "else:",
    "    database.execute(",
    "        \"\"\"",
    "        WITH ranked AS (",
    "            SELECT",
    "                id,",
    "                (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id",
    "            FROM code_chunks",
    "            WHERE embedding_model IS NOT NULL",
    "              AND embedding_vector IS NOT NULL",
    "        )",
    "        UPDATE code_chunks",
    "        SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)",
    "        WHERE id IN (SELECT id FROM ranked)",
    "        \"\"\"",
    "        None,",
    "    )"
]}
```

### 5. Remove isinstance commit guard (lines 175-179)

DELETE If node `adad552c` entirely.

```json
{"action": "delete", "node_id": "adad552c-8602-4dff-9a30-9bfe36d1116c"}
```

### 6. Change signature of `_fetch_chunks_for_rebuild` (line 191)
**Before:** `database: Union[CodeDatabase, DatabaseClient],`
**After:** `database: DatabaseClient,`

Use `cst_get_node_by_range(start_line=191, end_line=191)` or replace the FunctionDef node.

### 7. Remove isinstance branch in `_fetch_chunks_for_rebuild` (lines 196-226)

Keep ONLY the DatabaseClient path (the `if isinstance(database, DatabaseClient):` body).
DELETE the `else: chunks = database.get_all_chunks_for_faiss_rebuild(project_id=project_id)` branch.
Replace If node `da8d88e3` with just the batched SQL content (without the outer `if isinstance`).

```json
{"action": "replace", "node_id": "da8d88e3-3c47-460d-84a7-1045ab2ff20b", "code_lines": [
    "sql_common = \"\"\"",
    "    SELECT",
    "        cc.id, cc.file_id, cc.project_id, cc.chunk_uuid, cc.chunk_type,",
    "        cc.chunk_text, cc.chunk_ordinal, cc.vector_id, cc.embedding_model,",
    "        cc.embedding_vector, cc.class_id, cc.function_id, cc.method_id,",
    "        cc.line, cc.ast_node_type, cc.source_type",
    "    FROM code_chunks cc",
    "    WHERE cc.embedding_model IS NOT NULL",
    "      AND cc.embedding_vector IS NOT NULL",
    "\"\"\"",
    "if project_id:",
    "    sql_common += \" AND cc.project_id = ?\"",
    "sql_common += \" ORDER BY cc.created_at, cc.id LIMIT ? OFFSET ?\"",
    "offset = 0",
    "while True:",
    "    params: Tuple[Any, ...]",
    "    if project_id:",
    "        params = (project_id, REBUILD_FROM_DB_BATCH_SIZE, offset)",
    "    else:",
    "        params = (REBUILD_FROM_DB_BATCH_SIZE, offset)",
    "    result = database.execute(sql_common, params)",
    "    batch = result.get(\"data\", []) if isinstance(result, dict) else []",
    "    if not batch:",
    "        break",
    "    chunks.extend(batch)",
    "    offset += len(batch)",
    "    if len(batch) < REBUILD_FROM_DB_BATCH_SIZE:",
    "        break"
]}
```

### 8. Change signature of `_embedding_from_chunk` (line 235)
**Before:** `database: Union[CodeDatabase, DatabaseClient],`
**After:** `database: DatabaseClient,`

Actual function starts at line 230; the `database` parameter is the 6th argument.
Use `cst_get_node_by_range(start_line=235, end_line=235)` to find and replace.

### 9. Change signature of `_fetch_embedding_from_svo` (line 275)
**Before:** `database: Union[CodeDatabase, DatabaseClient],`
**After:** `database: DatabaseClient,`

Actual function starts at line 271; `database` is the 4th parameter (line 275).
Use `cst_get_node_by_range(start_line=275, end_line=275)` to find and replace.

### 10. Fix embedding save in `_fetch_embedding_from_svo` (lines 301-305)

**This is a behaviour fix (bug):** currently the embedding is only saved when
`database` is `CodeDatabase`; when it is `DatabaseClient` (the production path)
embeddings are silently NOT saved. Replace with unconditional `database.execute()`.

Replace If node `d29dfad0` (lines 301-305) with the body using `database.execute()`.

**After:**
```python
                database.execute(
                    "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                    (embedding_json, save_model, chunk_id),
                )
```

```json
{"action": "replace", "node_id": "d29dfad0-5d8b-46df-81c6-37c27eb65906", "code_lines": [
    "database.execute(",
    "    \"UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?\",",
    "    (embedding_json, save_model, chunk_id),",
    ")"
]}
```

## Validation sequence
1. `lint_code(file_path="code_analysis/core/faiss_manager_rebuild.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. **Bug-fix verification (important):** after deploying this step, trigger SVO vectorization
   for a chunk that was previously missing an embedding. Verify that `code_chunks.embedding_vector`
   is now populated (was silently skipped when `database` was `DatabaseClient` before this fix).
## Risk: LOW
Logic for DatabaseClient path is unchanged. The CodeDatabase branches are removed.
Embedding save behaviour for DatabaseClient is fixed (was a bug — embeddings were not saved).