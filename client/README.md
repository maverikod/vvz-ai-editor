# code-analysis-client

Async Python client for the **code-analysis** server. It wraps `mcp-proxy-adapter`'s `JsonRpcClient`, so you get the adapter's built-in methods (queue, transfer, `help`, `health`, …) plus thin helpers to run any registered server command. On the thin AI Editor Server, file editing uses `universal_file_*` commands only; queue polling helpers remain for generic RPC but are not part of the file workflow surface.

## Install

```bash
pip install code-analysis-client
```

## Usage

```python
import asyncio
from code_analysis_client import CodeAnalysisAsyncClient


async def main() -> None:
    client = CodeAnalysisAsyncClient(
        protocol="https",
        host="127.0.0.1",
        port=15001,
        cert="/path/client.crt",
        key="/path/client.key",
        ca="/path/ca.crt",
        timeout=120.0,
    )
    async with client:
        h = await client.rpc.help()
        r = await client.call("list_projects", {"include_deleted": False})
    print(h, r)


asyncio.run(main())
```

Build client settings from the same JSON shape as the pipeline adapter settings (`host`, `port`, `protocol`, optional `ssl` with `cert` / `key` / `ca` or `*_path` aliases), or from a full server `config.json` object.

```python
from code_analysis_client import CodeAnalysisAsyncClient

client = CodeAnalysisAsyncClient.from_server_config(config_dict, timeout=60.0)
```

Queued/long commands: use `client.call_unified(..., expect_queue=True, auto_poll=True)` or the underlying `client.rpc.execute_command_unified(...)`.

## Validation using the server schema

The authoritative input schema is whatever the running server returns from **`help`** with `cmdname` set to the command. The client calls that, optionally caches the result, performs the same shallow checks as the server's `BaseMCPCommand` (types, `required`, `enum`, `additionalProperties`), then runs the command.

```python
async with CodeAnalysisAsyncClient(host="127.0.0.1", port=15001) as client:
    # Explicit
    out = await client.call_validated(
        "list_projects",
        {"include_deleted": False},
    )
    # Dynamic wrapper: same as call_validated("list_projects", {...})
    out = await client.commands.list_projects(include_deleted=False)
    # After server reload
    client.clear_command_schema_cache()
```

Use `call_unified_validated` when you need queue polling. Pass `refresh_schema=True` on a single call to bypass the in-memory schema cache.

## File Workflow (C-009)

The thin AI Editor Server exposes file editing only through `UniversalFileClient` (`client.universal_files`). One file at a time follows **open → edit → write → close**. Optional read-only inspection during an open file uses `preview` (`universal_file_preview`). Every stage requires the same CA Session `session_id`, `project_id`, and (where applicable) `file_path`.

### Workflow stages

1. **Open** (`universal_file_open`) — agent supplies CA `session_id`; server locks file on upstream CA, creates local Editor Session Directory and File Subtree, stores Origin Snapshot, creates Edit Subdirectory. Use `create=True` with `initial_content` for new files.
2. **Edit** (`universal_file_edit`) — mutations apply only to the Edit Subdirectory; Origin Snapshot unchanged.
3. **Write** (`universal_file_write`) — compares Origin Snapshot to edited content; `write_mode="preview"` returns local diff without upstream upload; commit mode uploads to CA on change and refreshes Origin Snapshot on success.
4. **Close** (`universal_file_close`) — unlocks file on CA, removes local File Subtree; removes Editor Session Directory when last file in session closes.

### Minimal async example

```python
import asyncio
import uuid

from ai_editor_client import CodeAnalysisAsyncClient


async def main() -> None:
    # Created upstream via CA session_create (outside this client package).
    ca_session_id = str(uuid.uuid4())

    async with CodeAnalysisAsyncClient.from_server_config_path("config.json") as client:
        uf = client.universal_files
        project_id = "..."
        file_path = "src/example.py"

        await uf.open(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=file_path,
        )
        await uf.preview(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=file_path,
        )
        await uf.edit(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=file_path,
            operations=[{"action": "replace", "start_line": 1, "end_line": 1, "code": "# edited\n"}],
        )
        await uf.write(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=file_path,
            write_mode="preview",
        )
        await uf.close(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=file_path,
        )


asyncio.run(main())
```

Full runnable script: `client/examples/ex_universal_files.py`.

### CA Session ID contract (C-003)

