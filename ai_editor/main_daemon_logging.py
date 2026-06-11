"""
Daemon-mode logging setup (file handler, excepthook, heartbeat).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path
from typing import Any, Optional

import threading


def setup_daemon_logging(
    args: Any,
    full_config: dict[str, Any],
    config_path: Path,
) -> Optional[threading.Event]:
    """
    Set up file logging, excepthook, and heartbeat when running as daemon.
    Returns heartbeat_stop Event if daemon mode, else None.
    """
    if not getattr(args, "daemon", False):
        return None

    heartbeat_stop = None
    try:
        log_dir = Path(full_config.get("server", {}).get("log_dir", "./logs"))
        if not log_dir.is_absolute():
            log_dir = (config_path.resolve().parent / log_dir).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        daemon_log_file = log_dir / "mcp_server.log"
        root_logger = logging.getLogger()
        if not any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", "") == str(daemon_log_file)
            for h in root_logger.handlers
        ):
            from ai_editor.logging import (
                create_unified_formatter,
                install_unified_record_factory,
            )

            install_unified_record_factory()
            file_handler = logging.FileHandler(daemon_log_file, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(create_unified_formatter())
            root_logger.addHandler(file_handler)
            root_logger.setLevel(logging.INFO)

        def _daemon_thread_excepthook(args_obj: object) -> None:
            root_logger.error(
                "Uncaught exception in thread %s: %s",
                getattr(getattr(args_obj, "thread", None), "name", None)
                or getattr(getattr(args_obj, "thread", None), "ident", None),
                getattr(args_obj, "exc_value", None),
                exc_info=(
                    getattr(args_obj, "exc_type", None),
                    getattr(args_obj, "exc_value", None),
                    getattr(args_obj, "exc_traceback", None),
                ),
            )

        threading.excepthook = _daemon_thread_excepthook

        try:
            import faulthandler

            faulthandler.enable()
        except Exception:
            pass

        _original_excepthook = sys.excepthook

        def _daemon_excepthook(
            exc_type: type[BaseException],
            exc_value: BaseException,
            exc_tb: types.TracebackType | None,
        ) -> None:
            root_logger.error(
                "Uncaught exception in main thread (process will exit): %s",
                exc_value,
                exc_info=(exc_type, exc_value, exc_tb),
            )
            _original_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = _daemon_excepthook

        heartbeat_stop = threading.Event()

        def _heartbeat_worker() -> None:
            log = logging.getLogger(__name__)
            while not heartbeat_stop.wait(timeout=60.0):
                log.info("Main process heartbeat (pid=%s)", os.getpid())

        _hb_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
        _hb_thread.start()

        root_logger.info(
            "Daemon main() entered, pid=%s (logging to %s)",
            os.getpid(),
            daemon_log_file,
        )
    except Exception:
        pass

    return heartbeat_stop
