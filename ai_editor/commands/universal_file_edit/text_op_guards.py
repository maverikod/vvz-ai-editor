"""
Operation guards for the plain-text and parse-error-fallback edit pipelines.

Every guard here runs BEFORE any mutation reaches the draft, so a rejected
batch leaves the draft byte-identical: no operation of it is half-applied.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.anchor_check import AnchorMismatch, check_text_anchor
from ai_editor.commands.universal_file_edit.errors import (
    ANCHOR_MISMATCH,
    INVALID_OPERATION,
    LINE_OUT_OF_RANGE,
    UNKNOWN_NODE_REF,
    error_result_for_edit,
)
from ai_editor.commands.universal_file_edit.text_fallback_tree import (
    ROOT_NODE_REF,
    FallbackDocumentTree,
)
from ai_editor.core.edit_session.edit_operations_adapter import (
    _coalesce_node_ref_keys,
    _operation_uses_node_address,
)

# The operation types ``universal_file_edit`` declares in its own metadata.
KNOWN_OPERATION_TYPES = frozenset({"replace", "insert", "delete", "move"})

# Payload keys of the Python sidecar form. They address a CST node, which a
# parse-error fallback session by definition does not have. ``code`` is NOT one
# of them: the text pipeline has always accepted it as a plain content alias.
SIDECAR_ONLY_KEYS = ("code_lines", "stable_id")


def line_count(buffer: List[str]) -> int:
    return len(buffer)


def resolve_line_range(op: Dict[str, Any]) -> tuple[int, int]:
    start_line = int(op.get("start_line", 1))
    end_raw = op.get("end_line")
    end_line = start_line if end_raw is None else int(end_raw)
    return start_line, end_line


def _declared_type_tokens(op: Dict[str, Any]) -> List[Any]:
    """Every operation-type token the caller actually supplied."""
    return [op[key] for key in ("type", "action") if key in op and op[key] is not None]


def validate_operation_types(
    operations: List[Dict[str, Any]],
) -> Optional[ErrorResult]:
    """Reject any operation whose declared type is not a documented one.

    An unrecognised type must never fall through to the default branch of the
    apply loop and be silently carried out as a replace.
    """
    for op in operations:
        for token in _declared_type_tokens(op):
            normalized = token.strip().lower() if isinstance(token, str) else token
            if normalized in KNOWN_OPERATION_TYPES:
                continue
            return error_result_for_edit(
                f"Unsupported operation type: {token!r}",
                INVALID_OPERATION,
                {
                    "type": token,
                    "supported_types": sorted(KNOWN_OPERATION_TYPES),
                    "hint": (
                        "Use type: replace | insert | delete | move with "
                        "universal_file_edit."
                    ),
                },
            )
    return None


def _op_type(op: Dict[str, Any]) -> str:
    raw = op.get("type", op.get("action", "replace"))
    return raw.strip().lower() if isinstance(raw, str) else "replace"


def validate_fallback_operation(
    tree: FallbackDocumentTree,
    op: Dict[str, Any],
) -> Optional[ErrorResult]:
    """Resolve one operation against the fallback tree, or refuse it.

    Line numbers are kept as a convenience, but only because every one of them
    maps onto a real line node of ``tree``; an address outside the tree is
    refused here rather than sliced out of the buffer downstream.
    """
    if op.get("position") == "last":
        return None

    op_type = _op_type(op)
    node_ref = op.get("node_ref")

    forbidden = _reject_sidecar_node_form(op, op_type)
    if forbidden is not None:
        return forbidden

    if "node_ref" in op and str(node_ref) == ROOT_NODE_REF:
        return _resolve_root_ref(tree, op, op_type)

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
                    "Address the draft with node_ref from universal_file_preview "
                    "(the empty string is the document root) or with explicit "
                    "start_line/end_line."
                ),
            },
        )

    start_line, end_line = resolve_line_range(op)
    if op_type == "insert":
        if not tree.accepts_insert_at(start_line):
            return _out_of_tree(tree, start_line, end_line, insert=True)
        return None
    if not tree.covers(start_line, end_line):
        return _out_of_tree(tree, start_line, end_line, insert=False)
    return None


def _resolve_root_ref(
    tree: FallbackDocumentTree,
    op: Dict[str, Any],
    op_type: str,
) -> Optional[ErrorResult]:
    """Bind ``node_ref: ""`` to the document root's own line span."""
    if op_type not in ("replace", "delete"):
        return error_result_for_edit(
            f"The document root cannot be the target of a {op_type!r} operation.",
            INVALID_OPERATION,
            {"node_ref": ROOT_NODE_REF, "op_type": op_type},
        )
    if tree.line_count == 0:
        # An empty document has no line node to replace; seed it instead.
        op["type"] = "insert"
        op["start_line"] = 1
        op.pop("end_line", None)
        return None
    op["start_line"] = tree.root.start_line
    op["end_line"] = tree.root.end_line
    return None


