#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_config_only — print JSON-RPC connection kwargs from ``config.json`` **without** TCP.

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    python client/examples/ex_config_only.py

================================================================================
DESCRIPTION
================================================================================
This script is the **offline** chapter of the examples “manual”: it exercises
only the **pure configuration** helpers shipped with ``ai_editor_client``:

* :func:`ai_editor_client.load_server_config` — read and parse the JSON
  object used by the daemon.
* :func:`ai_editor_client.adapter_settings_from_server_config` — derive the
  small “adapter-style” dict (``host``, ``port``, ``protocol``, optional
  ``ssl``) understood by the client layer. This includes the same pragmatic
  rules as production tooling, e.g. rewriting bind-all addresses
  (``0.0.0.0`` / ``::``) to ``127.0.0.1`` for outbound connections, and
  attaching TLS file paths for ``https`` when certificates are present.
* :func:`ai_editor_client.adapter_settings_to_jsonrpc_kwargs` — the final
  mapping into keyword arguments for
  :class:`mcp_proxy_adapter.client.jsonrpc_client.client.JsonRpcClient`.

**No network calls** are made. The program prints a JSON object to stdout. For
safety, **secrets are redacted**: keys ``cert``, ``key``, ``ca``, and ``token``
are omitted from the printed structure (only metadata such as ``host`` and
``protocol`` appear). Operators who need to verify absolute cert paths should
inspect ``config.json`` or temporarily print inside a private debugger session.

================================================================================
PREREQUISITES
================================================================================
    * Python **3.10+** with the ``ai_editor_client`` package importable
      (either ``pip install -e ./client`` from the repo, or rely on this
      script’s ``sys.path`` tweak that adds ``client/``).
    * Working directory is switched to the **repository root** via
      ``_common.chdir_repo_root()`` so relative TLS paths resolve.

================================================================================
OUTPUT
================================================================================
    UTF-8 JSON on stdout, two top-level keys:

    * ``config_path`` — absolute path that was loaded.
    * ``jsonrpc_safe`` — kwargs safe to log (TLS material and token removed).

================================================================================
EXIT STATUS
================================================================================
    **0** — Success.

    **non-zero** — Uncaught exception (missing file, invalid JSON, I/O error).

================================================================================
SEE ALSO
================================================================================
    * ``client/examples/run_all_examples.py`` — full live API tour.
    * ``client/examples/ex_minimal_validated.py`` — minimal authenticated RPC.
    * PyPI: https://pypi.org/project/ai-editor-client/ (when published).

================================================================================
AUTHOR
================================================================================
    Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import json
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

from ai_editor_client import (  # noqa: E402
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    load_server_config,
)

CLIENT_API_COVERAGE = frozenset(
    {
        "config.load_server_config",
        "config.adapter_settings_from_server_config",
        "config.adapter_settings_to_jsonrpc_kwargs",
    }
)


def main() -> None:
    """Print redacted JSON-RPC kwargs (see **OUTPUT** in the module docstring)."""
    chdir_repo_root()
    path = default_config_path()
    cfg = load_server_config(path)
    settings = adapter_settings_from_server_config(cfg)
    jr = adapter_settings_to_jsonrpc_kwargs(settings, timeout=30.0)
    safe = {k: v for k, v in jr.items() if k not in ("cert", "key", "ca", "token")}
    print(json.dumps({"config_path": str(path), "jsonrpc_safe": safe}, indent=2))


if __name__ == "__main__":
    main()