- The **agent** creates the CA Session on Code Analysis Server (`session_create`) **before** calling any editor `universal_file_*` command. That RPC is **not** part of the thin editor MCP surface and is **not** wrapped by `UniversalFileClient`.
- The agent passes the **same** `session_id` string to every `universal_file_open`, `universal_file_edit`, `universal_file_write`, `universal_file_close`, and `universal_file_preview` call for the workflow.
- Do **not** treat the `open` response as the source of `session_id` for later calls. If the server echoes `session_id`, it must match the agent-supplied value; the agent already owns the identifier.
- The agent decides when to `write` (commit or preview) and `close`; the client library does not manage CA session lifecycle.

## High-level facades (thin AI Editor Server / C-016)

The supported public MCP commands for file workflow are `UNIVERSAL_FILE_COMMANDS` plus `health` only (`CLIENT_FACADE_COMMANDS` in `ai_editor_client.server_api`). CST commands (`cst_*`, `list_cst_blocks`, `query_cst`) and legacy direct file I/O are in `REMOVED_COMMANDS` — not on the thin server, not documented as supported. `client.universal_files` is the **only** supported high-level facade for file editing.

| Facade | Property | Server commands | Status |
|--------|----------|-----------------|--------|
| Universal file workflow | `client.universal_files` | `universal_file_open`, `universal_file_edit`, `universal_file_write`, `universal_file_close`, `universal_file_preview` | **Supported** (C-009 / C-016) |
| Infrastructure | `client.call("health", {})` or adapter `health` | `health` | **Supported** |
| Generic RPC | `client.call` / `client.commands.<name>` | any command returned by live `help()` on connected server | Escape hatch; thin server exposes only rows above for files |
| Legacy sessions + transfer | `client.file_sessions` | `session_*`, `subordinate_session_*`, `project_file_transfer_*`, `project_file_advisory_lock_batch` | **Deprecated** — `DEPRECATED_CLIENT_FACADE_COMMANDS`; not registered on thin editor server |

Canonical command lists: `ai_editor_client.server_api` exports `UNIVERSAL_FILE_COMMANDS`, `INFRASTRUCTURE_COMMANDS`, `CLIENT_FACADE_COMMANDS`, `DEPRECATED_CLIENT_FACADE_COMMANDS`, and `REMOVED_COMMANDS`.

Sync checks (in-process registry):

```bash
pytest tests/test_client_server_api_sync.py -v
```

These tests assert `CLIENT_FACADE_COMMANDS` matches the live server registry (C-016) and `REMOVED_COMMANDS` are absent from the server (C-022).

Package version is in ``client/ai_editor_client/version.txt`` (synced with the
root ``code-analysis`` project via ``scripts/sync_code_analysis_client_version.py``).

## Examples (this repository)

Runnable scripts live under `client/examples/`. **Long-form "man page" style
documentation** is embedded in the **module docstrings** of those Python files
(see `client/examples/README.md` for how to read them).

| Script | Purpose |
|--------|---------|
| `ex_universal_files.py` | **Primary:** C-009 File Workflow demo — all `UniversalFileClient` methods with agent-supplied CA `session_id` (C-003) |
| `ex_minimal_validated.py` | Smallest validated RPC example (`health` / generic call) |
| `ex_config_only.py` | Parse `config.json` without TCP |
| `run_all_examples.py` | Runs sibling live scripts (includes universal files demo) |
| `ex_session_view_subordinates.py` | **Deprecated** — legacy CA session API; not thin editor MCP |
| `ex_file_sessions.py` | **Deprecated** — legacy sessions/transfer; not thin editor MCP |

For file editing on thin AI Editor Server, start with `ex_universal_files.py`; do not use `ex_file_sessions.py` or `ex_session_view_subordinates.py` as file workflow templates.

```bash
aiedmgr --config config.json start
python client/examples/ex_universal_files.py
```

## Development

From the repository root:

```bash
pip install -e ./client
pytest tests/test_code_analysis_client.py
```

### Releasing to PyPI (version = root ``code-analysis`` project)

The client wheel version is read from ``client/code_analysis_client/version.txt``.
That file must match ``[project].version`` in the **repository root**
``pyproject.toml``. Sync before build:

```bash
python scripts/sync_code_analysis_client_version.py
cd client && python -m build && twine check dist/* && twine upload dist/*
```
