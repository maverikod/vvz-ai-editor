# Step 09: update.py — create update_file_data_via_driver (standalone function)

## Target files
- **NEW FILE:** `code_analysis/core/database/files/update_standalone.py`
- `code_analysis/core/database/files/update.py` — keep as-is (backward compat for CodeDatabase)

## Architecture check
`update_file_data` is a CodeDatabase mixin (401 lines) that calls `analyze_file()` and
various DB methods. The goal: create a STANDALONE version accepting `BaseDatabaseDriver`.

**Correct path (NEW):**
`RPCHandlers.handle_index_file()` → `update_file_data_via_driver(driver)` →
`InProcessRpcClient(RPCHandlers(driver))` → `DatabaseClient(rpc_client=ipc)` → `analyze_file(database=client)`

**Key constraint: `analyze_file()` expects DatabaseClient, NOT BaseDatabaseDriver.**

From `commands/update_indexes_analyzer.py:34` (verified):
```python
def analyze_file(
    database: Any,  # annotation is Any but docstring says: "DatabaseClient instance"
    file_path: Path,
    project_id: str,
    root_path: Path,
    ...
) -> Dict[str, Any]:
```
All internal calls use `database.add_file(...)`, `database.save_ast_tree(...)`,
`database.add_class(...)` etc. — client API methods from `_ClientAPIFilesMixin`.
Passing a raw `BaseDatabaseDriver` will fail with AttributeError.

**Solution:** inside `update_file_data_via_driver`, wrap the driver in InProcessRpcClient:
```python
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_client.client import DatabaseClient

handlers = RPCHandlers(driver)
ipc = InProcessRpcClient(handlers)
ipc.connect()
client = DatabaseClient(rpc_client=ipc)
```
Then call `analyze_file(database=client, ...)`.

**Verified existing classes (all exist in production code):**
- `InProcessRpcClient(handlers: RPCHandlers)` — `database_client/in_process_rpc_client.py:38`
- `RPCHandlers(driver: BaseDatabaseDriver)` — `database_driver_pkg/rpc_handlers.py:42`
- `DatabaseClient(rpc_client=Optional[Any])` — `database_client/client.py:56` (keyword-only `rpc_client`) ✅
- `analyze_file(database: Any, ...)` — `commands/update_indexes_analyzer.py:34` ✅

## STOP before implementing — read these files first

1. `code_analysis/core/database/files/update.py` (full 401 lines) — understand all 14 `self.xxx()` calls
2. `code_analysis/commands/update_indexes_analyzer.py` — `analyze_file` signature and body
3. `code_analysis/core/database/files/atomic.py` — `update_file_data_atomic` (newer path)

**IMPORTANT:** check if `atomic.py` already contains a driver-based version of the update logic.
If `update_file_data_atomic` in `atomic.py` already uses `DatabaseClient`, this step may be
much simpler — it might just call that function.

## What to create

### New file: `code_analysis/core/database/files/update_standalone.py`

Use `cst_create_file` to create the new file.

The file contains `update_file_data_via_driver(driver, file_path, project_id, root_dir)`
which:
1. Wraps `driver` in `InProcessRpcClient → DatabaseClient`
2. Delegates to `analyze_file(database=client, ...)` (from update_indexes_analyzer)
3. Returns the same result dict as the original `update_file_data`

**Pattern:**
```python
"""
Standalone update_file_data using BaseDatabaseDriver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict

from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver

logger = logging.getLogger(__name__)


def update_file_data_via_driver(
    driver: BaseDatabaseDriver,
    file_path: str,
    project_id: str,
    root_dir: Path,
) -> Dict[str, Any]:
    """
    Update all database records for a file using a BaseDatabaseDriver.

    Creates an in-process DatabaseClient over the driver and delegates to analyze_file.
    This is the driver-process-safe alternative to CodeDatabase.update_file_data().

    Args:
        driver: Database driver (SQLiteDriver or PostgreSQLDriver).
        file_path: Absolute path to the file.
        project_id: Project UUID.
        root_dir: Project root directory.

    Returns:
        Per-file result dict (same structure as update_file_data).
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
        return analyze_file(
            database=client,
            file_path=Path(file_path),
            project_id=project_id,
            root_path=root_dir,
        )
    finally:
        ipc.disconnect()
```

**Note:** `analyze_file` handles all DB writes (AST, CST, entities, imports) internally
through the `DatabaseClient` API. The function result dict is the same as the original
`update_file_data` result dict (success, file_id, file_path, ast_updated, etc.).

## Implementation approach

1. Read `code_analysis/core/database/files/update.py` lines 1-401 to understand the flow
2. Read `code_analysis/commands/update_indexes_analyzer.py` to verify `analyze_file` covers all steps
3. Check `code_analysis/core/database/files/atomic.py` — may contain a driver-based shortcut
4. Create `update_standalone.py` using `cst_create_file()`
5. Validate with `lint_code` + `type_check_code` + `comprehensive_analysis(check_stubs=True)`

## Validation sequence
1. `lint_code(file_path="code_analysis/core/database/files/update_standalone.py", project_id=...)`
2. `type_check_code(file_path=...)`
3. `format_code(file_path=...)`
4. `comprehensive_analysis(file_path=..., check_stubs=True)`
5. Apply step 08 and run full reindex: `update_indexes(project_id=...)`
6. Verify: functions > 0, `cst_node_id` != "" in DB after reindex

## Risk: HIGH
Core indexing logic. Creating a new standalone function instead of rewriting 400 lines.
Must verify that `analyze_file()` covers all the same DB operations as `update_file_data`.
Do NOT guess — always read source before writing.
