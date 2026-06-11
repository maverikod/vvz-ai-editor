#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    run_all_examples — **operator manual** for ``ai_editor_client`` (executable).

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    aiedmgr --config config.json start    # or your own supervisor
    python client/examples/run_all_examples.py

Optional configuration path::

    export AI_EDITOR_CONFIG=/abs/other/config.json
    python client/examples/run_all_examples.py

================================================================================
DESCRIPTION
================================================================================
This program is the **canonical integration test narrative** for the PyPI
package **ai-editor-client** (import name ``ai_editor_client``). It
sequentially exercises **every public symbol** exported from
``ai_editor_client.__init__`` plus a **representative subset** of the
underlying ``mcp-proxy-adapter`` :class:`~mcp_proxy_adapter.client.jsonrpc_client.client.JsonRpcClient`
surface that typical automation relies on.

Why this exists (PyPI “man page” role)
    PyPI project pages rarely host a full UNIX **man(1)** volume. Long **module
    docstrings** in runnable examples are therefore the **offline operator
    manual**: they document purpose, prerequisites, diagnostics, exit codes, and
    cross-references the same way man pages do.

Architecture (two layers)
    #. **Transport + JSON-RPC** — ``JsonRpcClient`` (from ``mcp-proxy-adapter``):
       HTTPS/mTLS, JSON-RPC envelope, ``help``, ``health``, ``echo``,
       ``execute_command``, ``execute_command_unified``, HTTP helpers such as
       ``get_heartbeat``, optional ``get_commands_list``.
    #. **Domain façade** — :class:`ai_editor_client.client.CodeAnalysisAsyncClient`:
       thin async methods plus **server-schema-backed** validation helpers that
       call ``help(cmdname=…)`` to retrieve the live JSON Schema before invoking
       a command.

Sections executed (in order)
    The ``_run`` coroutine prints banner lines ``== N) … ==`` and invokes the
    following **async** sections:

    1. **Config helpers (no TCP)** — :func:`~ai_editor_client.load_server_config`,
       :func:`~ai_editor_client.adapter_settings_from_server_config`,
       :func:`~ai_editor_client.adapter_settings_to_jsonrpc_kwargs`. Proves
       that configuration parsing is deterministic without a daemon.

    2. **All constructors** — each variant opens a short-lived client, awaits
       ``rpc.health()``, then **closes** explicitly:

       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.from_server_config_path`
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.from_server_config`
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.from_adapter_settings`
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.from_jsonrpc_kwargs`
       * Direct ``CodeAnalysisAsyncClient(**kwargs)`` (same kwargs as
         ``JsonRpcClient``).

    3. **Long-lived client** — one instance reused for:

       * ``rpc.health``, ``rpc.get_heartbeat``, optional ``rpc.get_commands_list``
         (wrapped in ``try/except`` because some deployments disable GET routes).
       * ``rpc.help()`` (global catalogue) and ``rpc.help("list_projects")``
         (per-command schema source used by validation).
       * ``rpc.echo`` (adapter self-test).
       * ``rpc.execute_command("list_projects", …)`` (raw JSON-RPC style).
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.call` /
         :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.call_unified`
         (façade wrappers).
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.get_command_schema`
         with cache + ``refresh`` behaviour.
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.call_validated`
         and :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.call_unified_validated`
         (the latter demonstrates an **async** ``status_hook`` coroutine).
       * :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.clear_command_schema_cache`
         and re-fetch to prove cache invalidation.
       * :class:`~ai_editor_client.commands_proxy.ValidatedCommandsProxy`
         (``client.commands``): ``fetch_schema``, ``invoke`` (dict + kwargs merge),
         dynamic attribute ``list_projects``, ``clear_schema_cache``.
       * Low-level schema helpers:
         :func:`~ai_editor_client.parse_schema_from_help_payload`,
         :func:`~ai_editor_client.fetch_command_schema_from_server`,
         :func:`~ai_editor_client.prepare_params_for_schema`,
         :func:`~ai_editor_client.validate_params_against_schema`, and a
         deliberate :exc:`~ai_editor_client.ClientValidationError` path.

    4. **Async context manager** — ``async with CodeAnalysisAsyncClient.from_server_config_path(...)``
       proves ``__aenter__`` / ``__aexit__`` call :meth:`~ai_editor_client.client.CodeAnalysisAsyncClient.close`.

    5. **Sibling example scripts** — subprocess invocations of every other live-server
       driver under ``client/examples/`` (``ex_minimal_validated.py``,
       ``ex_session_view_subordinates.py``, ``ex_file_sessions.py``). Offline
       ``ex_config_only.py`` is covered by section 1.

    6. **Explicit close** — the long-lived instance is closed in ``finally`` to
       mirror scripts that do **not** use ``async with``.

