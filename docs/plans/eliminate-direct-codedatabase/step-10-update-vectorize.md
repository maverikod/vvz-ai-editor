# Step 10: update_vectorize.py — add update_and_vectorize_via_driver to update_standalone.py

## Target files
- Extend `code_analysis/core/database/files/update_standalone.py` (created in step 09)
- `code_analysis/core/database/files/update_vectorize.py` — keep as-is (backward compat)

## Depends on: Step 09 (`update_standalone.py` must exist)

---

## Key discovery: DocstringChunker already supports DatabaseClient

After reading the full source of `vectorize_file_immediately` and `DocstringChunker`,
the implementation is much simpler than originally expected.

`vectorize_file_immediately` has **zero** direct `self._execute()` / `self._fetchone()` calls.
All DB work is inside `DocstringChunker`, which already has dual-path support:

```python
# docstring_chunker.py: _file_still_exists_and_not_deleted (line 136)
if hasattr(self.database, '_fetchone'):  # CodeDatabase path
    row = self.database._fetchone(sql, params)
else:  # DatabaseClient path — already handled
    r = self.database.execute(sql, params)
    return len(r.get('data', [])) > 0

# docstring_chunker.py: _persist_code_chunk_param_rows (line 311)
upsert_batch = getattr(self.database, 'upsert_code_chunks_batch', None)
if callable(upsert_batch):  # DatabaseClient has this — uses execute_batch internally
    await upsert_batch(param_rows)
    return
# fallback: execute_batch — also exists on DatabaseClient
ops = build_code_chunk_upsert_batch(param_rows)
await asyncio.to_thread(execute_batch, ops)
```

`DatabaseClient` has all required methods:

| Method called on `self` / `database` | Exists in DatabaseClient? |
|--------------------------------------|--------------------------|
| `mark_file_needs_chunking(file_path, project_id)` | ✅ via `_ClientAPIFilesMixin` |
| `get_project(project_id)` | ✅ via `_ClientAPIProjectsMixin` |
| `DocstringChunker(database=self, ...)` | ✅ dual-path already in chunker |
| `upsert_code_chunks_batch(param_rows)` | ✅ via `_ClientOperationsMixin` |
| `execute_batch(ops)` (fallback) | ✅ via `_ClientOperationsMixin` |

**Conclusion:** `_vectorize_via_client` is not a rewrite of SQL logic.
It is a thin wrapper that passes `DatabaseClient` to existing `DocstringChunker`.

---

## Architecture check

```
vectorize_after_index.py
  └→ _vectorize_file_immediately(db, ...)   [db is DatabaseClient after step 06]
       └→ db.vectorize_file_immediately(...)   [AttributeError until step 10!]
```

Step 10 adds `_vectorize_via_client` to `update_standalone.py` and updates
`vectorize_after_index.py` to call it instead of `db.vectorize_file_immediately()`.

New path after step 10:
```
vectorize_after_index._vectorize_file_immediately(client, ...)
  └→ update_standalone._vectorize_via_client(client, ...)
       └→ DocstringChunker(database=client, ...).process_file(...)
            └→ [DB ops via DatabaseClient — already works]
```

---

## What to add to update_standalone.py

### Function 1: `_vectorize_via_client` (private helper)

```python
async def _vectorize_via_client(
    client: Any,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Any,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Vectorize a file immediately using a DatabaseClient.

    Thin wrapper: passes the client to DocstringChunker as `database`.
    DocstringChunker already supports DatabaseClient via its dual-path
    `_file_still_exists_and_not_deleted` and `_persist_code_chunk_param_rows`.

    Args:
        client: DatabaseClient instance (already connected).
        file_id: File ID in the database.
        project_id: Project UUID.
        file_path: Absolute path to the file.
        svo_client_manager: SVO client manager for embeddings.
        faiss_manager: Optional FAISS manager (reserved, not used directly).

    Returns:
        Result dict: {success, chunked, chunks_created, vectorized,
                      marked_for_worker, error}.
    """
    import ast
    from pathlib import Path
    from code_analysis.core.docstring_chunker_pkg.docstring_chunker import DocstringChunker

    if not svo_client_manager:
        client.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": True, "chunked": False, "chunks_created": 0,
            "vectorized": False, "marked_for_worker": True, "error": None,
        }

    try:
        # Get project root for path normalization (optional — graceful fallback)
        project_root = None
        try:
            db_project = client.get_project(project_id)
            if db_project:
                project_root = Path(db_project["root_path"])
        except Exception as e:
            logger.debug("Could not get project root: %s", e)

        # Read file content
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            client.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False, "chunked": False, "chunks_created": 0,
                "vectorized": False, "marked_for_worker": True,
                "error": "File not found",
            }

        file_content = file_path_obj.read_text(encoding="utf-8")

        # Parse AST
        try:
            tree = ast.parse(file_content, filename=file_path)
        except SyntaxError as e:
            client.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False, "chunked": False, "chunks_created": 0,
                "vectorized": False, "marked_for_worker": True,
                "error": f"Syntax error: {e}",
            }

        # DocstringChunker already supports DatabaseClient via dual-path
        chunker = DocstringChunker(
            database=client,         # DatabaseClient — supported
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
            min_chunk_length=30,
        )

        chunks_created = await chunker.process_file(
            file_id=str(file_id),
            project_id=project_id,
            file_path=file_path,
            tree=tree,
            file_content=file_content,
        )

        return {
            "success": True, "chunked": True, "chunks_created": chunks_created,
            "vectorized": chunks_created > 0, "marked_for_worker": False,
            "error": None,
        }

    except Exception as e:
        logger.error("Error in _vectorize_via_client for %s: %s", file_path, e, exc_info=True)
        client.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": False, "chunked": False, "chunks_created": 0,
            "vectorized": False, "marked_for_worker": True, "error": str(e),
        }
```

