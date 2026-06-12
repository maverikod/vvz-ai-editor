"""
Map ai_editor ``code_analysis_server`` config to code-analysis-client settings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from code_analysis_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
)

from ai_editor.core.config_placeholders import resolve_config_placeholders
from ai_editor.core.env_loader import load_dotenv_near_config
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.storage_paths import load_raw_config


def ca_section_to_server_config(section: Mapping[str, Any]) -> Dict[str, Any]:
    """Wrap flat ``code_analysis_server`` block as CA server config dict."""
    ssl = section.get("ssl")
    client_ssl = dict(ssl) if isinstance(ssl, dict) else {}
    server = {
        key: value
        for key, value in section.items()
        if key not in ("server_id", "command_transport")
    }
    return {"server": server, "client": {"ssl": client_ssl}}


def ca_section_to_adapter_settings(section: Mapping[str, Any]) -> Dict[str, Any]:
    """Map ai_editor ``code_analysis_server`` to adapter-style settings."""
    return adapter_settings_from_server_config(ca_section_to_server_config(section))


def build_jsonrpc_kwargs_from_ca_section(section: Mapping[str, Any]) -> Dict[str, Any]:
    """Build JsonRpcClient kwargs from ai_editor ``code_analysis_server`` section."""
    settings = ca_section_to_adapter_settings(section)
    return adapter_settings_to_jsonrpc_kwargs(
        settings,
        timeout=float(section.get("timeout") or 60.0),
        check_hostname=bool(section.get("check_hostname", False)),
    )


def load_resolved_ca_section(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load ``code_analysis_server`` with env and placeholder resolution."""
    path = config_path
    if path is None:
        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            cfg_path = getattr(cfg, "config_path", None)
            if isinstance(cfg_path, str) and cfg_path.strip():
                path = Path(cfg_path).expanduser().resolve()
        except Exception:
            path = None
    if path is None:
        path = (Path.cwd() / "config.json").resolve()

    load_dotenv_near_config(path)
    raw = load_raw_config(path)
    resolved, unresolved = resolve_config_placeholders(raw)
    if unresolved:
        names = ", ".join(item.name for item in unresolved)
        raise ValidationError(
            f"Unresolved config placeholders: {names}",
            field="config",
            details={"placeholders": [item.name for item in unresolved]},
        )
    section = resolved.get("code_analysis_server")
    if not isinstance(section, dict) or not section:
        raise ValidationError(
            "Missing required section: code_analysis_server",
            field="code_analysis_server",
            details={"config_path": str(path)},
        )
    return {
        **section,
        "server_id": str(section.get("server_id") or "code-analysis-server"),
        "command_transport": str(section.get("command_transport") or "direct"),
    }
