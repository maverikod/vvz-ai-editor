"""EditSession facade — re-exports implementation (C-019).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .edit_session_impl import (
    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,
    EditSession,
    EditSessionError,
    SESSION_INVALID_TRUTH_INVARIANT,
    SESSION_VALID_TRUTH_INVARIANT,
    SessionTreeValidity,
    _active_sessions,
)

__all__ = [
    "EditSession",
    "EditSessionError",
    "SessionTreeValidity",
    "get_active_session",
    "CONTENT_NOT_ALLOWED_FOR_VALID_FILE",
    "SESSION_VALID_TRUTH_INVARIANT",
    "SESSION_INVALID_TRUTH_INVARIANT",
]


def get_active_session(session_id: str) -> EditSession:
    """Resolve live EditSession; KeyError if absent."""
    try:
        return _active_sessions[session_id]
    except KeyError as exc:
        raise KeyError(f"No active edit session: {session_id}") from exc
