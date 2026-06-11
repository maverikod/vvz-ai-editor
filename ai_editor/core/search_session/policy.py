"""
Session TTL policy and maximum block size configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SEARCH_SESSION_TTL_SECONDS_DEFAULT = 1800
SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT = 4_096

TTL_SECONDS_MIN = 60
TTL_SECONDS_MAX = 604_800
MAX_BLOCK_SIZE_BYTES_MIN = 1024
MAX_BLOCK_SIZE_BYTES_MAX = 16_777_216


@dataclass(frozen=True)
class SessionTTLPolicy:
    """Validated search session TTL and result block size limits."""

    ttl_seconds: int
    max_block_size_bytes: int


def load_session_ttl_policy(config_data: dict[str, Any]) -> SessionTTLPolicy:
    """Load policy from ``ai_editor.search_session`` with code defaults."""
    ai_editor = config_data.get("ai_editor") or {}
    search_session = ai_editor.get("search_session") or {}
    ttl_raw = search_session.get("ttl_seconds", SEARCH_SESSION_TTL_SECONDS_DEFAULT)
    block_raw = search_session.get(
        "max_block_size_bytes",
        SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    )
    return SessionTTLPolicy(
        ttl_seconds=int(ttl_raw),
        max_block_size_bytes=int(block_raw),
    )


def validate_session_ttl_policy(policy: SessionTTLPolicy) -> None:
    """Raise ValueError when TTL or block size is invalid or out of range."""
    _validate_positive_int(
        policy.ttl_seconds,
        name="ttl_seconds",
        minimum=TTL_SECONDS_MIN,
        maximum=TTL_SECONDS_MAX,
    )
    _validate_positive_int(
        policy.max_block_size_bytes,
        name="max_block_size_bytes",
        minimum=MAX_BLOCK_SIZE_BYTES_MIN,
        maximum=MAX_BLOCK_SIZE_BYTES_MAX,
    )


def _validate_positive_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be int, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {value}")
