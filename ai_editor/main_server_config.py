"""
Build server engine config (host, port, SSL) for main entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from typing import Any, Dict


def build_server_config(
    server_host: str,
    server_port: int,
    app_config: dict[str, Any],
) -> Dict[str, Any]:
    """Build server_config dict for ServerEngine (hypercorn). Adds SSL if configured."""
    server_config = {
        "host": server_host,
        "port": server_port,
        "log_level": "info",
        "reload": False,
        "workers": 1,
    }

    from mcp_proxy_adapter.core.app_factory.ssl_config import build_server_ssl_config

    try:
        ssl_engine_config = build_server_ssl_config(app_config)
        if ssl_engine_config:
            server_config.update(ssl_engine_config)
    except ValueError as e:
        print(f"❌ SSL configuration invalid: {e}", file=sys.stderr)
        sys.exit(1)

    return server_config
