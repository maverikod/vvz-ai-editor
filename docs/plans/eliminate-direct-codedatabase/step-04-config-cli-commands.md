# Step 04: config_cli_commands.py — replace CodeDatabase with SQLiteDriver.sync_schema()

## Target file
`code_analysis/cli/config_cli_commands.py` (118 lines)

## Architecture check
`cmd_schema` is a CLI utility that applies schema migration on an existing DB file.
There is NO running driver process here — this is a standalone admin CLI command.

Correct fix: use `SQLiteDriver` directly and call `driver.sync_schema(schema_definition, backup_dir)`.
`sync_schema()` EXISTS on `SQLiteDriver` at `code_analysis/core/database_driver_pkg/drivers/sqlite.py:476`.
`get_schema_definition()` EXISTS at `code_analysis/core/database/schema_definition.py:30`.

**Note on dual SQLiteDriver classes:** there are two classes named `SQLiteDriver` in the codebase:
- `code_analysis.core.database_driver_pkg.drivers.sqlite.SQLiteDriver` — the **RPC process driver** (use this one)
- `code_analysis.core.db_driver.sqlite.SQLiteDriver` — the legacy factory driver used by CodeDatabase internally

Always import from `database_driver_pkg.drivers.sqlite`, not from `db_driver.sqlite`.

**sync_schema signature (verified):**
`SQLiteDriver.sync_schema(self, schema_definition: Dict[str, Any], backup_dir: Optional[str] = None) -> Dict[str, Any]`

`schema_definition` is required. `backup_dir` is **optional** (defaults to `None`),
but should always be passed explicitly here so backups are created before schema changes.
`backup_dir` must be computed from `db_path` (CLI has no `storage.backup_dir`).

This is NOT an RPC-layer violation — the CLI is an admin tool, not a runtime data path.

## Verified node IDs (always re-verify via cst_load_file before editing)

| Element | Line | node_id |
|---------|------|---------|
| `from ..core.database import CodeDatabase` | 15 | `9073626a-b5f1-42de-af53-34d01cad927f` |
| `cmd_schema` FunctionDef | 25-72 | `4664a190-c09e-4816-a9a7-38a997dc0dc2` |

## What to change

```
tree_id = cst_load_file(file_path="code_analysis/cli/config_cli_commands.py")
```

### 1. Remove CodeDatabase import (line 15)
**Before:** `from ..core.database import CodeDatabase`
**After:** DELETE this line

```json
{"action": "delete", "node_id": "9073626a-b5f1-42de-af53-34d01cad927f"}
```

### 2. Replace CodeDatabase usage in `cmd_schema` (lines 55-67 inside the try block)

Replace the whole `cmd_schema` FunctionDef (node_id `4664a190`) with the corrected version.

**Key changes inside the try block:**
- Remove `os.environ["CODE_ANALYSIS_DB_DRIVER"] = "1"` (no longer needed)
- Replace `CodeDatabase(driver_config)` + `db.sync_schema()` + `db.close()` with:
  - Import `SQLiteDriver` from `database_driver_pkg.drivers.sqlite`
  - Import `get_schema_definition` from `code_analysis.core.database.schema_definition`
  - Create driver, connect, get schema definition, compute backup_dir from db_path, sync, disconnect

```json
{"action": "replace", "node_id": "4664a190-c09e-4816-a9a7-38a997dc0dc2", "code_lines": [
    "def cmd_schema(args: argparse.Namespace) -> int:",
    "    \"\"\"",
    "    Apply database schema (tables and indexes) to the configured database.",
    "",
    "    Stops server/workers first if database is in use, then runs migration.",
    "    \"\"\"",
    "    config_path = Path(args.file)",
    "    if not config_path.exists():",
    "        print(f\"Error: config file not found: {config_path}\", file=sys.stderr)",
    "        return 1",
    "    try:",
    "        with open(config_path, \"r\", encoding=\"utf-8\") as f:",
    "            config = json.load(f)",
    "        db_path = _get_db_path_from_config(config)",
    "    except Exception as e:",
    "        print(f\"Error: {e}\", file=sys.stderr)",
    "        return 1",
    "",
    "    if not args.no_stop and _db_open_by_other_processes(db_path):",
    "        print(\"Database is in use. Stopping server and workers...\", flush=True)",
    "        if _stop_server(config_path):",
    "            print(\"Server stopped.\", flush=True)",
    "        else:",
    "            print(",
    "                \"Warning: could not stop server. If migration fails, run manually:\\n\"",
    "                \"  python -m code_analysis.cli.server_manager_cli --config config.json stop\",",
    "                file=sys.stderr,",
    "            )",
    "",
    "    from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver",
    "    from code_analysis.core.database.schema_definition import get_schema_definition",
    "",
    "    try:",
    "        print(\"Connecting...\", flush=True)",
    "        driver = SQLiteDriver()",
    "        driver.connect({\"path\": str(db_path)})",
    "        print(\"Applying schema (compare, backup if needed, migrate)...\", flush=True)",
    "        schema_definition = get_schema_definition()",
    "        db_path_obj = Path(str(db_path))",
    "        if db_path_obj.parent.name == \"data\":",
    "            backup_dir = str(db_path_obj.parent.parent / \"backups\")",
    "        else:",
    "            backup_dir = str(db_path_obj.parent / \"backups\")",
    "        result = driver.sync_schema(schema_definition, backup_dir)",
    "        driver.disconnect()",
    "        n = len(result.get(\"changes_applied\") or [])",
    "        if result.get(\"backup_uuid\"):",
    "            print(f\"Backup: {result['backup_uuid']}\", flush=True)",
    "        print(f\"Schema applied. Changes: {n}\", flush=True)",
    "        return 0",
    "    except Exception as e:",
    "        print(f\"Schema apply failed: {e}\", file=sys.stderr)",
    "        return 1"
]}
```

## Validation sequence
1. `lint_code(file_path="code_analysis/cli/config_cli_commands.py", project_id=...)`
2. `format_code(file_path=...)`
3. `type_check_code(file_path=...)`
4. Manual test: `python -m code_analysis.cli.server_manager_cli --config config.json schema`

## Risk: LOW
CLI admin tool, not a runtime data path. Clear replacement with direct driver call.
`get_schema_definition()` returns the same schema that `CodeDatabase._get_schema_definition()` returns.
`backup_dir` logic mirrors `CodeDatabase._do_sync_schema()`.