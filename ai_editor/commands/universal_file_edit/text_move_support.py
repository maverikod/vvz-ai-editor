"""
Expand text-format move operations into delete + insert (buffer then place).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.universal_file_edit.errors import (
    INVALID_OPERATION,
    error_result_for_edit,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.text_node_ref import (
    _coalesce_text_move_node_refs,
    resolve_text_block_line_range,
    resolve_text_insert_line,
)
from ai_editor.core.edit_session.edit_operations_adapter import (
    _coalesce_node_ref_keys,
    _normalize_action,
)


def expand_text_move_operations(
    session: EditSession,
    buffer: List[str],
    operations: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Optional[ErrorResult]]:
    """Replace each ``move`` op with delete then insert using buffered content."""
    expanded: List[Dict[str, Any]] = []
    for op in operations:
        action = _normalize_action(_coalesce_node_ref_keys(dict(op)))
        if action != "move":
            expanded.append(op)
            continue
        move_op = dict(op)
        _coalesce_text_move_node_refs(move_op)
        m = _coalesce_node_ref_keys(move_op)
        source_ref = m.get("node_id") or m.get("node_ref")
        if source_ref in (None, ""):
            return operations, error_result_for_edit(
                "move requires node_id or node_ref for the source block.",
                INVALID_OPERATION,
                {"operation": op},
            )
        bounds = resolve_text_block_line_range(
            session.draft_path,
            str(source_ref),
            session_is_invalid=session.is_invalid,
        )
        if isinstance(bounds, ErrorResult):
            return operations, bounds
        start_line, end_line = bounds
        if start_line < 1 or end_line < start_line or end_line > len(buffer):
            return operations, error_result_for_edit(
                f"move source lines {start_line}-{end_line} out of draft range",
                INVALID_OPERATION,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": len(buffer),
                },
            )
        payload_lines = buffer[start_line - 1 : end_line]
        payload = "".join(payload_lines)

        insert_line = resolve_text_insert_line(
            session.draft_path,
            m,
            session_is_invalid=session.is_invalid,
        )
        if isinstance(insert_line, ErrorResult):
            return operations, insert_line

        delete_op: Dict[str, Any] = {
            "type": "delete",
            "action": "delete",
            "start_line": start_line,
            "end_line": end_line,
        }
        insert_op: Dict[str, Any] = {
            "type": "insert",
            "action": "insert",
            "start_line": insert_line,
            "content": payload,
        }
        expanded.extend([delete_op, insert_op])
    return expanded, None
