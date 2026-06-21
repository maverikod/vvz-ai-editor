"""
Helpers for previewing syntactically invalid source files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from typing import Any

from .models import Node, NodeKind
from .plain_text_preview_window import (
    plain_text_pagination_payload,
    slice_plain_text_view,
)


def invalid_preview_line_params(
    budget: object | None,
) -> dict[str, int | None]:
    """Resolve line-window caps for degraded plain-text preview."""
    if budget is None:
        return {"line_offset": 0, "max_lines": 20, "max_chars": None}
    return {
        "line_offset": int(getattr(budget, "preview_offset", 0) or 0),
        "max_lines": int(getattr(budget, "preview_lines", 20) or 20),
        "max_chars": int(getattr(budget, "max_chars", 0) or 0) or None,
    }


def invalid_source_node(
    file_path: str,
    exc: BaseException,
    *,
    line_offset: int = 0,
    max_lines: int = 20,
    max_chars: int | None = None,
) -> Node:
    """Build a scalar root node with a line-windowed plain-text view."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    window = slice_plain_text_view(
        source,
        line_offset=line_offset,
        max_lines=max_lines,
        max_chars=max_chars,
    )
    attrs: dict[str, object] = {
        "text": window.text,
        "parse_error": str(exc),
        "full_text": not window.has_more and window.line_offset == 0,
        **plain_text_pagination_payload(window),
    }
    return Node(
        node_kind=NodeKind.SCALAR,
        node_ref="",
        is_invalid=True,
        attributes=attrs,
    )


_PLAIN_TEXT_PAGINATION_KEYS = (
    "preview_total_lines",
    "preview_line_offset",
    "preview_lines_returned",
    "preview_has_more",
    "preview_next_offset",
)


def apply_invalid_line_pagination(
    envelope: dict[str, Any],
    focus_attrs: dict[str, object],
) -> dict[str, Any]:
    """Merge line-window pagination from invalid-source focus into the envelope."""
    result = dict(envelope)
    for key in _PLAIN_TEXT_PAGINATION_KEYS:
        if key in focus_attrs:
            result[key] = focus_attrs[key]
    focus = envelope.get("focus") or {}
    focus_text = focus.get("text") if isinstance(focus.get("text"), str) else ""
    result["preview_total_chars"] = len(focus_text)
    return result
