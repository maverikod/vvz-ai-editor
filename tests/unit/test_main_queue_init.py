"""Tests for queue manager initialization order before workers."""

from __future__ import annotations

from unittest.mock import patch

from ai_editor.main_queue_init import init_queue_manager_before_workers


def test_init_queue_manager_skipped_when_disabled() -> None:
    with patch(
        "ai_editor.main_queue_init.asyncio.run",
    ) as mock_run:
        init_queue_manager_before_workers({"queue_manager": {"enabled": False}})
    mock_run.assert_not_called()
