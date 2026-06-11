"""
Unified ``position`` syntax for sibling-relative insert (tree-temp and text).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

# (side, address) when position is ``before:<addr>`` or ``after:<addr>``
ColonPosition = Tuple[str, str]


def parse_colon_position(position: Any) -> Optional[ColonPosition]:
    """Parse ``before:<address>`` / ``after:<address>``; return None if not colon form."""
    if not isinstance(position, str):
        return None
    stripped = position.strip()
    if stripped.startswith("before:"):
        addr = stripped[7:].strip()
        if not addr:
            raise ValueError("position before:<address> requires a non-empty address")
        return "before", addr
    if stripped.startswith("after:"):
        addr = stripped[6:].strip()
        if not addr:
            raise ValueError("position after:<address> requires a non-empty address")
        return "after", addr
    return None


def _is_uuid_v4_string(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


def _legacy_anchor_fields_present(mop: Dict[str, Any]) -> bool:
    return any(
        mop.get(k) is not None
        for k in (
            "before_node_id",
            "after_node_id",
            "before_key",
            "after_key",
            "before_json_pointer",
            "after_json_pointer",
        )
    )


def coalesce_tree_temp_insert_position(mop: Dict[str, Any]) -> None:
    """Map ``position`` ``before:<addr>`` / ``after:<addr>`` to legacy anchor fields."""
    parsed = parse_colon_position(mop.get("position"))
    if parsed is None:
        return
    side, addr = parsed
    if _legacy_anchor_fields_present(mop):
        raise ValueError(
            "position 'before:<address>' / 'after:<address>' is mutually exclusive "
            "with before_node_id, after_node_id, before_key, after_key, "
            "before_json_pointer, and after_json_pointer"
        )
    if addr.startswith("/"):
        key = "before_json_pointer" if side == "before" else "after_json_pointer"
        mop[key] = addr
    elif _is_uuid_v4_string(addr):
        key = "before_node_id" if side == "before" else "after_node_id"
        mop[key] = addr
    else:
        key = "before_key" if side == "before" else "after_key"
        mop[key] = addr
    mop.pop("position", None)


def resolve_text_insert_side_and_node_ref(
    op: Dict[str, Any],
) -> Tuple[str, Optional[str]]:
    """Return (insert_side, node_ref) for text insert: side in before|after|last."""
    position = op.get("position", "after")
    parsed = parse_colon_position(position)
    if parsed is not None:
        side, addr = parsed
        explicit = op.get("node_ref")
        if explicit not in (None, "") and str(explicit) != addr:
            raise ValueError(
                f"position {position!r} address {addr!r} conflicts with "
                f"node_ref {explicit!r}"
            )
        return side, addr
    if position in (None, "after"):
        return "after", (
            op.get("node_ref") if op.get("node_ref") not in ("", None) else None
        )
    if position == "before":
        return "before", (
            op.get("node_ref") if op.get("node_ref") not in ("", None) else None
        )
    if position == "last":
        return "last", None
    raise ValueError(
        f"insert position must be 'before', 'after', 'last', or "
        f"'before:<node_ref>' / 'after:<node_ref>', got {position!r}"
    )
