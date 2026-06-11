"""
Plain-text universal edit pipeline (FORMAT_TEXT draft replacement).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.anchor_check import AnchorMismatch, check_text_anchor
from ai_editor.commands.universal_file_edit.edit_draft_path_utils import (
    project_root_near,
)
from ai_editor.commands.universal_file_edit.errors import (
    ANCHOR_MISMATCH,
    INVALID_OPERATION,
    LINE_OUT_OF_RANGE,
    UNKNOWN_NODE_REF,
    WRITE_FAILED,
    error_result_for_edit,
)
from ai_editor.commands.universal_file_replace_command import (
    TextReplacementTriple,
    _sort_text_replacements_bottom_up,
)
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    apply_source_mutation,
    apply_tree_operation,
)
from ai_editor.commands.universal_file_edit.text_move_support import (
    expand_text_move_operations,
)
from ai_editor.commands.universal_file_edit.text_node_ref import (
    resolve_text_operation_line_range,
)
from ai_editor.core.edit_session.edit_operations_adapter import (
    _coalesce_node_ref_keys,
    _operation_uses_node_address,
    command_op_to_edit_operation,
    expand_markdown_section_ops,
    session_has_map_tree,
    session_has_valid_tree,
    sidecar_ops_use_unified_tree,
    text_ops_use_unified_tree,
)
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.edit_operations import EditOperationError


def _line_count(buffer: List[str]) -> int:
    return len(buffer)


def _resolve_line_range(op: Dict[str, Any]) -> tuple[int, int]:
    start_line = int(op.get("start_line", 1))
    end_raw = op.get("end_line")
    end_line = start_line if end_raw is None else int(end_raw)
    return start_line, end_line


def _validate_text_line_operation(
    buffer: List[str],
    op: Dict[str, Any],
) -> Optional[ErrorResult]:
    """Validate one text edit operation against the current draft buffer."""
    if op.get("position") == "last":
        return None

    op_type = op.get("type", "replace")
    if op_type != "insert" and "start_line" not in op:
        return error_result_for_edit(
            "text edit operation has no resolvable target: "
            "no node_ref produced a line range and no explicit start_line "
            "was given.",
            INVALID_OPERATION,
            {
                "op_type": op_type,
                "received_keys": sorted(op.keys()),
                "hint": (
                    "For .md/text files use node_ref (zero-based block index "
                    "or markdown slug from universal_file_preview) plus "
                    "content, or explicit start_line/end_line. Do not use the "
                    "Python sidecar form (node_id + code_lines) on text files."
                ),
            },
        )
    start_line, end_line = _resolve_line_range(op)
    line_count = _line_count(buffer)

    if start_line < 1:
        return error_result_for_edit(
            f"start_line must be >= 1, got {start_line}",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": line_count},
        )
    if end_line < start_line:
        return error_result_for_edit(
            f"end_line ({end_line}) must be >= start_line ({start_line})",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": line_count},
        )

    anchor_head = op.get("anchor_head")
    anchor_tail = op.get("anchor_tail")
    if (anchor_head is None) != (anchor_tail is None):
        return error_result_for_edit(
            "anchor_head and anchor_tail must be supplied together",
            LINE_OUT_OF_RANGE,
            {"fields": ["anchor_head", "anchor_tail"]},
        )

    if op_type == "insert":
        if start_line > line_count + 1:
            return error_result_for_edit(
                f"insert start_line {start_line} is beyond end of file "
                f"(line_count={line_count}; max insert line is {line_count + 1})",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "hint": (
                        "Line numbers are 1-based against the current draft. "
                        "Re-run universal_file_preview with session_id after each edit."
                    ),
                },
            )
    elif op_type in ("replace", "delete"):
        if start_line > line_count or end_line > line_count:
            return error_result_for_edit(
                f"line range {start_line}-{end_line} is out of range "
                f"(draft has {line_count} lines)",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "hint": (
                        "Line numbers are 1-based against the current draft. "
                        "Do not reuse line numbers from fulltext_search or an earlier "
                        "read after a prior universal_file_edit call — re-run "
                        "universal_file_preview with session_id first."
                    ),
                },
            )
        if anchor_head is not None:
            try:
                check_text_anchor(
                    buffer,
                    start_line,
                    end_line,
                    anchor_head,
                    anchor_tail,
                )
            except AnchorMismatch as exc:
                return error_result_for_edit(
                    str(exc),
                    ANCHOR_MISMATCH,
                    {
                        **exc.details,
                        "line_count": line_count,
                        "hint": (
                            "The target lines no longer match the expected content. "
                            "Re-run universal_file_preview with session_id to obtain "
                            "fresh line numbers from the draft."
                        ),
                    },
                )

    return None


def _insert_op_has_unresolved_node_target(op: Dict[str, Any]) -> bool:
    """True when insert names a node address but ``start_line`` was not resolved."""
    if op.get("position") == "last":
        return False
    action = op.get("type") or op.get("action") or "replace"
    if str(action).lower() != "insert":
        return False
    if op.get("start_line") is not None:
        return False
    return _operation_uses_node_address(_coalesce_node_ref_keys(op))


def _validate_unresolved_text_insert_targets(
    operations: List[Dict[str, Any]],
) -> Optional[ErrorResult]:
    """Reject insert ops that named node_ref targets but got no line range."""
    for op in operations:
        if not _insert_op_has_unresolved_node_target(op):
            continue
        m = _coalesce_node_ref_keys(op)
        return error_result_for_edit(
            "insert node_ref could not be resolved to a draft line position.",
            UNKNOWN_NODE_REF,
            {
                "node_ref": m.get("node_ref") or m.get("node_id"),
                "target_node_id": m.get("target_node_id"),
                "hint": (
                    "Use node_ref / target_node_id from universal_file_preview "
                    "with the same session_id. For .md marked-tree preview, "
                    "pass integer short_id as node_ref or target_node_id."
                ),
            },
        )
    return None


def _run_valid_text_tree_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply text-format edits via short_id EditOperation dispatch when tree is valid."""
    try:
        bm = BackupManager(root_dir=session.core.project_root)
        bm.create_backup(
            session.core.session_source_path, command="universal_file_edit"
        )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.core.session_source_path)},
        )

    tree_snapshot = session.core.session_tree_path.read_text(encoding="utf-8")
    source_snapshot = session.core.session_source_path.read_text(encoding="utf-8")

    def _rollback() -> None:
        session.core.session_tree_path.write_text(tree_snapshot, encoding="utf-8")
        session.core.session_source_path.write_text(source_snapshot, encoding="utf-8")

    try:
        for op in operations:
            sections = parse_tree_file(
                session.core.session_tree_path.read_text(encoding="utf-8")
            )
            for expanded in expand_markdown_section_ops(op, sections, session.core):
                edit_op = command_op_to_edit_operation(expanded, sections, session.core)
                apply_tree_operation(session, edit_op)
    except (EditOperationError, ValueError) as exc:
        _rollback()
        return error_result_for_edit(
            str(exc),
            INVALID_OPERATION,
            {"operations": operations},
        )
    except Exception as exc:
        _rollback()
        return error_result_for_edit(
            str(exc),
            WRITE_FAILED,
            {"path": str(session.core.session_tree_path)},
        )

    line_count = len(
        session.core.session_source_path.read_text(encoding="utf-8").splitlines()
    )
    return SuccessResult(data={"success": True, "line_count": line_count})


