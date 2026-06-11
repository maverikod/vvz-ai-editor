"""
Print server startup info (no daemon/foreground).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any


def print_startup_info(
    *,
    config_path: Path,
    server_host: str,
    server_port: int,
    server_config: dict[str, Any],
    app_config: dict[str, Any],
) -> None:
    """Print server startup info without actually starting the server process."""
    print("ℹ️  ai-editor-server startup info (no --daemon):", flush=True)
    print(f"   Config: {config_path}", flush=True)
    print(f"   Host: {server_host}", flush=True)
    print(f"   Port: {server_port}", flush=True)
    ssl_keys = {"ssl_certfile", "ssl_keyfile", "ssl_ca_certs"}
    ssl_enabled = any(k in server_config and server_config.get(k) for k in ssl_keys)
    print(f"   mTLS/SSL: {'enabled' if ssl_enabled else 'disabled'}", flush=True)
    queue_cfg = app_config.get("queue") or {}
    if isinstance(queue_cfg, dict):
        print(
            f"   Queue: {'enabled' if queue_cfg.get('enabled', False) else 'disabled'}",
            flush=True,
        )
    print("   Engine: hypercorn (default)", flush=True)
    print(
        "   Start: python -m ai_editor.main --daemon --config <path>",
        flush=True,
    )
