"""
Register FastAPI startup/shutdown events.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from ai_editor.core.cst_tree.tree_builder import start_cst_tree_ttl_cleanup


def register_startup_shutdown_events(
    app: Any,
    app_config: dict[str, Any],
) -> None:
    """Register startup/shutdown hooks for editing server."""

    @app.on_event("startup")
    async def start_on_startup() -> None:
        logger = logging.getLogger(__name__)
        print(
            "🚀 [STARTUP EVENT] AI Editor startup (file-editing mode, no local DB)...",
            flush=True,
        )
        logger.info("AI Editor startup: file-editing mode (no local database)")
        try:
            start_cst_tree_ttl_cleanup()
            print("✅ [STARTUP EVENT] Startup completed", flush=True)
        except Exception as e:
            print(
                f"❌ [STARTUP EVENT] Failed during startup: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error("Startup failed: %s", e, exc_info=True)
            raise

    @app.on_event("shutdown")
    async def stop_on_shutdown() -> None:
        logger = logging.getLogger(__name__)
        print("🛑 [SHUTDOWN EVENT] AI Editor shutdown", flush=True)
        logger.info("AI Editor shutdown complete")