def run_text_draft_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply text edits to ``session.draft_path`` sorted bottom-up.

    Each operation supports:
    - ``type``: replace (default) | insert | delete
    - ``node_ref``: optional; for ``.md`` slug paths from preview, or zero-based
      line index for other text files. Takes precedence over ``start_line``/``end_line``.
      For ``.md`` insert with ``node_ref``: ``position`` ``before`` (insert at the
      section heading line) or ``after`` (default; after the section's last line).
    - ``start_line``: 1-based start line (inclusive).
    - ``end_line``: 1-based end line (inclusive); defaults to start_line.
    - ``content``: text to write.
    - ``anchor_head`` / ``anchor_tail``: optional fingerprints of the target
      range (first/last line, first/last five non-whitespace chars). When
      supplied, both must be present and must match the current draft lines
      before the edit is applied.
    - ``position``: ``'last'`` — append to end of file.
      When ``position='last'``, ``start_line``/``end_line`` are ignored.
    """

    if session_has_map_tree(session.core) and text_ops_use_unified_tree(operations):
        if sidecar_ops_use_unified_tree(session.core, operations):
            return _run_valid_text_tree_apply(session, operations)
        m = _coalesce_node_ref_keys(operations[0])
        return error_result_for_edit(
            "One or more node_ref values could not be resolved in the session tree.",
            UNKNOWN_NODE_REF,
            {
                "operations": operations,
                "node_ref": m.get("node_ref") or m.get("node_id"),
                "target_node_id": m.get("target_node_id"),
            },
        )

    try:
        root_dir = project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    buffer = session.draft_path.read_text(encoding="utf-8").splitlines(keepends=True)

    operations, move_err = expand_text_move_operations(session, buffer, operations)
    if move_err is not None:
        return move_err

    for op in operations:
        ref_err = resolve_text_operation_line_range(
            session.draft_path,
            op,
            session_is_invalid=session.is_invalid,
        )
        if ref_err is not None:
            return ref_err

    unresolved = _validate_unresolved_text_insert_targets(operations)
    if unresolved is not None:
        return unresolved

    for op in operations:
        if not session.is_invalid:
            continue
        if op.get("type", "replace") != "replace":
            continue
        if op.get("node_ref") not in ("", None):
            continue
        content_raw = op.get("content", op.get("code", ""))
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        block = content_str if content_str.endswith("\n") else content_str + "\n"
        apply_source_mutation(session, block)
        return SuccessResult(
            data={"success": True, "line_count": len(block.splitlines())},
        )

    # Separate position='last' ops (always append, no sort needed) from
    # line-targeted ops (must be applied bottom-up to keep line numbers stable).
    append_ops: List[Dict[str, Any]] = []
    line_ops: List[Dict[str, Any]] = []
    for op in operations:
        if op.get("position") == "last":
            append_ops.append(op)
        else:
            line_ops.append(op)

    for op in line_ops:
        validation = _validate_text_line_operation(buffer, op)
        if validation is not None:
            return validation

    # Sort line-targeted ops bottom-up.
    keyed: List[Dict[str, Any]] = []
    for op in line_ops:
        s_ln = int(op.get("start_line", 1))
        e_raw = op.get("end_line")
        e_ln = s_ln if e_raw is None else int(e_raw)
        keyed.append({"start": s_ln, "end": e_ln, "op": op})
    triples_only: List[TextReplacementTriple] = [
        (int(k["start"]), int(k["end"]), [], None, None) for k in keyed
    ]
    _sort_text_replacements_bottom_up(triples_only)
    keyed.sort(key=lambda row: (row["start"], row["end"]), reverse=True)
    sorted_ops = [row["op"] for row in keyed]

    # Apply line-targeted ops first (bottom-up).
    for op in sorted_ops:
        start = int(op.get("start_line", 1)) - 1
        e_raw = op.get("end_line")
        end = (start + 1) if e_raw is None else int(e_raw)
        content_raw = op.get("content", "")
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        op_type = op.get("type", "replace")
        if op_type == "delete":
            del buffer[start:end]
        elif op_type == "insert":
            inserted = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer.insert(start, inserted)
        else:
            block = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer[start:end] = [block]

    # Apply position='last' ops in order (append to current end of buffer).
    for op in append_ops:
        content_raw = op.get("content", "")
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        op_type = op.get("type", "replace")
        if op_type == "delete":
            # delete with position='last' removes the last line if buffer non-empty
            if buffer:
                buffer.pop()
        else:
            # insert and replace both append to end
            appended = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer.append(appended)

    new_text = "".join(buffer)
    apply_source_mutation(session, new_text)

    return SuccessResult(
        data={"success": True, "line_count": len(buffer)},
    )
