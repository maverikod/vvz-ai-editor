"""
Uniform EditOperation dispatch layer (C-015).

Resolves FormatHandler via HandlerRegistry, enforces tree-validity edit gate,
validates integer short_id arguments, dispatches to handler op_* methods.
External addressing is short_id int only ({n003}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from ai_editor.tree.contracts import NodeId, validate_short_id
from ai_editor.tree.format_handler import FormatHandler
from ai_editor.tree.handler_registry import HandlerRegistry

VALID_POSITIONS = ("before", "after", "first_child", "last_child")


class EditOperationKind(str, Enum):
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"
    MOVE = "move"
    EDIT_ATTRIBUTES = "edit_attributes"
    EDIT_CONTENT = "edit_content"


class EditOperationError(ValueError):
    """Input errors: invalid gate, unknown kind, missing args, invalid position, invalid short_id int."""


@dataclass
class EditOperation:
    kind: EditOperationKind
    short_id: Optional[NodeId] = None
    anchor_short_id: Optional[NodeId] = None
    position: Optional[str] = None
    new_content: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    next_free: Optional[int] = None


def _require(value: Any, name: str, kind: EditOperationKind) -> Any:
    if value is None:
        raise EditOperationError(f"{name} is required for {kind.value}")
    return value


def _check_position(position: Optional[str], kind: EditOperationKind) -> str:
    pos = _require(position, "position", kind)
    assert isinstance(pos, str)
    if pos not in VALID_POSITIONS:
        raise EditOperationError(
            f"position must be one of {VALID_POSITIONS!r}, got {pos!r}"
        )
    return pos


def _normalize_short_id(value: int, name: str) -> NodeId:
    try:
        return validate_short_id(value)
    except ValueError:
        raise EditOperationError(
            f"{name} must be positive int short_id, got {value!r}"
        ) from None


def apply_edit_operation(
    *,
    registry: HandlerRegistry,
    source_path: Path,
    marked_text: str,
    operation: EditOperation,
    tree_is_valid: bool,
    next_free: Optional[int] = None,
) -> tuple[str, int]:
    """Dispatch a uniform EditOperation to the resolved FormatHandler.

    Returns:
        Tuple of (new_marked_text, updated_next_free).
    """
    if not tree_is_valid:
        raise EditOperationError(
            "tree is invalid (text mode); short_id edit operations forbidden until re-validation"
        )

    handler: FormatHandler = registry.resolve(source_path)
    if hasattr(handler, "set_tree_validity"):
        handler.set_tree_validity(True)

    kind = operation.kind

    if kind is EditOperationKind.INSERT:
        anchor = _normalize_short_id(
            _require(operation.anchor_short_id, "anchor_short_id", kind),
            "anchor_short_id",
        )
        nf = _require(
            operation.next_free if operation.next_free is not None else next_free,
            "next_free",
            kind,
        )
        if nf < 1:
            raise EditOperationError("next_free must be >= 1")
        pos = _check_position(operation.position, kind)
        content = _require(operation.new_content, "new_content", kind)
        result = handler.op_insert(marked_text, anchor, pos, content, nf)
        return result, nf + 1

    if kind is EditOperationKind.DELETE:
        sid = _normalize_short_id(
            _require(operation.short_id, "short_id", kind),
            "short_id",
        )
        result = handler.op_delete(marked_text, sid)
        updated_nf = next_free if next_free is not None else (operation.next_free or 1)
        return result, updated_nf

    if kind is EditOperationKind.REPLACE:
        sid = _normalize_short_id(
            _require(operation.short_id, "short_id", kind),
            "short_id",
        )
        content = _require(operation.new_content, "new_content", kind)
        result = handler.op_replace(marked_text, sid, content)
        updated_nf = next_free if next_free is not None else (operation.next_free or 1)
        return result, updated_nf

    if kind is EditOperationKind.MOVE:
        sid = _normalize_short_id(
            _require(operation.short_id, "short_id", kind),
            "short_id",
        )
        anchor = _normalize_short_id(
            _require(operation.anchor_short_id, "anchor_short_id", kind),
            "anchor_short_id",
        )
        pos = _check_position(operation.position, kind)
        nf_raw = operation.next_free if operation.next_free is not None else next_free
        if nf_raw is None:
            nf_raw = handler.peak_short_id_in_marked(marked_text) + 1
        if nf_raw < 1:
            raise EditOperationError("next_free must be >= 1")
        result = handler.op_move_via_delete_insert(
            marked_text,
            sid,
            anchor,
            pos,
            nf_raw,
        )
        return result, nf_raw + 1

    if kind is EditOperationKind.EDIT_ATTRIBUTES:
        sid = _normalize_short_id(
            _require(operation.short_id, "short_id", kind),
            "short_id",
        )
        result = handler.op_edit_attributes(marked_text, sid, operation.attributes)
        updated_nf = next_free if next_free is not None else (operation.next_free or 1)
        return result, updated_nf

    if kind is EditOperationKind.EDIT_CONTENT:
        sid = _normalize_short_id(
            _require(operation.short_id, "short_id", kind),
            "short_id",
        )
        content = _require(operation.new_content, "new_content", kind)
        result = handler.op_edit_content(marked_text, sid, content)
        updated_nf = next_free if next_free is not None else (operation.next_free or 1)
        return result, updated_nf

    raise EditOperationError(f"unknown edit operation kind: {kind!r}")