**Not** covered here (by design)
    * Every one of the **100+** ``JsonRpcClient`` methods (transfer sessions,
      websocket job streaming, etc.). Consult **upstream**
      ``mcp-proxy-adapter`` documentation for those.
    * ``use_cmd_endpoint=True`` branches — behaviour depends on server OpenAPI
      routing; enable only when you understand ``/cmd`` semantics.

================================================================================
PREREQUISITES
================================================================================
    * Python **3.10+**.
    * Installable client on ``sys.path`` (editable ``pip install -e ./client``
      **or** rely on this script prepending ``client/``).
    * **Running** ai-editor daemon compatible with the chosen ``config.json``.
    * TLS trust material readable from cwd after ``chdir_repo_root()`` (see
      ``client/examples/_common.py``).

================================================================================
ENVIRONMENT
================================================================================
AI_EDITOR_CONFIG
    Optional path override for the JSON file consumed by
    :func:`~ai_editor_client.load_server_config`.

================================================================================
OUTPUT
================================================================================
    Progress banners on stdout. **No stable JSON** — this is a narrative
    integration driver, not a monitoring probe.

================================================================================
EXIT STATUS
================================================================================
    **0** — Every internal assertion succeeded.

    **1** — Any unhandled exception (printed with Python traceback on stderr).
    Typical causes: daemon down, TLS mismatch, wrong host/port, schema drift
    causing validation failure, command-level ``ErrorResult`` mapped to an
    exception by the adapter client.

================================================================================
DIAGNOSTICS
================================================================================
    * Re-run with ``PYTHONASYNCIODEBUG=1`` for extra asyncio scheduling detail.
    * Inspect ``logs/`` under the repository when using the stock ``config.json``.
    * Compare ``adapter_settings_from_server_config`` output with
      ``ex_config_only.py`` when debugging path resolution.

================================================================================
SEE ALSO
================================================================================
    * ``client/examples/ex_config_only.py`` — offline configuration chapter.
    * ``client/examples/ex_minimal_validated.py`` — minimal validated RPC.
    * ``client/examples/ex_session_view_subordinates.py`` — ``session_view`` and
      ``subordinate_session_*`` via ``FileSessionClient``.
    * ``client/examples/ex_file_sessions.py`` — full session/transfer integration.
    * ``client/examples/_common.py`` — bootstrap semantics (cwd, ``sys.path``).
    * ``client/examples/README.md`` — short index (this file’s docstring is the
      **long-form** manual).
    * PyPI project **ai-editor-client** (when published).

================================================================================
BUGS
================================================================================
    ``rpc.list_commands`` is **intentionally omitted** — on some server builds
    the legacy JSON-RPC ``list`` command returns HTTP 500. Prefer ``help`` or
    ``get_commands_list`` (the latter is attempted best-effort in this script).

================================================================================
AUTHOR
================================================================================
    Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

# -----------------------------------------------------------------------------
# Path bootstrap (examples/ is not an installed package)
# -----------------------------------------------------------------------------
_EXAMPLES = Path(__file__).resolve().parent
_CLIENT = _EXAMPLES.parent
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from _common import (  # noqa: E402
    chdir_repo_root,
    default_config_path,
    ensure_client_package_on_path,
)

ensure_client_package_on_path()

