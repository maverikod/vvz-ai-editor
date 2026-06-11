# Step 05: main_workers.py — replace CodeDatabase schema init with direct driver

## Target file
`code_analysis/main_workers.py` (560 lines)

## Architecture check
`startup_vectorization_worker` creates CodeDatabase ONLY to trigger `sync_schema()`
for initial DB creation. There is no running driver process yet at this point.
Correct fix: call `driver.sync_schema(schema_definition, backup_dir)` directly.

`sync_schema()` EXISTS on both drivers:
- `SQLiteDriver` at `database_driver_pkg/drivers/sqlite.py:476` ✅
- `PostgreSQLDriver` at `database_driver_pkg/drivers/postgres.py:532` ✅ (updated from stale :509)

**Signature:** `sync_schema(schema_definition: Dict[str, Any], backup_dir: Optional[str] = None)`.
`backup_dir` is **optional** (default `None`) but should always be passed explicitly.
`schema_definition` is obtained from `get_schema_definition()` (schema_definition.py:30).
`backup_dir` is obtained from `storage.backup_dir` (already in scope).

**Important:** `driver_config["type"]` can be `"sqlite"`, `"sqlite_proxy"`, or `"postgres"`.
For PostgreSQL the driver is `PostgreSQLDriver`; for SQLite variants it is `SQLiteDriver`.
Both are imported from `database_driver_pkg.drivers.*`, NOT from `db_driver.*`.

**Note on dual SQLiteDriver classes:** always import from
`code_analysis.core.database_driver_pkg.drivers.sqlite`, NOT from `code_analysis.core.db_driver.sqlite`.

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Lines | node_id |
|---------|-------|---------|
| `if not db_path_obj.exists():` block | **289-331** | `cabe32fd-27e5-4719-8aff-eaf7e27f1d9b` |

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/main_workers.py")
```

### 1. Replace the `if not db_path_obj.exists():` block (lines 289-331)

Replace If node `cabe32fd` with the corrected version that uses driver directly.

**Before (summary):**
```python
if not db_path_obj.exists():
    ...imports CodeDatabase...
    init_database = CodeDatabase(driver_config=driver_config)
    init_database.close()
```

**After:** branch on `driver_config["type"]` to pick the correct driver class.
The `storage.backup_dir` is already in scope at this point.

```json
{"action": "replace", "node_id": "cabe32fd-27e5-4719-8aff-eaf7e27f1d9b", "code_lines": [
    "if not db_path_obj.exists():",
    "    logger.info(f\"Database file not found, creating new database at {db_path}\")",
    "    try:",
    "        from code_analysis.core.database_driver_pkg.drivers.sqlite import (",
    "            SQLiteDriver,",
    "        )",
    "        from code_analysis.core.database_driver_pkg.drivers.postgres import (",
    "            PostgreSQLDriver,",
    "        )",
    "        from code_analysis.core.database.base import (",
    "            create_driver_config_for_worker,",
    "        )",
    "        from code_analysis.core.config import get_driver_config",
    "        from code_analysis.core.database.schema_definition import get_schema_definition",
    "",
    "        db_path_obj.parent.mkdir(parents=True, exist_ok=True)",
    "",
    "        driver_config = None",
    "        try:",
    "            driver_config = get_driver_config(app_config)",
    "        except Exception as e:",
    "            logger.debug(f\"Could not get driver config from config: {e}\")",
    "",
    "        if not driver_config:",
    "            driver_config = create_driver_config_for_worker(",
    "                db_path=db_path_obj,",
    "                driver_type=\"sqlite_proxy\",",
    "                backup_dir=storage.backup_dir,",
    "            )",
    "        else:",
    "            if \"config\" in driver_config and \"path\" in driver_config[\"config\"]:",
    "                driver_config[\"config\"][\"path\"] = str(db_path_obj)",
    "            if storage.backup_dir and \"config\" in driver_config:",
    "                driver_config[\"config\"][\"backup_dir\"] = str(storage.backup_dir)",
    "",
    "        schema_definition = get_schema_definition()",
    "        backup_dir = str(storage.backup_dir) if storage.backup_dir else None",
    "        driver_type = driver_config.get(\"type\", \"sqlite\") if driver_config else \"sqlite\"",
    "        driver_cfg = driver_config.get(\"config\", {\"path\": str(db_path_obj)}) if driver_config else {\"path\": str(db_path_obj)}",
    "",
    "        if driver_type == \"postgres\":",
    "            init_driver = PostgreSQLDriver()",
    "        else:",
    "            init_driver = SQLiteDriver()",
    "        init_driver.connect(driver_cfg)",
    "        init_driver.sync_schema(schema_definition, backup_dir)",
    "        init_driver.disconnect()",
    "        logger.info(f\"Created new database at {db_path}\")",
    "    except Exception as e:",
    "        logger.warning(",
    "            f\"Failed to create database: {e}, continuing anyway\",",
    "            exc_info=True,",
    "        )"
]}
```

## Validation sequence
1. `lint_code(file_path="code_analysis/main_workers.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. Restart vectorization worker, verify it starts without errors

## Risk: LOW
Only affects initial DB creation path (runs once when DB doesn’t exist).
No runtime data impact. Both SQLite and PostgreSQL paths are handled.