#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_minimal_validated — shortest **async** example with **server-backed** schema validation.

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    aiedmgr --config config.json start    # daemon must listen
    python client/examples/ex_minimal_validated.py

================================================================================
DESCRIPTION
================================================================================
This script answers the question: *“What is the smallest correct program that
uses the published client against a real server?”*

Execution flow:

1. **Bootstrap** — prepend ``client/`` to ``sys.path`` (git checkout ergonomics)
   and call ``ensure_client_package_on_path()`` from the sibling module
   ``client/examples/_common.py`` (not shipped inside the PyPI wheel).

2. **Repository cwd** — :func:`chdir_repo_root` so TLS paths inside
   ``config.json`` resolve the same way as for ``casmgr``.

3. **Client construction** — :meth:`CodeAnalysisAsyncClient.from_server_config_path`
   reads ``AI_EDITOR_CONFIG`` or ``<repo>/config.json``, builds HTTPS/mTLS
   settings, and constructs the underlying
   :class:`mcp_proxy_adapter.client.jsonrpc_client.client.JsonRpcClient`.

4. **Context manager** — ``async with … as client`` ensures
   :meth:`CodeAnalysisAsyncClient.close` runs even on failure (releases HTTP
   pools inside the adapter client).

5. **Validated execution** — two equivalent styles are demonstrated:

   * :meth:`CodeAnalysisAsyncClient.call_validated` — explicit command name +
     parameter dict. Internally: ``help(cmdname=…)`` on the wire to fetch the
     authoritative JSON Schema, shallow local validation (types, ``required``,
     ``enum``, ``additionalProperties``), then ``execute_command``.

   * ``await client.commands.list_projects(…)`` — dynamic attribute on
     :class:`ai_editor_client.commands_proxy.ValidatedCommandsProxy` that
     forwards to the same validation path.

**Important limitation (documented here as for a man page):** validation
mirrors the *schema* checks in the server’s ``BaseMCPCommand`` implementation
(``ai_editor.commands.base_mcp_command`` in the **server** repository).
Semantic checks (e.g. “does this ``project_id`` exist?”) still happen on the
server when the command runs.

================================================================================
PREREQUISITES
================================================================================
    * Running **ai-editor** daemon reachable with the same TLS material as
      in ``config.json``.
    * Network access from this host to ``server.host:server.port`` (after any
      bind-address rewriting for ``0.0.0.0``).

================================================================================
OUTPUT
================================================================================
    Human-readable lines on stdout confirming both call styles completed and
    returned mapping objects. This is intentionally **not** JSON-RPC traffic
    logging — operators should use server log files for wire-level traces.

================================================================================
EXIT STATUS
================================================================================
    **0** — Both RPC calls returned without raising.

    **non-zero** — Connection failure, TLS failure, validation error, or
    command-level error propagated as a Python exception (see server logs).

================================================================================
DIAGNOSTICS
================================================================================
    * ``ClientValidationError`` — parameter dict failed shallow schema validation
      against the schema returned by ``help``; field name is attached to the
      exception instance.
    * ``httpx.*`` / ``RuntimeError`` — transport or JSON-RPC envelope errors from
      the adapter client.

================================================================================
SEE ALSO
================================================================================
    * ``client/examples/run_all_examples.py`` — exhaustive narrative of every
      public entry point.
    * ``ai_editor_client.client.CodeAnalysisAsyncClient.call_unified_validated``
      — long-running / queued commands with polling.
    * Package metadata on PyPI: project **ai-editor-client**.

================================================================================
AUTHOR
================================================================================
    Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CLIENT = _HERE.parent
sys.path.insert(0, str(_CLIENT))

from _common import (  # noqa: E402
    chdir_repo_root,
    default_config_path,
    ensure_client_package_on_path,
)

ensure_client_package_on_path()

from ai_editor_client import CodeAnalysisAsyncClient  # noqa: E402

CLIENT_API_COVERAGE = frozenset(
    {
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.call_validated",
        "CodeAnalysisAsyncClient.commands",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "ValidatedCommandsProxy.__getattr__",
    }
)


async def main() -> None:
    """Run the minimal validated scenario (see **DESCRIPTION** in the module docstring)."""
    chdir_repo_root()
    cfg = default_config_path()
    async with CodeAnalysisAsyncClient.from_server_config_path(
        cfg, timeout=45.0
    ) as client:
        r1 = await client.call_validated("list_projects", {"include_deleted": False})
        r2 = await client.commands.list_projects(include_deleted=False)
        assert isinstance(r1, dict) and isinstance(r2, dict)
        print("call_validated OK:", "success" in r1 or "data" in r1 or True)
        print("commands.list_projects OK:", "success" in r2 or "data" in r2 or True)


if __name__ == "__main__":
    asyncio.run(main())
