from __future__ import annotations

import re
import uuid
from typing import Optional

import libcst as cst


_STABLE_ID_RE = re.compile(r"#\s*@node-id:\s*([0-9a-f-]{36})")
_STABLE_ID_PREFIX = "# @node-id: "
# Whole-line legacy markers (same shape as LibCST ``Comment.value`` for leading_lines)
_INLINE_NODE_ID_LINE_RE = re.compile(r"^\s*#\s*@node-id:\s*[0-9a-fA-F-]{36}\s*$")

_SUPPORTED = (cst.FunctionDef, cst.ClassDef)


def strip_inline_node_id_lines_from_source(source: str) -> str:
    """Drop standalone ``# @node-id: <uuid>`` lines from raw source (legacy persistence).

    Used when loading/saving so logical ``.py`` has no inline identity markers.
    ``stable_id`` for edit sessions lives in sidecar ``metadata_map``, not in source.
    """
    lines = source.splitlines()
    kept = [ln for ln in lines if not _INLINE_NODE_ID_LINE_RE.match(ln)]
    out = "\n".join(kept)
    if source.endswith("\n"):
        out += "\n"
    return out


def logical_source_from_module(module: cst.Module) -> str:
    """Canonical source text (no legacy inline ``# @node-id`` lines)."""
    return strip_inline_node_id_lines_from_source(module.code)


def get_stable_id(node: cst.CSTNode) -> Optional[str]:
    """Extract legacy stable_id from def/class ``leading_lines`` (old on-disk files).

    In-memory edit identity is ``TreeNodeMetadata.stable_id`` / sidecar JSON.
    """
    if not isinstance(node, _SUPPORTED):
        return None
    for empty_line in node.leading_lines:
        if empty_line.comment is not None:
            m = _STABLE_ID_RE.match(empty_line.comment.value)
            if m:
                return m.group(1)
    return None


def set_stable_id(node: cst.CSTNode, stable_id: str) -> cst.CSTNode:
    """Write legacy ``# @node-id`` into def/class ``leading_lines`` (migration only)."""
    if not isinstance(node, _SUPPORTED):
        return node
    comment_line = cst.EmptyLine(
        whitespace=cst.SimpleWhitespace(""),
        comment=cst.Comment(f"{_STABLE_ID_PREFIX}{stable_id}"),
    )
    existing = list(node.leading_lines)
    filtered = [
        line
        for line in existing
        if line.comment is None or not _STABLE_ID_RE.match(line.comment.value)
    ]
    new_leading = [comment_line] + filtered
    return node.with_changes(leading_lines=new_leading)


def ensure_stable_id(node: cst.CSTNode) -> tuple[cst.CSTNode, str]:
    """Ensure legacy def/class node has inline stable_id (migration only)."""
    existing = get_stable_id(node)
    if existing:
        return node, existing
    new_id = str(uuid.uuid4())
    return set_stable_id(node, new_id), new_id