def _reject_sidecar_node_form(
    op: Dict[str, Any],
    op_type: str,
) -> Optional[ErrorResult]:
    """Refuse Python sidecar node operations: the fallback has no CST tree."""
    present = [key for key in SIDECAR_ONLY_KEYS if op.get(key) not in (None, "")]
    addresses_node = _operation_uses_node_address(_coalesce_node_ref_keys(dict(op)))
    if not present and not (addresses_node and op.get("node_ref") in (None, "")):
        return None
    return error_result_for_edit(
        "Node operations are not available in the line-based fallback: this "
        "session has no parsed tree to address.",
        INVALID_OPERATION,
        {
            "op_type": op_type,
            "sidecar_keys": present,
            "received_keys": sorted(op.keys()),
            "hint": (
                "Fix the parse errors and commit with write_mode=commit to "
                "restore node addressing, or edit by node_ref / "
                "start_line+end_line while the file does not parse."
            ),
        },
    )


def _out_of_tree(
    tree: FallbackDocumentTree,
    start_line: int,
    end_line: int,
    *,
    insert: bool,
) -> ErrorResult:
    limit = tree.line_count + 1 if insert else tree.line_count
    kind = "insert position" if insert else "line range"
    return error_result_for_edit(
        f"{kind} {start_line}-{end_line} does not resolve to a node of the "
        f"draft (the document has {tree.line_count} lines; highest addressable "
        f"line is {limit})",
        LINE_OUT_OF_RANGE,
        {
            "start_line": start_line,
            "end_line": end_line,
            "line_count": tree.line_count,
            "hint": (
                "Line numbers are 1-based against the current draft. Re-run "
                "universal_file_preview with session_id to obtain fresh line "
                "numbers before editing again."
            ),
        },
    )


def validate_text_line_operation(
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
    start_line, end_line = resolve_line_range(op)
    count = line_count(buffer)

    if start_line < 1:
        return error_result_for_edit(
            f"start_line must be >= 1, got {start_line}",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": count},
        )
    if end_line < start_line:
        return error_result_for_edit(
            f"end_line ({end_line}) must be >= start_line ({start_line})",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": count},
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
        if start_line > count + 1:
            return error_result_for_edit(
                f"insert start_line {start_line} is beyond end of file "
                f"(line_count={count}; max insert line is {count + 1})",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": count,
                    "hint": (
                        "Line numbers are 1-based against the current draft. "
                        "Re-run universal_file_preview with session_id after each edit."
                    ),
                },
            )
    elif op_type in ("replace", "delete"):
        if start_line > count or end_line > count:
            return error_result_for_edit(
                f"line range {start_line}-{end_line} is out of range "
                f"(draft has {count} lines)",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": count,
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
                check_text_anchor(buffer, start_line, end_line, anchor_head, anchor_tail)
            except AnchorMismatch as exc:
                return error_result_for_edit(
                    str(exc),
                    ANCHOR_MISMATCH,
                    {
                        **exc.details,
                        "line_count": count,
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


def validate_unresolved_text_insert_targets(
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
