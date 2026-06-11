# Step 06: vectorize_after_index.py — replace CodeDatabase with InProcessRpcClient

## Target file
`code_analysis/core/indexing_worker_pkg/vectorize_after_index.py` (142 lines)

## Architecture check
This module runs INSIDE the indexing worker process (separate from driver process).

**Current (WRONG) path:**
Indexing worker → `_create_database()` → `SQLiteDriver()` direct → `CodeDatabase.from_existing_driver(driver)` → `db.vectorize_file_immediately()` via CodeDatabase mixin

Problems:
- Opens a SECOND SQLite connection (the driver process already holds one)
- Bypasses RPC layer entirely
- `vectorize_file_immediately` does NOT exist in DatabaseClient

**Chosen solution — InProcessRpcClient (Option B):**
Instead of a real socket-based RPC call, create an in-process dispatch that calls
RPCHandlers directly without network overhead:

```
Indexing worker
  → SQLiteDriver().connect()   (opens second connection in-process)
  → RPCHandlers(driver)        (RPC handler facade over the local driver)
  → InProcessRpcClient(handlers) (dispatches calls without network)
  → DatabaseClient(rpc_client=ipc) (standard DatabaseClient API)
```

This is architecturally correct: all SQL goes through the RPC handler layer,
no direct `_execute`/`_fetchall` on the driver object, no CodeDatabase involved.

**Verified existing classes (all exist in production code):**
- `InProcessRpcClient(handlers: RPCHandlers)` — `database_client/in_process_rpc_client.py:38`
- `RPCHandlers(driver: BaseDatabaseDriver)` — `database_driver_pkg/rpc_handlers.py:42`
- `DatabaseClient(rpc_client=Optional[Any])` — `database_client/client.py:56` (keyword-only `rpc_client` param) ✅

**Note on `vectorize_file_immediately`:** this method exists in `update_vectorize.py` as a CodeDatabase
mixin and is called as `db.vectorize_file_immediately(...)`. Once `db` is replaced with a `DatabaseClient`,
this call will fail. Therefore `_vectorize_file_immediately` in this file must call
`db.vectorize_file_immediately(...)` via the `DatabaseClient` API. Since `vectorize_file_immediately`
is not yet in `DatabaseClient`, this step also requires **adding it** (see step 10). Until step 10 is
done, calls to `_vectorize_file_immediately` can be left as-is or bridged via the DatabaseClient
`execute()` interface directly.

**Immediate scope of this step:** replace only `_create_database()` and `_close_driver()`.
The `_vectorize_file_immediately` wrapper stays unchanged until step 10 resolves it.

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Lines | node_id |
|---------|-------|---------|
| `_create_database` FunctionDef | **87-98** | `08dfaf89-fa3a-4985-b0e0-21fc626c2d04` |
| `_close_driver` FunctionDef | **134-142** | `5a80ecaf-3e00-4a26-bab4-5c9bb936b65a` |

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/core/indexing_worker_pkg/vectorize_after_index.py")
```

**Out of scope — no change needed:**
`_create_svo_manager` (lines 100-107) uses no `CodeDatabase` — leave unchanged.
`_load_config` (lines 71-78) uses no `CodeDatabase` — leave unchanged.

### 1. Replace `_create_database` (lines 87-98)

**Before:**
```python
def _create_database(db_path: Path) -> Any:
    """Create CodeDatabase using direct SQLite driver (same process as indexer)."""
    try:
        from code_analysis.core.database import CodeDatabase
        from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
        driver = SQLiteDriver()
        driver.connect({"path": str(db_path.resolve())})
        return CodeDatabase.from_existing_driver(driver)
    except Exception as e:
        logger.warning("Could not create database for %s: %s", db_path, e)
        return None
```

**After:** create DatabaseClient via InProcessRpcClient (no CodeDatabase, no direct SQL).

```json
{"action": "replace", "node_id": "08dfaf89-fa3a-4985-b0e0-21fc626c2d04", "code_lines": [
    "def _create_database(db_path: Path) -> Any:",
    "    \"\"\"Create DatabaseClient using InProcessRpcClient over a local SQLiteDriver.\"\"\"",
    "    try:",
    "        from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver",
    "        from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers",
    "        from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient",
    "        from code_analysis.core.database_client.client import DatabaseClient",
    "",
    "        driver = SQLiteDriver()",
    "        driver.connect({\"path\": str(db_path.resolve())})",
    "        handlers = RPCHandlers(driver)",
    "        ipc = InProcessRpcClient(handlers)",
    "        ipc.connect()",
    "        client = DatabaseClient(rpc_client=ipc)",
    "        return client",
    "    except Exception as e:",
    "        logger.warning(\"Could not create database for %s: %s\", db_path, e)",
    "        return None"
]}

### 2. Replace `_close_driver` (lines 134-142)

**Before:** closes `db.driver.conn` (CodeDatabase-specific internal attribute)
**After:** disconnect InProcessRpcClient and the underlying SQLiteDriver.

```json
{"action": "replace", "node_id": "5a80ecaf-3e00-4a26-bab4-5c9bb936b65a", "code_lines": [
    "def _close_driver(db: Any) -> None:",
    "    \"\"\"Disconnect InProcessRpcClient (which also disconnects the underlying SQLiteDriver).\"\"\"",
    "    try:",
    "        rpc_client = getattr(db, \"rpc_client\", None)",
    "        if rpc_client is not None:",
    "            rpc_client.disconnect()  # InProcessRpcClient.disconnect() already calls driver.disconnect()",
    "    except Exception as e:",
    "        logger.debug(\"Error disconnecting rpc_client: %s\", e)"
]}
```

**Why no `_in_process_driver` attribute:** `InProcessRpcClient.disconnect()` already
calls `self.handlers.driver.disconnect()` internally (verified at `in_process_rpc_client.py:54`),
so an explicit second call via a stored driver reference is redundant.
The driver is also reachable via `client.rpc_client.handlers.driver` if needed.

### 3. Update docstring of `vectorize_file_after_index` (line 31)
**Before:** `Uses direct CodeDatabase + SVOClientManager to run vectorize_file_immediately.`
**After:** `Uses DatabaseClient via InProcessRpcClient + SVOClientManager to run vectorize_file_immediately.`

Use `cst_get_node_by_range(start_line=31, end_line=31)` to find and replace the docstring line.

## Validation sequence
1. `lint_code(file_path="code_analysis/core/indexing_worker_pkg/vectorize_after_index.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. Test: trigger file indexing and verify vectorization completes
5. Check DB: verify `embedding_vector` populated for indexed file

## Risk: MEDIUM
Replaces the database connection strategy. The `_vectorize_file_immediately` function
calls `db.vectorize_file_immediately(...)` which does not yet exist on DatabaseClient.
This will cause a runtime AttributeError until step 10 resolves it.
Option: temporarily disable `_vectorize_file_immediately` or leave step 06 blocked until step 10.