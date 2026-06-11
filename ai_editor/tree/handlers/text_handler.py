"""
Text FormatHandler (.txt, .rst) — integer short_id line prefixes (C-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.format_handler import FormatHandler, ShortIdAllocator
from ai_editor.tree.tree_node import TreeNode

_MARKER_LINE_RE = re.compile(r"^(\d+):", re.MULTILINE)
_MARKER_PREFIX_RE = re.compile(r"^\d+:")


class TextHandler(FormatHandler):
    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        if content == "":
            return []
        allocator = ShortIdAllocator(start=1)
        nodes: List[TreeNode] = []
        in_paragraph = False
        for i, line in enumerate(content.splitlines(keepends=True), start=1):
            stripped = line.rstrip("\n")
            if stripped == "":
                in_paragraph = False
                continue
            kind = "paragraph" if not in_paragraph else "line"
            sid = allocator.allocate()
            attributes = {"line_no": i, "block_level": kind}
            if kind == "paragraph":
                attributes["is_paragraph_start"] = True
            nodes.append(
                TreeNode(
                    short_id=NodeId(sid),
                    kind=kind,
                    content=stripped,
                    attributes=attributes,
                )
            )
            in_paragraph = True
        return nodes

    def mark(self, content: str) -> str:
        allocator = ShortIdAllocator(1)
        in_paragraph = False
        result: List[str] = []
        for line in content.splitlines(keepends=True):
            stripped = line.rstrip("\n")
            if stripped == "":
                in_paragraph = False
                result.append(line)
                continue
            sid = allocator.allocate()
            prefix = f"{sid}:"
            if line.endswith("\n"):
                result.append(f"{prefix}{stripped}\n")
            else:
                result.append(f"{prefix}{stripped}")
            in_paragraph = True
        return "".join(result)

    def unmark(self, marked_text: str) -> str:
        result: List[str] = []
        for line in marked_text.splitlines(keepends=True):
            line_without_newline = line.rstrip("\n")
            newline_suffix = line[len(line_without_newline) :]
            if _MARKER_PREFIX_RE.match(line_without_newline):
                restored = _MARKER_PREFIX_RE.sub("", line_without_newline, count=1)
                result.append(restored + newline_suffix)
            else:
                result.append(line)
        return "".join(result)

    def sidecar_path(self, source_abs: Path) -> Path:
        return source_abs.parent / (source_abs.name + ".tree")

    def op_insert(
        self,
        marked_text: str,
        anchor_short_id: NodeId,
        position: str,
        new_content: str,
        next_free: int,
    ) -> str:
        if next_free < 1:
            raise ValueError("next_free must be >= 1")
        if position not in ("before", "after", "first_child", "last_child"):
            raise ValueError(f"invalid position: {position!r}")
        nodes, blank_lines = _parse_marked(marked_text)
        anchor = _find_node(nodes, anchor_short_id)
        anchor_idx = nodes.index(anchor)
        if position in ("before", "first_child"):
            insert_at = anchor_idx
        elif position in ("after", "last_child"):
            insert_at = anchor_idx + 1
        else:
            raise ValueError(f"invalid position: {position!r}")
        new_sid = NodeId(next_free)
        new_node = TreeNode(
            short_id=new_sid,
            kind="paragraph",
            content=new_content.strip(),
            attributes={"trailing_newline": True},
        )
        nodes.insert(insert_at, new_node)
        return _serialize_marked(nodes, blank_lines)

    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        nodes, blank_lines = _parse_marked(marked_text)
        target = _find_node(nodes, short_id)
        anchor_idx = nodes.index(target)
        remove = [anchor_idx]
        if target.kind == "paragraph":
            j = anchor_idx + 1
            while j < len(nodes) and nodes[j].kind == "line":
                remove.append(j)
                j += 1
        for idx in sorted(remove, reverse=True):
            del nodes[idx]
        return _serialize_marked(nodes, blank_lines)

    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        nodes, blank_lines = _parse_marked(marked_text)
        node = _find_node(nodes, short_id)
        node.content = new_content
        return _serialize_marked(nodes, blank_lines)

    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        nodes, _blank_lines = _parse_marked(marked_text)
        src = _find_node(nodes, short_id)
        src_idx = nodes.index(src)
        block_indices = [src_idx]
        if src.kind == "paragraph":
            j = src_idx + 1
            while j < len(nodes) and nodes[j].kind == "line":
                block_indices.append(j)
                j += 1
        return "\n".join(nodes[i].content for i in block_indices)

    def op_move(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
    ) -> str:
        next_free = self.peak_short_id_in_marked(marked_text) + 1
        return self.op_move_via_delete_insert(
            marked_text,
            short_id,
            anchor_short_id,
            position,
            next_free,
        )

    def op_edit_attributes(
        self, marked_text: str, short_id: NodeId, attributes: Dict[str, Any]
    ) -> str:
        nodes, blank_lines = _parse_marked(marked_text)
        node = _find_node(nodes, short_id)
        node.attributes.update(attributes)
        return _serialize_marked(nodes, blank_lines)

    def op_edit_content(
        self, marked_text: str, short_id: NodeId, new_content: str
    ) -> str:
        nodes, blank_lines = _parse_marked(marked_text)
        node = _find_node(nodes, short_id)
        if not _is_leaf_line_node(node, nodes):
            raise ValueError("edit-content requires leaf block")
        node.content = new_content
        return _serialize_marked(nodes, blank_lines)


def _parse_marked(marked_text: str) -> Tuple[List[TreeNode], List[Tuple[int, str]]]:
    lines = marked_text.splitlines(keepends=True)
    nodes: List[TreeNode] = []
    blank_lines: List[Tuple[int, str]] = []
    in_paragraph = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == "":
            in_paragraph = False
            blank_lines.append((i, line))
            continue
        match = _MARKER_LINE_RE.match(stripped)
        if not match:
            raise ValueError(f"marked line missing integer prefix: {stripped!r}")
        sid = int(match.group(1))
        body = stripped[match.end() :]
        kind = "paragraph" if not in_paragraph else "line"
        attributes: Dict[str, Any] = {"line_no": i + 1, "block_level": kind}
        if kind == "paragraph":
            attributes["is_paragraph_start"] = True
        attributes["trailing_newline"] = line.endswith("\n")
        nodes.append(
            TreeNode(
                short_id=NodeId(sid),
                kind=kind,
                content=body,
                attributes=attributes,
            )
        )
        in_paragraph = True
    return nodes, blank_lines


def _serialize_marked(nodes: List[TreeNode], blank_lines: List[Tuple[int, str]]) -> str:
    blank_at = {idx: line for idx, line in blank_lines}
    total = len(nodes) + len(blank_lines)
    if blank_at:
        total = max(total, max(blank_at) + 1)
    parts: List[str] = []
    node_i = 0
    for i in range(total):
        if i in blank_at:
            parts.append(blank_at[i])
            continue
        if node_i >= len(nodes):
            break
        node = nodes[node_i]
        node_i += 1
        prefix = f"{int(node.short_id)}:"
        body = node.content
        line = f"{prefix}{body}"
        if node.attributes.get("trailing_newline", True):
            if not line.endswith("\n"):
                line += "\n"
        elif line.endswith("\n"):
            line = line[:-1]
        parts.append(line)
    return "".join(parts)


def _find_node(nodes: List[TreeNode], short_id: NodeId) -> TreeNode:
    for node in nodes:
        if node.short_id == short_id:
            return node
    raise UnknownNodeIdError(short_id)


def _is_leaf_line_node(node: TreeNode, nodes: List[TreeNode]) -> bool:
    if node.kind == "line":
        return True
    if node.kind != "paragraph":
        return False
    idx = nodes.index(node)
    for j in range(idx + 1, len(nodes)):
        if nodes[j].kind == "line":
            return False
    return True