from _client_api_inventory import verify_examples_cover_client_api  # noqa: E402

from ai_editor_client import (  # noqa: E402
    ClientValidationError,
    CodeAnalysisAsyncClient,
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    fetch_command_schema_from_server,
    load_server_config,
    parse_schema_from_help_payload,
    prepare_params_for_schema,
    validate_params_against_schema,
)
from ai_editor_client.server_api import (  # noqa: E402
    assert_file_session_facade_complete,
    assert_transfer_facade_complete,
)

CLIENT_API_COVERAGE = frozenset(
    {
        "config.load_server_config",
        "config.adapter_settings_from_server_config",
        "config.adapter_settings_to_jsonrpc_kwargs",
        "validation.prepare_params_for_schema",
        "validation.validate_params_against_schema",
        "server_schema.parse_schema_from_help_payload",
        "server_schema.fetch_command_schema_from_server",
        "server_api.assert_file_session_facade_complete",
        "server_api.assert_transfer_facade_complete",
        "CodeAnalysisAsyncClient.__init__",
        "CodeAnalysisAsyncClient.from_jsonrpc_kwargs",
        "CodeAnalysisAsyncClient.from_adapter_settings",
        "CodeAnalysisAsyncClient.from_server_config",
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.rpc",
        "CodeAnalysisAsyncClient.commands",
        "CodeAnalysisAsyncClient.clear_command_schema_cache",
        "CodeAnalysisAsyncClient.get_command_schema",
        "CodeAnalysisAsyncClient.call_validated",
        "CodeAnalysisAsyncClient.call_unified_validated",
        "CodeAnalysisAsyncClient.call",
        "CodeAnalysisAsyncClient.call_unified",
        "CodeAnalysisAsyncClient.close",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "ValidatedCommandsProxy.clear_schema_cache",
        "ValidatedCommandsProxy.fetch_schema",
        "ValidatedCommandsProxy.invoke",
        "ValidatedCommandsProxy.__getattr__",
    }
)


