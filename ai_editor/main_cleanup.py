"""
Register atexit and signal handlers for worker cleanup on exit.

Logs every shutdown path with a stable ``[DAEMON_SHUTDOWN]`` tag so daemon
death is visible in ``mcp_server.log`` (signal, atexit, normal server loop end).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
import threading
from typing import Any, Optional

from ai_editor.core.constants import DEFAULT_SHUTDOWN_GRACE_TIMEOUT

SHUTDOWN_LOG_TAG = "[DAEMON_SHUTDOWN]"


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except (ValueError, AttributeError):
        return f"signal_{signum}"


def _flush_log_handlers() -> None:
    try:
        for handler in logging.root.handlers[:]:
            try:
                handler.flush()
            except Exception:
                pass
        logging.shutdown()
    except Exception:
        pass


def log_daemon_shutdown(
    logger: Any,
    reason: str,
    *,
    signum: Optional[int] = None,
    exc_info: bool = False,
) -> None:
    """Write a highly visible shutdown line (ERROR) and flush logging."""
    sig_part = ""
    if signum is not None:
        sig_part = f" signum={signum} ({_signal_name(signum)})"
    logger.error(
        "%s reason=%s pid=%s ppid=%s%s",
        SHUTDOWN_LOG_TAG,
        reason,
        os.getpid(),
        os.getppid(),
        sig_part,
        exc_info=exc_info,
    )
    _flush_log_handlers()


def register_cleanup_handlers(
    worker_manager: Any,
    app_config: dict[str, Any],
    main_logger: Any,
    *,
    heartbeat_stop: Optional[threading.Event] = None,
) -> None:
    """Register cleanup_workers on atexit and SIGTERM/SIGINT/SIGHUP."""
    cleanup_lock = threading.Lock()
    cleanup_started = False
    shutdown_logged = False

    def _stop_heartbeat() -> None:
        if heartbeat_stop is not None:
            heartbeat_stop.set()

    def _log_shutdown_once(reason: str, *, signum: Optional[int] = None) -> None:
        nonlocal shutdown_logged
        with cleanup_lock:
            if shutdown_logged:
                return
            shutdown_logged = True
        _stop_heartbeat()
        log_daemon_shutdown(main_logger, reason, signum=signum)

    def cleanup_workers() -> None:
        nonlocal cleanup_started
        with cleanup_lock:
            if cleanup_started:
                main_logger.info(
                    "cleanup_workers() already executed for this shutdown; "
                    "skipping duplicate invocation"
                )
                return
            cleanup_started = True
        try:
            main_logger.info(
                "cleanup_workers() invoked (shutdown path); stopping workers"
            )
            main_logger.info("🛑 Server shutdown: stopping all workers")
            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT

            if worker_manager is not None:
                shutdown_result = worker_manager.stop_all_workers(timeout=shutdown_timeout)
                if shutdown_result.get("total_failed", 0) > 0:
                    main_logger.warning(
                        "⚠️  Some workers failed to stop: %s",
                        shutdown_result.get("message"),
                    )
                else:
                    main_logger.info(
                        "✅ All workers stopped: %s",
                        shutdown_result.get("message"),
                    )
            else:
                main_logger.info("No worker manager configured; skip worker shutdown")
        except Exception as e:
            main_logger.error(
                "❌ Error stopping workers: %s",
                e,
                exc_info=True,
            )
        finally:
            _flush_log_handlers()

    def _shutdown(reason: str, *, signum: Optional[int] = None) -> None:
        _log_shutdown_once(reason, signum=signum)
        cleanup_workers()

    def _atexit_handler() -> None:
        _shutdown("atexit")

    def signal_handler(signum: int, frame: object) -> None:
        del frame
        _shutdown("signal", signum=signum)
        main_logger.info("Signal handler: calling sys.exit(0) after cleanup")
        sys.exit(0)

    atexit.register(_atexit_handler)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, signal_handler)
        except (OSError, ValueError) as e:
            main_logger.warning(
                "Could not register handler for %s: %s",
                _signal_name(sig),
                e,
            )

    main_logger.info(
        "%s handlers registered (SIGTERM, SIGINT, SIGHUP, atexit); pid=%s",
        SHUTDOWN_LOG_TAG,
        os.getpid(),
    )
