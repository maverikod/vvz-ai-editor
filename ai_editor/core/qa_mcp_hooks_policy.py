"""
Whether QA MCP / RPC hooks (db retry injection, plan hooks) are enabled.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os


def _truthy_env() -> bool:
    v = (os.environ.get("AI_EDITOR_ENABLE_QA_MCP_HOOKS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _truthy_server_config() -> bool:
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        data = getattr(cfg, "config_data", None)
        if isinstance(data, dict) and data.get("enable_qa_mcp_hooks") is True:
            return True
    except Exception:
        pass
    return False


def qa_mcp_hooks_enabled_for_mcp_commands() -> bool:
    """MCP commands: env wins; else optional ``server.enable_qa_mcp_hooks`` in loaded config."""
    return _truthy_env() or _truthy_server_config()


def qa_mcp_hooks_enabled_for_driver_rpc() -> bool:
    """Driver RPC handlers: environment only (subprocess inherits from parent after ``apply_global_config``)."""
    return _truthy_env()
