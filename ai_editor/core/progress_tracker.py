"""
Progress tracker for queue jobs.

This module provides a mechanism for commands to update progress
and description when executed via queue.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class _DelegatingProgressTracker:
    """
    Wraps queue-injected trackers that lack set_status (e.g. mcp_proxy_adapter's
    _JobProgressTracker). Delegates set_status to the underlying job when available.
    """

    __slots__ = ("_inner", "_job")

    def __init__(self, inner: Any, job: Any) -> None:
        self._inner = inner
        self._job = job

    def set_progress(self, progress: int) -> None:
        self._inner.set_progress(progress)

    def set_description(self, description: str) -> None:
        self._inner.set_description(description)

    def set_status(self, status: str) -> None:
        if self._job is not None:
            set_status_fn = getattr(self._job, "set_status", None)
            if callable(set_status_fn):
                try:
                    set_status_fn(status)
                except Exception as e:
                    logger.warning(f"Failed to set status: {e}")

    def log(self, message: str) -> None:
        log_fn = getattr(self._inner, "log", None)
        if callable(log_fn):
            log_fn(message)
        else:
            logger.info(message)

    def is_enabled(self) -> bool:
        fn = getattr(self._inner, "is_enabled", None)
        if callable(fn):
            return bool(fn())
        return True


def _wrap_progress_tracker_if_needed(tracker: Optional[Any]) -> Optional[Any]:
    """Ensure set_status exists; wrap mcp_proxy_adapter _JobProgressTracker when needed."""
    if tracker is None:
        return None
    if callable(getattr(tracker, "set_status", None)):
        return tracker
    job = getattr(tracker, "_job", None)
    return _DelegatingProgressTracker(tracker, job)


class ProgressTracker:
    """
    Progress tracker for queue jobs.

    This class provides methods to update job progress, description, and status
    when a command is executed via queue. It is passed through context and
    allows commands to report their progress without direct access to the job object.
    """

    def __init__(
        self,
        set_progress_fn: Optional[Callable[[int], None]] = None,
        set_description_fn: Optional[Callable[[str], None]] = None,
        set_status_fn: Optional[Callable[[str], None]] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize progress tracker.

        Args:
            set_progress_fn: Function to set progress (0-100)
            set_description_fn: Function to set description
            set_status_fn: Function to set status
            log_fn: Function to log messages
        """
        self.set_progress_fn = set_progress_fn
        self.set_description_fn = set_description_fn
        self.set_status_fn = set_status_fn
        self.log_fn = log_fn
        self._enabled = (
            set_progress_fn is not None
            or set_description_fn is not None
            or set_status_fn is not None
        )

    def set_progress(self, progress: int) -> None:
        """
        Set progress percentage (0-100).

        Args:
            progress: Progress percentage (0-100)
        """
        if self.set_progress_fn:
            try:
                # Clamp progress to 0-100 range
                safe_progress = max(0, min(100, int(progress)))
                self.set_progress_fn(safe_progress)
            except Exception as e:
                logger.warning(f"Failed to set progress: {e}")

    def set_description(self, description: str) -> None:
        """
        Set job description.

        Args:
            description: Human-readable description
        """
        if self.set_description_fn:
            try:
                # Limit description length
                safe_description = description[:1024] if description else ""
                self.set_description_fn(safe_description)
            except Exception as e:
                logger.warning(f"Failed to set description: {e}")

    def set_status(self, status: str) -> None:
        """
        Set job status.

        Args:
            status: Job status (pending, running, completed, failed, stopped)
        """
        if self.set_status_fn:
            try:
                self.set_status_fn(status)
            except Exception as e:
                logger.warning(f"Failed to set status: {e}")

    def log(self, message: str) -> None:
        """
        Log a message.

        Args:
            message: Message to log
        """
        if self.log_fn:
            try:
                self.log_fn(message)
            except Exception as e:
                logger.warning(f"Failed to log message: {e}")
        else:
            # Fallback to standard logger
            logger.info(message)

    def is_enabled(self) -> bool:
        """
        Check if progress tracking is enabled.

        Returns:
            True if progress tracking is enabled
        """
        return self._enabled


def get_progress_tracker_from_context(context: dict) -> Optional[Any]:
    """
    Get ProgressTracker (or compatible wrapper) from context.

    Args:
        context: Command context dictionary

    Returns:
        ProgressTracker or a wrapper with set_progress/set_description/set_status,
        or None if not available
    """
    if not context:
        return None
    return _wrap_progress_tracker_if_needed(context.get("progress_tracker"))
