"""
Central timeouts for search commands (inline attempt vs hard queued cap).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

SEARCH_INLINE_TIMEOUT_SECONDS = 3.0
SEARCH_HARD_TIMEOUT_SECONDS = 120.0

SEARCH_INLINE_TIMEOUT_MIN = 0.1
SEARCH_INLINE_TIMEOUT_MAX = 30.0

AUTO_QUEUE_REASON = "SEARCH_INLINE_TIMEOUT"
EXECUTION_MODE_QUEUED = "queued"
INTERNAL_EXECUTION_MODE_KEY = "_execution_mode"


def resolve_inline_timeout_seconds(explicit: Optional[float]) -> float:
    """Clamp client override; default is SEARCH_INLINE_TIMEOUT_SECONDS."""
    if explicit is None:
        return SEARCH_INLINE_TIMEOUT_SECONDS
    return max(
        SEARCH_INLINE_TIMEOUT_MIN,
        min(SEARCH_INLINE_TIMEOUT_MAX, float(explicit)),
    )