def _ok(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


async def ex_load_server_config_and_adapter_helpers(cfg_path: Path) -> None:
    r"""Section 1 — **CONFIGURATION** (no network).

    Demonstrates the three **pure** helpers that turn a daemon ``config.json``
    into ``JsonRpcClient`` keyword arguments:

    * ``load_server_config`` — filesystem read + JSON object validation.
    * ``adapter_settings_from_server_config`` — normalises bind addresses
      (``0.0.0.0`` → ``127.0.0.1``) and attaches TLS paths for ``https`` when
      certificates are present (same behaviour operators rely on in CI).
    * ``adapter_settings_to_jsonrpc_kwargs`` — produces the kwargs dict used by
      ``CodeAnalysisAsyncClient(**kwargs)``.

    This section answers: *“Is my config file parseable and self-consistent
    before I even start the daemon client?”*
    """
    raw = load_server_config(cfg_path)
    _ok("server" in raw, "config must contain server")
    settings = adapter_settings_from_server_config(raw)
    _ok("host" in settings and "port" in settings, "adapter settings missing host/port")
    kwargs = adapter_settings_to_jsonrpc_kwargs(settings, timeout=30.0)
    _ok(kwargs["port"] == settings["port"], "port mismatch in jsonrpc kwargs")
    _ok("protocol" in kwargs, "jsonrpc kwargs missing protocol")
    assert_file_session_facade_complete()
    assert_transfer_facade_complete()


async def ex_constructors(cfg_path: Path) -> None:
    r"""Section 2 — **CONSTRUCTORS** (short-lived TCP probes).

    Each factory path is exercised independently: a client is created, a
    single ``rpc.health()`` JSON-RPC call proves TLS + routing work, then
    ``await client.close()`` tears the adapter HTTP stack down.

    Factories covered:

    * ``from_server_config_path`` — highest-level: path string or
      ``pathlib.Path``.
    * ``from_server_config`` — you already hold the dict (e.g. loaded from a
      secrets manager).
    * ``from_adapter_settings`` — intermediate dict (used by some deployment
      templates).
    * ``from_jsonrpc_kwargs`` — explicit kwargs (mirrors ``JsonRpcClient``).
    * ``CodeAnalysisAsyncClient(**kwargs)`` — synonym of the previous line but
      documents that the façade is a thin wrapper.

    Operators comparing this to **curl**: ``health`` is the lightweight probe
    equivalent to ``curl -k https://host:port/health`` but via JSON-RPC.
    """
    cfg = load_server_config(cfg_path)
    settings = adapter_settings_from_server_config(cfg)
    jr = adapter_settings_to_jsonrpc_kwargs(settings, timeout=25.0)

    c1 = CodeAnalysisAsyncClient.from_server_config_path(cfg_path, timeout=25.0)
    await c1.rpc.health()
    await c1.close()

    c2 = CodeAnalysisAsyncClient.from_server_config(cfg, timeout=25.0)
    await c2.rpc.health()
    await c2.close()

    c3 = CodeAnalysisAsyncClient.from_adapter_settings(settings, timeout=25.0)
    await c3.rpc.health()
    await c3.close()

    c4 = CodeAnalysisAsyncClient.from_jsonrpc_kwargs(**jr)
    await c4.rpc.health()
    await c4.close()

    c5 = CodeAnalysisAsyncClient(**jr)
    await c5.rpc.health()
    await c5.close()


async def ex_rpc_methods(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3a — **JsonRpcClient** primitives used in production.

    * ``health`` — JSON-RPC health (differs from HTTP ``GET /heartbeat``).
    * ``get_heartbeat`` — REST shim; useful when a load balancer probes HTTP.
    * ``get_commands_list`` — **best-effort**; some hardened deployments return
      ``403``/``404``. Failure is logged but does not fail the suite.
    * ``help()`` / ``help("list_projects")`` — the second form returns the
      **authoritative JSON Schema** later reused by ``call_validated``.
    * ``echo`` — adapter self-test (round-trip message).
    * ``execute_command`` — lowest-level “invoke MCP command by name”.

    Why so many probes? Operators need to know **which layer** failed: TLS,
    routing, JSON-RPC envelope, or application ``ErrorResult``.
    """
    h = await client.rpc.health()
    _ok(isinstance(h, dict), "rpc.health() must return dict")

    hb = await client.rpc.get_heartbeat()
    _ok(isinstance(hb, dict), "rpc.get_heartbeat() must return dict")

    try:
        gcl = await client.rpc.get_commands_list()
        _ok(isinstance(gcl, dict), "rpc.get_commands_list() must return dict")
    except Exception as exc:
        print(f"  (optional rpc.get_commands_list skipped: {exc})")

    hall = await client.rpc.help()
    _ok(hall.get("success") is True, "help() without cmdname must succeed")

    hlp = await client.rpc.help("list_projects")
    _ok(hlp.get("success") is True, "help(list_projects) must succeed")

    echo = await client.rpc.echo(message="ai_editor_client examples")
    _ok(isinstance(echo, dict), "echo must return dict")

    ex = await client.rpc.execute_command("list_projects", {"include_deleted": False})
    _ok(isinstance(ex, dict), "execute_command must return dict")


async def ex_call_and_unified(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3b — **Façade** ``call`` / ``call_unified``.

    ``call`` maps directly to ``JsonRpcClient.execute_command`` (single round
    trip, no queue polling heuristics).

    ``call_unified`` maps to ``execute_command_unified`` — the same JSON-RPC
    command, but the adapter may treat long-running jobs differently (polling,
    websocket upgrades, etc.). Here ``expect_queue=False`` keeps the example
    deterministic for the read-only ``list_projects`` command.
    """
    r1 = await client.call("list_projects", {"include_deleted": False})
    _ok(isinstance(r1, dict), "call must return dict")

    r2 = await client.call_unified(
        "list_projects",
        {"include_deleted": False},
        expect_queue=False,
        auto_poll=True,
        timeout=60.0,
    )
    _ok(isinstance(r2, dict), "call_unified must return dict")


async def ex_validated_client_methods(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3c — **Server-schema validation** on the façade.

    Steps:

    #. ``get_command_schema`` — first call performs ``help(cmdname=…)`` over
       the wire; subsequent calls reuse the in-memory cache until
       ``clear_command_schema_cache`` runs.
    #. ``call_validated`` — validates then calls ``execute_command``.
    #. ``call_unified_validated`` — same validation, then
       ``execute_command_unified``; passes an **async** ``status_hook`` to show
       how to observe intermediate adapter states (hook body is a no-op aside
       from recording that it ran).
    #. ``clear_command_schema_cache`` + ``get_command_schema(..., refresh=True)``
       — proves operators can flush caches after ``reload`` on the server.

    **Limitation:** only JSON-schema-shaped checks run locally; business rules
    still execute server-side.
    """

    schema = await client.get_command_schema("list_projects", refresh=False)
    _ok(schema.get("type") == "object", "list_projects schema must be object")

    r1 = await client.call_validated(
        "list_projects", {"include_deleted": False}, refresh_schema=False
    )
    _ok(isinstance(r1, dict), "call_validated must return dict")

    events: List[str] = []

    async def _hook(_: Dict[str, Any]) -> None:
        events.append("tick")

    r2 = await client.call_unified_validated(
        "list_projects",
        {"include_deleted": False},
        refresh_schema=False,
        expect_queue=False,
        timeout=60.0,
        status_hook=_hook,
    )
    _ok(isinstance(r2, dict), "call_unified_validated must return dict")

    client.clear_command_schema_cache()
    schema2 = await client.get_command_schema("list_projects", refresh=True)
    _ok(isinstance(schema2, dict), "refresh_schema must yield dict")


async def ex_commands_proxy(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3d — **Dynamic** ``client.commands`` proxy.

    The proxy object implements:

    * ``fetch_schema`` — thin alias of ``get_command_schema`` (reads well in
      tutorials).
    * ``invoke("cmd", params=..., **kwargs)`` — merges mapping + keyword args
      then calls ``call_validated``.
    * Attribute access ``client.commands.list_projects`` — syntactic sugar for
      ``call_validated("list_projects", kwargs)``.
    * ``clear_schema_cache`` — forwards to ``CodeAnalysisAsyncClient.clear_command_schema_cache``.

    This section exists because many users prefer **dot notation** over string
    command names, while still keeping validation identical.
    """
    sch = await client.commands.fetch_schema("list_projects", refresh=False)
    _ok(sch.get("type") == "object", "commands.fetch_schema must return object schema")

    r1 = await client.commands.invoke(
        "list_projects", params={"include_deleted": False}
    )
    _ok(isinstance(r1, dict), "commands.invoke must return dict")

    r2 = await client.commands.invoke("list_projects", include_deleted=True)
    _ok(isinstance(r2, dict), "commands.invoke kwargs merge must return dict")

    r3 = await client.commands.list_projects(include_deleted=False)
    _ok(isinstance(r3, dict), "dynamic commands.list_projects must return dict")

    client.commands.clear_schema_cache()
    await client.commands.list_projects(include_deleted=False)


async def ex_low_level_schema_and_validation(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3e — **Library-grade** schema helpers (advanced).

    Shows how to compose the same primitives the façade uses inside your own
    middleware:

    * ``parse_schema_from_help_payload`` — when you already obtained a raw
      ``help`` dict (e.g. from logging).
    * ``fetch_command_schema_from_server`` — convenience ``await rpc.help`` +
      parse (duplicates façade logic — use one or the other).
    * ``prepare_params_for_schema`` / ``validate_params_against_schema`` —
      reusable locally before you batch commands.

    Ends with a **negative test** expecting ``ClientValidationError`` when a
    boolean field receives a string.
    """
    raw_help = await client.rpc.help("list_projects")
    schema = parse_schema_from_help_payload(raw_help, command_name="list_projects")
    _ok(schema.get("type") == "object", "parsed schema must be object")

    schema2 = await fetch_command_schema_from_server(client.rpc, "list_projects")
    _ok(
        schema2.get("properties"),
        "fetch_command_schema_from_server must include properties",
    )

    params = {"include_deleted": False}
    prepared = prepare_params_for_schema(params, schema2)
    validate_params_against_schema(prepared, schema2, command_name="list_projects")

    try:
        validate_params_against_schema(
            {"include_deleted": "not-a-bool"},
            schema2,
            command_name="list_projects",
        )
    except ClientValidationError:
        pass
    else:
        raise AssertionError("expected ClientValidationError for wrong type")


async def ex_async_context_manager(cfg_path: Path) -> None:
    r"""Section 4 — **Context manager** protocol.

    ``async with CodeAnalysisAsyncClient(...)`` guarantees ``close()`` runs.
    This matters because ``JsonRpcClient`` keeps persistent ``httpx`` clients;
    leaking instances exhausts sockets in long-running notebooks.
    """
    async with CodeAnalysisAsyncClient.from_server_config_path(
        cfg_path, timeout=25.0
    ) as c:
        h = await c.rpc.health()
        _ok(isinstance(h, dict), "context manager client must work")


async def ex_close_explicit(client: CodeAnalysisAsyncClient) -> None:
    r"""Section 3 cleanup — explicit ``await client.close()``.

    Called from a ``finally`` block to mirror scripts that are **not** written
    with ``async with`` (legacy procedural style).
    """
    await client.close()


_LIVE_SIBLING_SCRIPTS: Tuple[Tuple[str, List[str]], ...] = (
    ("ex_minimal_validated.py", []),
    ("ex_universal_files.py", []),
    ("ex_session_view_subordinates.py", []),
    ("ex_file_sessions.py", []),
)


def ex_run_sibling_scripts(examples_dir: Path) -> None:
    r"""Section 5 — run every other live-server example script as a subprocess.

    Each script must exit **0** on success. Failures propagate as
    ``AssertionError`` with captured stdout/stderr.
    """
    for script_name, extra_args in _LIVE_SIBLING_SCRIPTS:
        script = examples_dir / script_name
        if not script.is_file():
            raise AssertionError(f"missing example script: {script}")
        print(f"== 5) sibling script: {script_name} ==")
        proc = subprocess.run(
            [sys.executable, str(script), *extra_args],
            cwd=str(examples_dir.parent.parent),
            capture_output=True,
            text=True,
        )
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.returncode != 0:
            err = (
                proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
            )
            raise AssertionError(f"{script_name} failed: {err}")


async def _run() -> None:
    """Execute all example sections in order (see module **DESCRIPTION**)."""
    chdir_repo_root()
    cfg_path = default_config_path()
    if not cfg_path.is_file():
        raise SystemExit(f"Config not found: {cfg_path}")

    print("== 1) Config helpers (no network) ==")
    await ex_load_server_config_and_adapter_helpers(cfg_path)

    print("== 2) All constructors + rpc.health ==")
    await ex_constructors(cfg_path)

    print("== 3) Long-lived client: rpc.*, call*, validated*, commands.* ==")
    client = CodeAnalysisAsyncClient.from_server_config_path(cfg_path, timeout=60.0)
    try:
        await ex_rpc_methods(client)
        await ex_call_and_unified(client)
        await ex_validated_client_methods(client)
        await ex_commands_proxy(client)
        await ex_low_level_schema_and_validation(client)
    finally:
        await ex_close_explicit(client)

    print("== 4) async context manager ==")
    await ex_async_context_manager(cfg_path)

    print("== 5) sibling live-server example scripts ==")
    ex_run_sibling_scripts(_EXAMPLES)

    print("== 6) client API coverage registry ==")
    verify_examples_cover_client_api(_EXAMPLES)
    print("  all public client methods covered by examples")

    print("All example sections passed.")


def main() -> None:
    """CLI entry point: ``asyncio.run(_run())``; sets process exit code **1** on any exception."""
    try:
        asyncio.run(_run())
    except Exception as exc:  # pragma: no cover - manual run
        print(f"FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
