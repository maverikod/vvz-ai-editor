"""
Line-window helpers for invalid / plain-text preview (degraded mode).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlainTextViewWindow:
    """One page of plain-text preview."""

    text: str
    total_lines: int
    line_offset: int
    lines_returned: int
    has_more: bool
    next_line_offset: int | None


def _split_source_lines(source: str) -> list[str]:
    if source == "":
        return []
    lines = source.splitlines(keepends=True)
    if lines:
        return lines
    return [source]


def slice_plain_text_view(
    source: str,
    *,
    line_offset: int,
    max_lines: int,
    max_chars: int | None = None,
) -> PlainTextViewWindow:
    """Return at most ``max_lines`` source lines starting at ``line_offset``."""
    if max_lines < 1:
        raise ValueError(f"max_lines must be >= 1, got {max_lines}")
    if line_offset < 0:
        raise ValueError(f"line_offset must be >= 0, got {line_offset}")

    lines = _split_source_lines(source)
    total = len(lines)
    start = min(line_offset, total)
    chunk = lines[start : start + max_lines]
    text = "".join(chunk)
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\u2026"
    end = start + len(chunk)
    has_more = end < total
    return PlainTextViewWindow(
        text=text,
        total_lines=total,
        line_offset=start,
        lines_returned=len(chunk),
        has_more=has_more,
        next_line_offset=end if has_more else None,
    )


def plain_text_pagination_payload(window: PlainTextViewWindow) -> dict[str, int | bool | None]:
    """Top-level pagination fields for invalid-source preview responses."""
    return {
        "preview_total_lines": window.total_lines,
        "preview_line_offset": window.line_offset,
        "preview_lines_returned": window.lines_returned,
        "preview_has_more": window.has_more,
        "preview_next_offset": window.next_line_offset,
    }
