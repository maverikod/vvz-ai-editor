r"""
_common — shared bootstrap for ``client/examples`` (operational manual section).

================================================================================
NAME
================================================================================
    ``ai_editor_client`` examples — internal helper module ``_common``.

================================================================================
SYNOPSIS
================================================================================
    Other example scripts import this module **after** prepending ``client/`` to
    ``sys.path``. You normally do not run ``_common.py`` directly.

================================================================================
DESCRIPTION
================================================================================
This module centralises three concerns that every runnable example needs:

1. **Discovering the installable package directory** (``…/ai_editor/client``)
   so that ``import ai_editor_client`` works **without** a prior
   ``pip install ai-editor-client`` when you execute scripts from a git
   checkout.

2. **Changing the process current working directory** to the **repository root**
   (parent of ``client/``). Server ``config.json`` files almost always use
   **relative** paths for TLS material (e.g. ``mtls_certificates/…``). The
   helper :func:`adapter_settings_to_jsonrpc_kwargs` resolves those paths with
   :func:`pathlib.Path.resolve`, which is relative to **cwd**. If cwd is wrong,
   certificate paths break and HTTPS/mTLS connections fail with opaque TLS
   errors.

3. **Resolving which ``config.json`` to load** — either the path in environment
   variable ``AI_EDITOR_CONFIG`` or, by default,
   ``<repo_root>/config.json``.

Together, these behaviours mirror how operators run the daemon
(``aiedmgr --config config.json``): same file, same cwd semantics.

================================================================================
ENVIRONMENT
================================================================================
AI_EDITOR_CONFIG
    Optional. Absolute or relative path to the JSON file passed to
    :func:`ai_editor_client.load_server_config`. When unset,
    :func:`default_config_path` uses ``<repo_root>/config.json``.

================================================================================
FILES
================================================================================
    ``<repo_root>/config.json`` — primary server configuration (default).

    ``<repo_root>/mtls_certificates/…`` — typical layout for client/server TLS
    files referenced from ``config.json`` (paths are repo-relative).

================================================================================
SEE ALSO
================================================================================
    * PyPI package: ``ai-editor-client`` (import name ``ai_editor_client``).
    * ``client/ai_editor_client/config.py`` — mapping server JSON to
      :class:`mcp_proxy_adapter.client.jsonrpc_client.client.JsonRpcClient`
      keyword arguments.
    * ``client/examples/run_all_examples.py`` — exhaustive live-server walkthrough.
    * ``client/examples/README.md`` — short operator cheat-sheet.

================================================================================
AUTHOR
================================================================================
    Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_EXAMPLES_DIR = Path(__file__).resolve().parent
_CLIENT_DIR = _EXAMPLES_DIR.parent
_REPO_ROOT = _CLIENT_DIR.parent


def ensure_client_package_on_path() -> None:
    """Insert ``client/`` at the front of ``sys.path`` if missing.

    **Rationale:** In a git checkout the importable distribution lives under
    ``…/repository/client/``, not at repository root. Example scripts must
    therefore prepend that directory **before** ``import ai_editor_client``.
    After ``pip install ai-editor-client`` this call is redundant but
    harmless (the package is already on ``sys.path``).
    """
    p = str(_CLIENT_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def chdir_repo_root() -> None:
    """``os.chdir`` to the repository root (parent directory of ``client/``).

    **Rationale:** ``config.json`` almost always references TLS files with
    repository-relative paths. :func:`pathlib.Path.resolve` (used inside
    ``ai_editor_client.config``) is evaluated against the process **current
    working directory**. Failing to chdir produces misleading “file not found”
    or TLS handshake errors even when certificates exist on disk.
    """
    os.chdir(_REPO_ROOT)


def default_config_path() -> Path:
    """Return the JSON path used by all examples.

    Resolution order:

    1. Environment variable ``AI_EDITOR_CONFIG`` if set (any string accepted
       by :class:`pathlib.Path` — relative paths resolve against **cwd**, not
       against the repository; prefer absolute paths in automation).
    2. Otherwise ``<repo_root>/config.json`` where ``repo_root`` is the parent of
       the ``client/`` directory containing this file tree.

    Returns:
        Expanded path (``~`` resolved for the environment-variable branch only;
        the default branch is already absolute in typical checkouts).
    """
    return Path(
        os.environ.get("AI_EDITOR_CONFIG", str(_REPO_ROOT / "config.json"))
    ).expanduser()
