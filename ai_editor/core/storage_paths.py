"""
Thin-server path resolver (workspace, logs, config-relative).

Resolves editor workspace root, server logs directory, and shared config-relative
path helpers for AI Editor Server (C-018). Legacy db/faiss/trash paths removed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_LOGS_DIR = "./logs"
DEFAULT_WORKSPACE_ROOT = "data/editor_workspaces"


@dataclass(frozen=True)
class StoragePaths:
    """
    Resolved absolute paths for thin AI Editor Server state (C-018).

    Attributes:
        config_dir: Directory containing the loaded config file.
        editor_workspace_dir: Root for Editor Session Directory trees.
        logs_dir: Server log directory (``server.log_dir``).
    """

    config_dir: Path
    editor_workspace_dir: Path
    logs_dir: Path


def _resolve_path(config_dir: Path, value: str) -> Path:
    """
    Resolve a config path value (absolute or relative to config_dir).

    Args:
        config_dir: Config directory.
        value: Path string.

    Returns:
        Resolved absolute Path.
    """

    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (config_dir / p).resolve()
    return p.resolve()


def load_raw_config(config_path: Path) -> dict[str, Any]:
    """
    Load raw JSON config from disk.

    Args:
        config_path: Path to JSON config.

    Returns:
        Parsed dict.
    """

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ai_editor_storage(config_data: Mapping[str, Any]) -> Mapping[str, Any]:
    ai_editor_cfg = config_data.get("ai_editor") or {}
    if not isinstance(ai_editor_cfg, Mapping):
        return {}
    storage_cfg = ai_editor_cfg.get("storage") or {}
    if not isinstance(storage_cfg, Mapping):
        return {}
    return storage_cfg


def resolve_logs_dir(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> Path:
    """
    Resolve configured server log directory (absolute).

    Uses ``server.log_dir`` from config, default ``./logs``, relative paths
    resolved against the config file's directory.
    """
    config_dir = Path(config_path).resolve().parent
    server = config_data.get("server") or {}
    if not isinstance(server, Mapping):
        server = {}
    log_dir_val = server.get("log_dir", DEFAULT_LOGS_DIR)
    if not isinstance(log_dir_val, str) or not log_dir_val.strip():
        log_dir_val = DEFAULT_LOGS_DIR
    return _resolve_path(config_dir, log_dir_val.strip())


def resolve_editor_workspace_dir(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> Path:
    """
    Resolve editor workspace root from ``ai_editor.storage.workspace_root`` (C-018).
    """
    config_dir = Path(config_path).resolve().parent
    storage_cfg = _ai_editor_storage(config_data)
    value = storage_cfg.get("workspace_root")
    if not isinstance(value, str) or not value.strip():
        value = DEFAULT_WORKSPACE_ROOT
    return _resolve_path(config_dir, value.strip())


def resolve_storage_paths(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> StoragePaths:
    """
    Resolve thin-server storage paths from config.

    Expected config shape:
        ai_editor.storage.workspace_root
        server.log_dir (optional, default ./logs)

    Args:
        config_data: Raw config dict.
        config_path: Path to config.json (used to resolve relative paths).

    Returns:
        StoragePaths with absolute resolved Paths.
    """

    config_dir = Path(config_path).resolve().parent
    return StoragePaths(
        config_dir=config_dir,
        editor_workspace_dir=resolve_editor_workspace_dir(
            config_data=config_data,
            config_path=config_path,
        ),
        logs_dir=resolve_logs_dir(
            config_data=config_data,
            config_path=config_path,
        ),
    )


def ensure_storage_dirs(paths: StoragePaths) -> None:
    """
    Ensure that workspace and log directories exist.

    Args:
        paths: StoragePaths.
    """

    paths.editor_workspace_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
