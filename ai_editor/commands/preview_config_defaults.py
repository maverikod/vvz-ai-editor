"""
Server-config defaults for preview and grep commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .base_mcp_command import BaseMCPCommand

DEFAULT_PREVIEW_MAX_CHARS = 32_000
DEFAULT_PREVIEW_VALUE_PREVIEW_LEN = 120
DEFAULT_GREP_LINE_PREVIEW_LEN = 120
DEFAULT_PREVIEW_LINES = 20
DEFAULT_FULL_TEXT_MAX_LINES = 200


def get_preview_config_defaults() -> dict[str, Any]:
    """Load preview/grep default caps from active server config."""
    raw = BaseMCPCommand._get_raw_config()
    full_text = raw.get("preview_full_text_max_lines")
    if full_text is None:
        full_text_default: int | None = DEFAULT_FULL_TEXT_MAX_LINES
    else:
        full_text_default = int(full_text)

    return {
        "preview_max_chars_default": int(
            raw.get("preview_max_chars_default", DEFAULT_PREVIEW_MAX_CHARS)
        ),
        "preview_value_preview_len_default": int(
            raw.get(
                "preview_value_preview_len_default",
                DEFAULT_PREVIEW_VALUE_PREVIEW_LEN,
            )
        ),
        "grep_line_preview_len_default": int(
            raw.get("grep_line_preview_len_default", DEFAULT_GREP_LINE_PREVIEW_LEN)
        ),
        "preview_lines_default": int(
            raw.get("preview_lines_default", DEFAULT_PREVIEW_LINES)
        ),
        "preview_full_text_max_lines_default": full_text_default,
    }
