"""
Create FastAPI app and register startup/shutdown events.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp_proxy_adapter.api.core.app_factory import AppFactory

from ai_editor.main_app_events import register_startup_shutdown_events
from ai_editor.main_server_presentation import resolve_server_presentation
from ai_editor.openapi_mcp_proxy_compat import patch_app_openapi_for_mcp_proxy


def create_app_with_events(
    app_config: dict[str, Any],
    config_path: Path,
) -> Any:
    """Create FastAPI app and register startup/shutdown events."""
    title, description, version = resolve_server_presentation(app_config)
    app_factory = AppFactory()
    app = app_factory.create_app(
        title=title,
        description=description,
        version=version,
        app_config=app_config,
        config_path=str(config_path),
    )

    register_startup_shutdown_events(app, app_config)
    patch_app_openapi_for_mcp_proxy(app)

    return app


def setup_main_logger_file_handler(app_config: dict[str, Any]) -> logging.Logger:
    main_logger = logging.getLogger(__name__)
    if not main_logger.handlers:
        from ai_editor.logging import (
            create_unified_formatter,
            install_unified_record_factory,
        )

        install_unified_record_factory()
        log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "mcp_server.log"

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(create_unified_formatter())
        main_logger.addHandler(handler)
        main_logger.setLevel(logging.INFO)
    return main_logger
