# Step 08: rpc_handlers_index_file.py — replace CodeDatabase with update_file_data_via_driver

## Target file
`code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py` (200 lines)

## Architecture check
`_RPCHandlersIndexFileMixin` is part of `RPCHandlers` — the UNIVERSAL DRIVER layer.
Runs INSIDE the driver process. `self.driver` = specific driver.

**Current (WRONG) path:**
RPCHandlers → `CodeDatabase.from_existing_driver(self.driver)` → `db.update_file_data()` mixin

**Correct path:**
RPCHandlers → `update_file_data_via_driver(self.driver, ...)` standalone function

**CANNOT use `DatabaseClient.index_file()` here** — `DatabaseClient` is a network client.
`DatabaseClient.index_file()` (at `client_api_files.py:509`) makes an RPC call to THIS VERY HANDLER.
Calling it here would create infinite recursive RPC.

## Depends on: Step 09 (update_standalone.py must exist first)
`update_file_data_via_driver` must exist in `code_analysis/core/database/files/update_standalone.py`
before this step is applied.

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Lines | node_id |
|---------|-------|---------|
| local `from code_analysis.core.database import CodeDatabase` import | **103** | `7080aed8-05d2-4dca-8fcd-cb830361caff` |
| `handle_index_file` FunctionDef | **54-200** | `cd1367b6-35fa-421c-903c-110363ca15c8` |
| try-block with `CodeDatabase.from_existing_driver(...)` | **108-125** | `42045c95-e111-4656-b90f-f30c4a9dbc85` |

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py")
```

### 1. Replace the try-block with CodeDatabase (lines 108-125)

**Before:**
```python
            try:
                db = CodeDatabase.from_existing_driver(self.driver)
                update_result = db.update_file_data(
                    file_path, project_id, Path(root_path)
                )
            except Exception as e:
                if not _is_fk_or_integrity_error(e):
                    raise
                logger.warning(
                    "[index_file] FK/integrity (project likely deleted): project_id=%s %s",
                    project_id,
                    e,
                )
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description="Project no longer exists (deleted during indexing)",
                )
```

**After:**
```python
            try:
                from code_analysis.core.database.files.update_standalone import (
                    update_file_data_via_driver,
                )
                logger.debug(
                    "[index_file] Using update_file_data_via_driver (no CodeDatabase)"
                )
                update_result = update_file_data_via_driver(
                    driver=self.driver,
                    file_path=file_path,
                    project_id=project_id,
                    root_dir=Path(root_path),
                )
            except Exception as e:
                if not _is_fk_or_integrity_error(e):
                    raise
                logger.warning(
                    "[index_file] FK/integrity (project likely deleted): project_id=%s %s",
                    project_id,
                    e,
                )
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description="Project no longer exists (deleted during indexing)",
                )
```

```json
{"action": "replace", "node_id": "42045c95-e111-4656-b90f-f30c4a9dbc85", "code_lines": [
    "try:",
    "    from code_analysis.core.database.files.update_standalone import (",
    "        update_file_data_via_driver,",
    "    )",
    "    logger.debug(",
    "        \"[index_file] Using update_file_data_via_driver (no CodeDatabase)\"",
    "    )",
    "    update_result = update_file_data_via_driver(",
    "        driver=self.driver,",
    "        file_path=file_path,",
    "        project_id=project_id,",
    "        root_dir=Path(root_path),",
    "    )",
    "except Exception as e:",
    "    if not _is_fk_or_integrity_error(e):",
    "        raise",
    "    # Project deleted during indexing (FK race). Return clear error; do not run cleanup.",
    "    logger.warning(",
    "        \"[index_file] FK/integrity (project likely deleted): project_id=%s %s\",",
    "        project_id,",
    "        e,",
    "    )",
    "    return ErrorResult(",
    "        error_code=ErrorCode.NOT_FOUND,",
    "        description=\"Project no longer exists (deleted during indexing)\",",
    "    )"
]}
```

### 2. Remove the local CodeDatabase import (line 103)

The import at line 103 (`from code_analysis.core.database import CodeDatabase`) is a local
import inside the function body. After replacing the try-block above, the import node
`7080aed8` still exists as a separate node above the try. Delete it.

```json
{"action": "delete", "node_id": "7080aed8-05d2-4dca-8fcd-cb830361caff"}
```
**Note:** also remove the `logger.debug` line that references `from_existing_driver`
(lines 105–107 in the original file). **It is NOT inside the try-block** — it sits
immediately before `try:` at line 108, so it is **NOT** removed automatically by
replacing the try-block. Add a separate `delete` operation:

```
# Step 1: find and delete the logger.debug node at lines 105-107
debug_node = cst_get_node_by_range(tree_id=tree_id, start_line=105, end_line=107)
cst_modify_tree(tree_id=tree_id, operations=[{"action": "delete", "node_id": debug_node["node_id"]}])
```

Do this as a **separate operation before** replacing the try-block, or after — either
order works since the nodes are independent. Re-verify node_id via `cst_find_node`
if the line numbers have shifted since this step was written.

## Validation sequence
## Validation sequence
1. `lint_code(file_path="code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. Run full reindex: `update_indexes(project_id=...)`
5. Verify: functions > 0, `cst_node_id` != "" in DB after reindex

## Risk: HIGH
Core indexing pipeline. Must complete step 09 first.
`update_file_data_via_driver` must be created and tested before applying this step.