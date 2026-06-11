"""
Current ai-editor server instance identity (shared-DB partition key).

Config is read from ``core`` only (never from ``commands``) so workers and the DB
driver process can resolve ``registration.instance_uuid`` without breaking the
command → DatabaseClient → driver → DB chain.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional


def _resolve_active_config_path() -> Path:
    """Resolve server ``config.json`` (same rules as daemon / workers)."""
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        cfg_path = getattr(cfg, "config_path", None)
        if isinstance(cfg_path, str) and cfg_path.strip():
            return Path(cfg_path).expanduser().resolve()
    except Exception:
        pass
    env_cfg = (
        os.environ.get("AIEDMGR_CONFIG", "").strip()
        or os.environ.get("CASMGR_CONFIG", "").strip()
    )
    if env_cfg:
        return Path(env_cfg).expanduser().resolve()
    return (Path.cwd() / "config.json").resolve()


def server_instance_id_from_config(config: Mapping[str, Any]) -> str:
    """Return ``registration.instance_uuid`` from a loaded config mapping."""
    reg = config.get("registration")
    if not isinstance(reg, Mapping):
        return ""
    return str(reg.get("instance_uuid") or "").strip()


def get_server_instance_id(*, config: Optional[Mapping[str, Any]] = None) -> str:
    """
    Return this server's instance UUID (global partition key for watch_dirs/projects).

    Resolution order when ``config`` is omitted:
    1. ``AI_EDITOR_SERVER_INSTANCE_ID`` environment variable
    2. ``registration.instance_uuid`` from active ``config.json``
    """
    if config is None:
        env_sid = os.environ.get("AI_EDITOR_SERVER_INSTANCE_ID", "").strip()
        if env_sid:
            return env_sid
        from ai_editor.core.storage_paths import load_raw_config

        config = load_raw_config(_resolve_active_config_path())
    sid = server_instance_id_from_config(config)
    if not sid:
        raise RuntimeError(
            "registration.instance_uuid is required in server config "
            "(server instance partition key for watch_dirs and projects)"
        )
    return sid
