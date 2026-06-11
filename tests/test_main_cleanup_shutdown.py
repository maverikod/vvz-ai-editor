"""
Tests for daemon shutdown visibility logging.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

from ai_editor.main_cleanup import (
    SHUTDOWN_LOG_TAG,
    _signal_name,
    log_daemon_shutdown,
    register_cleanup_handlers,
)


def test_signal_name_sigterm() -> None:
    assert _signal_name(signal.SIGTERM) == "SIGTERM"


def test_log_daemon_shutdown_writes_tag() -> None:
    logger = MagicMock()
    log_daemon_shutdown(logger, "unit_test", signum=signal.SIGINT)
    assert logger.error.called
    args = logger.error.call_args[0]
    assert args[1] == SHUTDOWN_LOG_TAG
    assert args[2] == "unit_test"


def test_register_cleanup_handlers_logs_registration() -> None:
    logger = MagicMock()
    wm = MagicMock()
    wm.stop_all_workers.return_value = {"total_failed": 0, "message": "ok"}
    register_cleanup_handlers(wm, {}, logger)
    joined = " ".join(str(c) for c in logger.info.call_args_list)
    assert SHUTDOWN_LOG_TAG in joined
    assert "handlers registered" in joined
