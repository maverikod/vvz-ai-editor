"""
Post-render character pagination for universal_file_preview responses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from typing import Any


def serialize_preview_envelope(envelope: dict[str, Any]) -> str:
    """Canonical JSON text used for character-offset pagination."""
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def apply_preview_pagination(
    envelope: dict[str, Any],
    *,
    offset: int,
    max_chars: int,
) -> dict[str, Any]:
    """
    Paginate a rendered preview envelope by character offset.

    When the full serialized envelope fits within ``max_chars`` and ``offset`` is
    zero, the structured envelope is returned unchanged with pagination metadata.
    Otherwise a ``preview_chunk`` substring is returned for the client to stitch.
    """
    if max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")

    serialized = serialize_preview_envelope(envelope)
    total = len(serialized)
    start = min(offset, total)
    end = min(start + max_chars, total)
    chunk = serialized[start:end]
    has_more = end < total
    next_offset: int | None = end if has_more else None

    pagination = {
        "preview_total_chars": total,
        "preview_has_more": has_more,
        "preview_next_offset": next_offset,
    }

    if offset == 0 and total <= max_chars:
        return {**envelope, **pagination}

    result: dict[str, Any] = {**pagination, "preview_chunk": chunk}
    if envelope.get("focus") is not None:
        result["focus"] = envelope["focus"]
    if envelope.get("total_blocks") is not None:
        result["total_blocks"] = envelope["total_blocks"]
    if envelope.get("tree_id") is not None:
        result["tree_id"] = envelope["tree_id"]
    return result