### Function 2: `update_and_vectorize_via_driver` (public)

```python
async def update_and_vectorize_via_driver(
    driver: BaseDatabaseDriver,
    file_path: str,
    project_id: str,
    root_dir: Path,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Update database and immediately vectorize a file using BaseDatabaseDriver.

    Combines update_file_data_via_driver + _vectorize_via_client.
    Both operations share the same InProcessRpcClient session.

    Args:
        driver: Database driver (SQLiteDriver or PostgreSQLDriver).
        file_path: Absolute path to the file.
        project_id: Project UUID.
        root_dir: Project root directory.
        svo_client_manager: Optional SVO client manager for vectorization.
        faiss_manager: Optional FAISS manager.

    Returns:
        Combined result dict with keys from analyze_file +
        'vectorize_result' (if vectorization was attempted).
    """
    from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
    from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
    from code_analysis.core.database_client.client import DatabaseClient
    from code_analysis.commands.update_indexes_analyzer import analyze_file

    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    ipc.connect()
    client = DatabaseClient(rpc_client=ipc)
    try:
        # Step 1: index (sync) — analyze_file is NOT async (def, not async def)
        update_result = analyze_file(
            database=client,
            file_path=Path(file_path),
            project_id=project_id,
            root_path=root_dir,
        )
        if not update_result.get("success"):
            return update_result

        # Step 2: vectorize immediately (async)
        file_id = update_result.get("file_id")
        if file_id and svo_client_manager:
            vectorize_result = await _vectorize_via_client(
                client=client,
                file_id=file_id,
                project_id=project_id,
                file_path=file_path,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
            )
            update_result["vectorize_result"] = vectorize_result
        return update_result
    finally:
        ipc.disconnect()  # InProcessRpcClient.disconnect() also calls driver.disconnect()
```

---

## Step 2: update vectorize_after_index.py

