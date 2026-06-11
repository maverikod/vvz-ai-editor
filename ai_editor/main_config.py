"""
Config load, validation, storage, and app_config merge for main entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Tuple

from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

from ai_editor.core.storage_paths import (
    ensure_storage_dirs,
    resolve_storage_paths,
)
from ai_editor.main_server_presentation import sync_registration_presentation


def load_config_and_validate(
    args: Any,
) -> Tuple[Path, dict[str, Any]]:
    """
    Load config file and validate. Exits on error.
    Returns (config_path, full_config).
    """
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
        print(
            "   Generate one with: python -m ai_editor.cli.config_cli generate",
            file=sys.stderr,
        )
        sys.exit(1)

    from ai_editor.core.env_loader import load_dotenv_near_config

    load_dotenv_near_config(config_path)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            full_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in configuration file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to read configuration file: {e}", file=sys.stderr)
        sys.exit(1)

    return (config_path, full_config)


def ensure_storage_and_load_app_config(
    config_path: Path,
    full_config: dict[str, Any],
    args: Any,
) -> Tuple[dict[str, Any], SimpleConfig, str, int]:
    """
    Ensure storage dirs, load SimpleConfig, merge app_config, resolve server host/port.
    Exits on error. Returns (app_config, simple_config, server_host, server_port).
    """
    try:
        storage_paths = resolve_storage_paths(
            config_data=full_config,
            config_path=config_path.resolve(),
        )
        ensure_storage_dirs(storage_paths)
    except Exception as e:
        print(f"❌ Failed to prepare storage directories: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        simple_config = SimpleConfig(str(config_path))
        model = simple_config.load()
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if args.host:
        simple_config.model.server.host = args.host
    if args.port:
        simple_config.model.server.port = args.port

    from ai_editor.core.settings_manager import get_settings

    settings = get_settings()
    server_host = (
        settings.get("server_host") or args.host or simple_config.model.server.host
    )
    server_port = (
        settings.get("server_port") or args.port or simple_config.model.server.port
    )

    app_config = simple_config.to_dict()
    _merge_config_sections(app_config, full_config)
    sync_registration_presentation(app_config)

    return (app_config, simple_config, server_host, server_port)


def _merge_config_sections(
    app_config: dict[str, Any],
    full_config: dict[str, Any],
) -> None:
    """Merge top-level and ``registration`` keys from raw JSON into app_config."""
    for key, value in full_config.items():
        if key == "registration":
            continue
        if key not in app_config:
            app_config[key] = value

    src_reg = full_config.get("registration")
    if not isinstance(src_reg, dict):
        return
    dst_reg = app_config.get("registration")
    if not isinstance(dst_reg, dict):
        app_config["registration"] = dict(src_reg)
        return
    for reg_key, reg_value in src_reg.items():
        dst_reg[reg_key] = reg_value


def apply_global_config(
    config_path: Path,
    simple_config: SimpleConfig,
    app_config: dict[str, Any],
) -> None:
    """Update global config instance used by adapter internals."""
    from mcp_proxy_adapter.config import get_config

    cfg = get_config()
    cfg.config_path = str(config_path)
    setattr(cfg, "model", simple_config.model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    sync_registration_presentation(cfg.config_data)

    if app_config.get("enable_qa_mcp_hooks") is True:
        if not (os.environ.get("AI_EDITOR_ENABLE_QA_MCP_HOOKS") or "").strip():
            os.environ["AI_EDITOR_ENABLE_QA_MCP_HOOKS"] = "1"
