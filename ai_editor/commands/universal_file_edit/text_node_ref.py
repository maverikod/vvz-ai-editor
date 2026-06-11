"""
Resolve text-format ``node_ref`` to 1-based line ranges for universal_file_edit.

Valid sessions on plain text (.txt, .rst, …) use a two-level Paragraph + Line tree.
Invalid sessions and ``.jsonl`` / ``.ndjson`` use flat line indices only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.universal_file_edit.errors import (
    LINE_OUT_OF_RANGE,
    UNKNOWN_NODE_REF,
    error_result_for_edit,
)
from ai_editor.commands.universal_file_edit.insert_position import (
    parse_colon_position,
    resolve_text_insert_side_and_node_ref,
)
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.markdown_line_ranges import (
    resolve_markdown_line_range,
)
from ai_editor.core.cst_tree.models import ROOT_NODE_ID_SENTINEL
from ai_editor.tree.handlers.text_handler import TextHandler

_LINE_INDEX_SUFFIXES = frozenset({".jsonl", ".ndjson"})


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def text_uses_paragraph_line_tree(
    draft_path: Path, *, session_is_invalid: bool
) -> bool:
    """True when node_ref is a preview short_id on a Paragraph/Line tree."""
    if session_is_invalid:
        return False
    suffix = draft_path.suffix.lower()
    if draft_path.name.endswith(".md.draft"):
        return False
    if suffix in _LINE_INDEX_SUFFIXES:
        return False
    if suffix == ".md":
        return False
    return suffix in (".txt", ".rst", ".text", ".log", ".adoc", "")


def _resolve_paragraph_line_block(source: str, short_id: int) -> Tuple[int, int]:
    """Map preview short_id to 1-based source line range (paragraph + line children)."""
    nodes = TextHandler().parse_content(Path("dummy.txt"), source)
    target_idx: Optional[int] = None
    for idx, node in enumerate(nodes):
        if int(node.short_id) == short_id:
            target_idx = idx
            break
    if target_idx is None:
        raise ValueError(f"Unknown short_id: {short_id}")
    target = nodes[target_idx]
    start_line = int(target.attributes.get("line_no", target_idx + 1))
    end_line = start_line
    if target.kind == "paragraph":
        j = target_idx + 1
        while j < len(nodes) and nodes[j].kind == "line":
            end_line = int(nodes[j].attributes.get("line_no", end_line))
            j += 1
    return start_line, end_line


def _resolve_flat_line_index(source: str, node_ref: str) -> Tuple[int, int]:
    """Map zero-based line index node_ref to 1-based inclusive line range."""
    idx = int(node_ref)
    lines = source.splitlines()
    if idx < 0 or idx >= len(lines):
        raise ValueError(f"Line index {idx} out of range [0, {len(lines)}).")
    start_line = idx + 1
    return start_line, start_line


def resolve_text_block_line_range(
    draft_path: Path,
    node_ref: str,
    *,
    session_is_invalid: bool,
) -> Union[Tuple[int, int], ErrorResult]:
    """Resolve node_ref to a 1-based inclusive line range for delete/replace/move source."""
    source = _read_source(draft_path)
    suffix = draft_path.suffix.lower()
    if suffix == ".md" or draft_path.name.endswith(".md.draft"):
        bounds = resolve_markdown_line_range(
            source,
            node_ref,
            file_path=str(draft_path.resolve()),
        )
        if isinstance(bounds, PreviewError):
            return error_result_for_edit(
                bounds.message,
                UNKNOWN_NODE_REF,
                bounds.details,
            )
        return bounds

    try:
        if text_uses_paragraph_line_tree(
            draft_path, session_is_invalid=session_is_invalid
        ):
            return _resolve_paragraph_line_block(source, int(str(node_ref).strip()))
        return _resolve_flat_line_index(source, str(node_ref))
    except ValueError as exc:
        msg = str(exc)
        if "Unknown short_id" in msg:
            return error_result_for_edit(
                msg,
                UNKNOWN_NODE_REF,
                {"node_ref": node_ref},
            )
        if "Line index" in msg and "out of range" in msg:
            return error_result_for_edit(
                msg,
                LINE_OUT_OF_RANGE,
                {"node_ref": node_ref, "total_lines": len(source.splitlines())},
            )
        return error_result_for_edit(
            f"node_ref {node_ref!r} is not a valid integer reference.",
            UNKNOWN_NODE_REF,
            {"node_ref": node_ref},
        )


def _coalesce_text_insert_node_ref(op: Dict[str, Any]) -> None:
    """Map sidecar-style insert anchor fields onto ``node_ref`` for line resolution."""
    op_type = str(op.get("type") or op.get("action") or "replace").lower()
    if op_type != "insert":
        return
    if op.get("node_ref") not in (None, ""):
        return
    for key, position in (
        ("target_node_id", None),
        ("target_node_ref", None),
        ("before_node_id", "before"),
        ("after_node_id", "after"),
    ):
        raw = op.get(key)
        if raw not in (None, ""):
            op["node_ref"] = raw
            if position is not None and op.get("position") in (None, "after"):
                op["position"] = position
            return
    parsed = parse_colon_position(op.get("position"))
    if parsed is not None:
        side, addr = parsed
        op["node_ref"] = addr
        op["position"] = side


def _coalesce_text_move_node_refs(op: Dict[str, Any]) -> None:
    """Normalize move source/target anchor fields for line-based resolution."""
    if str(op.get("type") or op.get("action") or "").lower() != "move":
        return
    if op.get("node_ref") in (None, ""):
        raw = op.get("node_id")
        if raw not in (None, ""):
            op["node_ref"] = raw
    if op.get("target_node_ref") in (None, "") and op.get("target_node_id") not in (
        None,
        "",
    ):
        op["target_node_ref"] = op.get("target_node_id")
    parsed = parse_colon_position(op.get("position"))
    if parsed is not None:
        side, addr = parsed
        op["target_node_ref"] = addr
        op["position"] = side


def _map_move_position_to_insert_side(position: str) -> str:
    pos = str(position or "after").lower()
    if pos in ("before", "first", "first_child"):
        return "before"
    if pos in ("after", "last", "last_child"):
        return "after"
    raise ValueError(f"unsupported move position for text insert: {position!r}")


def resolve_text_insert_line(
    draft_path: Path,
    move_op: Dict[str, Any],
    *,
    session_is_invalid: bool,
) -> Union[int, ErrorResult]:
    """Resolve move target anchor to 1-based insert line (before/after block)."""
    target = move_op.get("target_node_ref") or move_op.get("target_node_id")
    parent = move_op.get("parent_node_id") or move_op.get("parent_node_ref")
    position = str(move_op.get("position") or "after")

    if target not in (None, ""):
        side = _map_move_position_to_insert_side(position)
        bounds = resolve_text_block_line_range(
            draft_path,
            str(target),
            session_is_invalid=session_is_invalid,
        )
        if isinstance(bounds, ErrorResult):
            return bounds
        start_line, end_line = bounds
        return start_line if side == "before" else end_line + 1

    if parent not in (None, "", ROOT_NODE_ID_SENTINEL):
        bounds = resolve_text_block_line_range(
            draft_path,
            str(parent),
            session_is_invalid=session_is_invalid,
        )
        if isinstance(bounds, ErrorResult):
            return bounds
        start_line, end_line = bounds
        pos = str(position or "last").lower()
        if pos in ("first", "first_child", "before"):
            return start_line
        return end_line + 1

    source = _read_source(draft_path)
    line_count = len(source.splitlines())
    pos = str(position or "last").lower()
    if pos in ("first", "first_child", "before"):
        return 1
    return line_count + 1


def resolve_text_operation_line_range(
    draft_path: Path,
    op: Dict[str, Any],
    *,
    session_is_invalid: bool = False,
) -> Optional[ErrorResult]:
    """When ``node_ref`` is set, fill ``start_line``/``end_line`` on ``op`` in place."""
    _coalesce_text_insert_node_ref(op)
    _coalesce_text_move_node_refs(op)
    op_type = op.get("type", "replace")
    node_ref = op.get("node_ref")

    if op_type == "insert":
        try:
            side, embedded_ref = resolve_text_insert_side_and_node_ref(op)
        except ValueError as exc:
            return error_result_for_edit(
                str(exc),
                LINE_OUT_OF_RANGE,
                {"position": op.get("position")},
            )
        if side == "last":
            return None
        if embedded_ref not in (None, ""):
            node_ref = embedded_ref
            op["node_ref"] = embedded_ref
        insert_side = side
    else:
        insert_side = None

    if node_ref in (None, ""):
        return None

    bounds = resolve_text_block_line_range(
        draft_path,
        str(node_ref),
        session_is_invalid=session_is_invalid,
    )
    if isinstance(bounds, ErrorResult):
        return bounds
    start_line, end_line = bounds

    if op_type == "insert":
        assert insert_side in ("before", "after")
        if insert_side == "before":
            op["start_line"] = start_line
        else:
            op["start_line"] = end_line + 1
        op.pop("end_line", None)
        op.pop("position", None)
    else:
        op["start_line"] = start_line
        op["end_line"] = end_line
    return None
