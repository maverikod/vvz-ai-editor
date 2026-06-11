"""
TreeNode to tolerant JSON SourceSerializer with comment restoration (C-006, C-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from typing import List, NoReturn

from ai_editor.core.tree_temp.tree_node import TreeNode

_ERR_PREFIX = "Invalid tree for JSON serialization:"


def _fail(msg: str) -> NoReturn:
    raise ValueError(f"{_ERR_PREFIX} {msg}")


def _validate_scalar(node: TreeNode) -> None:
    if node.children is not None:
        _fail("scalar node must not set children")
    if node.type == "string":
        if not isinstance(node.value, str):
            _fail("string node value must be str")
    elif node.type == "number":
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            _fail("number node value must be int or float (not bool)")
    elif node.type == "boolean":
        if not isinstance(node.value, bool):
            _fail("boolean node value must be bool")
    elif node.type == "null":
        if node.value is not None:
            _fail("null node value must be Python None")
    else:
        _fail(f"unexpected scalar type {node.type!r}")


def validate_tree_json(node: TreeNode, *, object_member: bool = False) -> None:
    """Validate TreeNode constraints for JSON serialization."""
    if not isinstance(node.stable_id, str) or not node.stable_id.strip():
        _fail("stable_id must be a non-empty string")
    if object_member:
        if node.key is None or not isinstance(node.key, str) or not node.key:
            _fail("object member requires non-empty string key")
    elif node.key is not None:
        _fail("non-member node must not set key")

    if node.type == "object":
        if node.value is not None:
            _fail("container nodes must not set value")
        chs = node.children
        if chs is None:
            _fail("object node requires children list")
        if not isinstance(chs, list):
            _fail("object node requires children list")
        for ch in chs:
            if not isinstance(ch, TreeNode):
                _fail("children must be TreeNode instances")
            validate_tree_json(ch, object_member=True)
        return

    if node.type == "array":
        if node.value is not None:
            _fail("container nodes must not set value")
        chs = node.children
        if chs is None:
            _fail("array node requires children list")
        if not isinstance(chs, list):
            _fail("array node requires children list")
        for ch in chs:
            if not isinstance(ch, TreeNode):
                _fail("children must be TreeNode instances")
            validate_tree_json(ch, object_member=False)
        return

    _validate_scalar(node)


def _emit_before(comment_before: str | None) -> List[str]:
    if not comment_before:
        return []
    out: List[str] = []
    for line in comment_before.split("\n"):
        if line.strip():
            out.append(line + "\n")
    return out


def _scalar_body(node: TreeNode) -> str:
    if node.type == "string":
        return json.dumps(node.value, ensure_ascii=False)
    if node.type == "number":
        v = node.value
        if isinstance(v, bool):
            _fail("number node value must not be bool")
        return json.dumps(v)
    if node.type == "boolean":
        return json.dumps(node.value)
    if node.type == "null":
        return "null"
    _fail(f"invalid scalar type {node.type!r}")
    return ""


def _append_inline(line: str, comment_inline: str | None) -> str:
    if comment_inline:
        return line + " " + comment_inline
    return line


def _emit_lines(
    node: TreeNode, depth: int, *, object_member_key: str | None
) -> List[str]:
    ind = "  " * depth
    out: List[str] = []
    out.extend(_emit_before(node.comment_before))

    if node.type in ("string", "number", "boolean", "null"):
        body = _scalar_body(node)
        prefix = ind
        if object_member_key is not None:
            prefix += json.dumps(object_member_key, ensure_ascii=False) + ": "
        out.append(_append_inline(prefix + body, node.comment_inline) + "\n")
        return out

    if node.type == "array":
        head = ind
        if object_member_key is not None:
            head += json.dumps(object_member_key, ensure_ascii=False) + ": "
        out.append(head + "[\n")
        arr_children = node.children
        if arr_children is None:
            _fail("array node missing children during emission")
        last = len(arr_children) - 1
        for idx, ch in enumerate(arr_children):
            sub = _emit_lines(ch, depth + 1, object_member_key=None)
            if idx != last and sub:
                sub[-1] = sub[-1].rstrip("\n") + ",\n"
            out.extend(sub)
        out.append(_append_inline(ind + "]", node.comment_inline) + "\n")
        return out

    if node.type == "object":
        head = ind
        if object_member_key is not None:
            head += json.dumps(object_member_key, ensure_ascii=False) + ": "
        out.append(head + "{\n")
        obj_children = node.children
        if obj_children is None:
            _fail("object node missing children during emission")
        last = len(obj_children) - 1
        for idx, ch in enumerate(obj_children):
            key = ch.key
            if key is None:
                _fail("object member missing key during emission")
            sub = _emit_lines(ch, depth + 1, object_member_key=key)
            if idx != last and sub:
                sub[-1] = sub[-1].rstrip("\n") + ",\n"
            out.extend(sub)
        out.append(_append_inline(ind + "}", node.comment_inline) + "\n")
        return out

    _fail(f"unsupported node type {node.type!r}")
    return []


def serialize_json_source(root_nodes: List[TreeNode]) -> str:
    """Serialize root TreeNode list to UTF-8 tolerant JSON text (C-006).

    Formatting rules:
    - Use 2-space indent, Unix \\n newlines, ensure_ascii=False, trailing newline at EOF.
    - Object keys are double-quoted; string values JSON-escaped.
    - Order: emit comment_before lines first (each non-empty line from comment_before emitted as-is
      followed by newline); then emit the structural line for the node; if comment_inline is set,
      one horizontal space then the inline comment string appended on the same line (no extra space inside
      the stored comment string).
    - comment_before and comment_inline strings are emitted exactly as stored (they already include // or /*
      delimiters per parser contract).
    - For block multi-line comments in comment_before, emit as stored (may span lines).
    Raises:
        ValueError: messages start with \"Invalid tree for JSON serialization:\" for inconsistent TreeNode
        field usage versus type (e.g. value set on object node, children on scalar, missing key on object member).
    """
    if len(root_nodes) == 0:
        return "[]\n"

    for r in root_nodes:
        validate_tree_json(r, object_member=False)

    if len(root_nodes) == 1:
        return "".join(_emit_lines(root_nodes[0], 0, object_member_key=None))

    lines: List[str] = ["[\n"]
    last_i = len(root_nodes) - 1
    for i, root in enumerate(root_nodes):
        sub = _emit_lines(root, 1, object_member_key=None)
        if i != last_i and sub:
            sub[-1] = sub[-1].rstrip("\n") + ",\n"
        lines.extend(sub)
    lines.append("]\n")
    return "".join(lines)
