"""
AI Editor daemon CLI — thin entry (C-001).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from .daemon_cli_commands import (
    cmd_restart,
    cmd_start,
    cmd_status,
    cmd_stop,
)

_ENV_AIEDMGR_CONFIG = "AIEDMGR_CONFIG"
_ENV_LEGACY_CONFIG = "CASMGR_CONFIG"
_SYSTEM_DEFAULT_CONFIG = Path("/etc/aiedmgr/config.json")
_LEGACY_SYSTEM_DEFAULT_CONFIG = Path("/etc/casmgr/config.json")
_CWD_CONFIG_NAME = "config.json"


def _resolve_config_path(cli_config: Optional[str]) -> Optional[str]:
    """
    Resolve ``config.json`` path by priority.

    1. ``--config`` from the CLI (must exist).
    2. ``AIEDMGR_CONFIG`` or legacy ``CASMGR_CONFIG`` (must exist if set).
    3. ``/etc/aiedmgr/config.json`` or legacy ``/etc/casmgr/config.json`` if present.
    4. ``./config.json`` under the current working directory if present.
    """

    if cli_config is not None and str(cli_config).strip() != "":
        p = Path(cli_config).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(f"error: config file not found: {p}", file=sys.stderr)
            return None
        return str(p)

    for env_name in (_ENV_AIEDMGR_CONFIG, _ENV_LEGACY_CONFIG):
        env_val = os.environ.get(env_name, "").strip()
        if not env_val:
            continue
        p = Path(env_val).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(
                f"error: {env_name} points to missing file: {p}",
                file=sys.stderr,
            )
            return None
        return str(p)

    for system_cfg in (_SYSTEM_DEFAULT_CONFIG, _LEGACY_SYSTEM_DEFAULT_CONFIG):
        if system_cfg.is_file():
            return str(system_cfg.resolve())

    cwd_cfg = (Path.cwd() / _CWD_CONFIG_NAME).resolve()
    if cwd_cfg.is_file():
        return str(cwd_cfg)

    print(
        "error: no config found; pass --config, set "
        f"{_ENV_AIEDMGR_CONFIG}, install {_SYSTEM_DEFAULT_CONFIG}, "
        f"or run from a directory containing {_CWD_CONFIG_NAME}.",
        file=sys.stderr,
    )
    return None


def _activate_project_root(config_path: str) -> str:
    """
    Set process ``cwd`` to the project root and return a project-relative config path.
    """

    resolved = Path(config_path).resolve()
    os.chdir(resolved.parent)
    try:
        return str(resolved.relative_to(resolved.parent))
    except ValueError:
        return str(resolved)


def server(argv: Optional[list[str]] = None) -> int:
    """
    Console entrypoint for the daemon manager (installed script: ``aiedmgr``).
    """

    parser = argparse.ArgumentParser(prog="aiedmgr")
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=(
            "Path to config.json (optional). If omitted: "
            f"{_ENV_AIEDMGR_CONFIG}, then {_SYSTEM_DEFAULT_CONFIG}, "
            f"then ./{_CWD_CONFIG_NAME} in the current directory."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    ns = parser.parse_args(argv)

    config_path_abs = _resolve_config_path(ns.config)
    if config_path_abs is None:
        return 2
    try:
        config_path = _activate_project_root(config_path_abs)
    except OSError as exc:
        print(
            f"error: cannot change to project root for config: {exc}",
            file=sys.stderr,
        )
        return 2

    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
    }
    return handlers[ns.cmd](config_path)


if __name__ == "__main__":
    raise SystemExit(server())