After adding `_vectorize_via_client` to `update_standalone.py`, update
`vectorize_after_index.py` so `_vectorize_file_immediately` no longer calls
`db.vectorize_file_immediately()` (which doesn't exist on `DatabaseClient`).

### Target: `_vectorize_file_immediately` (line 116, `vectorize_after_index.py`)

**Before:**
```python
async def _vectorize_file_immediately(
    db: Any,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Any,
) -> Dict[str, Any]:
    """Thin wrapper around database.vectorize_file_immediately."""
    await svo_client_manager.initialize()
    try:
        return await db.vectorize_file_immediately(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            svo_client_manager=svo_client_manager,
            faiss_manager=None,
        )
    finally:
        await svo_client_manager.close()
```

**After:**
```python
async def _vectorize_file_immediately(
    db: Any,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Any,
) -> Dict[str, Any]:
    """Vectorize via standalone function (db is DatabaseClient after step 06)."""
    from code_analysis.core.database.files.update_standalone import _vectorize_via_client
    await svo_client_manager.initialize()
    try:
        return await _vectorize_via_client(
            client=db,
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            svo_client_manager=svo_client_manager,
            faiss_manager=None,
        )
    finally:
        await svo_client_manager.close()
```

### CST command for vectorize_after_index.py

```
tree_id = cst_load_file(
    file_path="code_analysis/core/indexing_worker_pkg/vectorize_after_index.py",
    project_id=PROJECT_ID,
)
node = cst_find_node(tree_id=tree_id, search_type="simple",
                     node_type="FunctionDef", name="_vectorize_file_immediately")
cst_modify_tree(tree_id=tree_id, operations=[{
    "action": "replace",
    "node_id": node["node_id"],  # re-verify via cst_load_file before editing
    "code_lines": [
        "async def _vectorize_file_immediately(",
        "    db: Any,",
        "    file_id: int,",
        "    project_id: str,",
        "    file_path: str,",
        "    svo_client_manager: Any,",
        ") -> Dict[str, Any]:",
        "    \"\"\"Vectorize via standalone function (db is DatabaseClient after step 06).\"\"\"",
        "    from code_analysis.core.database.files.update_standalone import _vectorize_via_client",
        "    await svo_client_manager.initialize()",
        "    try:",
        "        return await _vectorize_via_client(",
        "            client=db,",
        "            file_id=file_id,",
        "            project_id=project_id,",
        "            file_path=file_path,",
        "            svo_client_manager=svo_client_manager,",
        "            faiss_manager=None,",
        "        )",
        "    finally:",
        "        await svo_client_manager.close()"
    ]
}])
cst_save_tree(tree_id=tree_id, project_id=PROJECT_ID,
              file_path="code_analysis/core/indexing_worker_pkg/vectorize_after_index.py")
```

---

## CST command for update_standalone.py

Use `cst_load_file` on the file created by step 09, then `cst_modify_tree` insert.

```
tree_id = cst_load_file(
    file_path="code_analysis/core/database/files/update_standalone.py",
    project_id=PROJECT_ID,
)
# Insert _vectorize_via_client and update_and_vectorize_via_driver at end of module
root_node = cst_find_node(tree_id=tree_id, search_type="simple",
                           node_type="Module")
cst_modify_tree(tree_id=tree_id, operations=[{
    "action": "insert",
    "parent_node_id": "__root__",
    "position": "last",
    "code_lines": [
        # paste full code of _vectorize_via_client and update_and_vectorize_via_driver
        # from the 'What to add' section above
    ]
}])
cst_save_tree(tree_id=tree_id, project_id=PROJECT_ID,
              file_path="code_analysis/core/database/files/update_standalone.py")
```

---

## Imports to add to update_standalone.py

At the top of `update_standalone.py`, add (if not already present from step 09):
```python
import ast  # for ast.parse in _vectorize_via_client
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver

logger = logging.getLogger(__name__)
```

All other imports are local (inside function body) to avoid circular dependencies.

---

## Verification: what DocstringChunker needs from `database`

Confirmed by reading `docstring_chunker.py` source:

| DocstringChunker call | Method | In DatabaseClient |
|----------------------|--------|-------------------|
| `_file_still_exists_and_not_deleted` | `execute(sql, (file_id, project_id))` | ✅ |
| `_persist_code_chunk_param_rows` | `upsert_code_chunks_batch(param_rows)` | ✅ via `_ClientOperationsMixin` |
| fallback persist | `execute_batch(ops)` | ✅ via `_ClientOperationsMixin` |

Calls on `self` in `vectorize_file_immediately` (CodeDatabase):

| Call | Method in DatabaseClient |
|------|--------------------------|
| `self.mark_file_needs_chunking(file_path, project_id)` | ✅ via `_ClientAPIFilesMixin` |
| `self.get_project(project_id)` | ✅ via `_ClientAPIProjectsMixin` |
| `DocstringChunker(database=self, ...)` | ✅ (dual-path in chunker) |

No SQL is written in step 10. All DB ops go through existing DatabaseClient methods.

---

## Validation sequence

1. `lint_code(file_path="code_analysis/core/database/files/update_standalone.py", project_id=...)`
2. `lint_code(file_path="code_analysis/core/indexing_worker_pkg/vectorize_after_index.py", project_id=...)`
3. `format_code` both files
4. `type_check_code` both files
5. `comprehensive_analysis(project_id=..., check_stubs=True)` — must have no stub methods
6. Run full reindex: trigger a file change → verify `vectorize_file_after_index` completes
7. Check DB: `SELECT embedding_vector FROM code_chunks WHERE file_id=<id>` — must be non-NULL
8. Confirm step 06 now unblocked: vectorization worker cycle completes end-to-end

---

## Risk: MEDIUM

Low SQL risk — no new SQL is written; DocstringChunker already handles DatabaseClient.
Medium implementation risk — async wiring between `_vectorize_file_immediately` (step 06)
and `_vectorize_via_client` must be correct. Verify with end-to-end test after applying.