"""
In-place replace, insert, delete on mutable tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Union, cast

import libcst as cst

from ai_editor.core.cst_tree.models import (
    ROOT_NODE_ID_SENTINEL,
    TreeOperation,
    TreeOperationType,
    TreeNodeMetadata,
)
from ai_editor.core.cst_tree.tree_modifier_ops import (
    join_code_lines,
    parse_code_snippet,
    parse_code_snippet_or_comment,
)

from .models import MutableNode, MutableTree, Span


def _indent(source: str, prefix: str = "    ") -> str:
    """Indent each line of source by prefix."""
    return "\n".join(prefix + line for line in source.split("\n"))


def _recompute_source_from_children(node: MutableNode) -> str:
    """Recompute node.source from children for container types."""
    if node.type == "Module":
        return "\n".join(c.source for c in node.children)
    if node.type == "IndentedBlock":
        return "\n".join(c.source for c in node.children)
    if node.type == "ClassDef":
        body = next((c for c in node.children if c.type == "IndentedBlock"), None)
        if body:
            return "class " + (node.name or "") + ":\n" + _indent(body.source)
        return node.source
    if node.type == "FunctionDef":
        body = next((c for c in node.children if c.type == "IndentedBlock"), None)
        if body:
            return "def " + (node.name or "") + "(self):\n" + _indent(body.source)
        return node.source
    return node.source


def _propagate_source_to_ancestors(tree: MutableTree, node: MutableNode) -> None:
    """After replacing node.source, update ancestor sources up to root."""
    current: Optional[MutableNode] = node.parent
    while current is not None:
        current.source = _recompute_source_from_children(current)
        current = current.parent


def _code_from_operation(op: TreeOperation) -> str:
    """Get code string from operation (code or code_lines)."""
    if op.code_lines:
        return join_code_lines(op.code_lines)
    if op.code:
        return op.code
    return ""


def _replace_node_source(
    tree: MutableTree,
    node_id: str,
    code: Optional[str] = None,
    code_lines: Optional[List[str]] = None,
) -> None:
    """Replace a node's source by id; parse with parse_code_snippet and set source."""
    node = tree.get_node(node_id)
    if not node:
        raise ValueError(f"Node not found: {node_id}")
    raw = join_code_lines(code_lines) if code_lines else (code or "")
    if not raw.strip():
        raise ValueError("code or code_lines required for replace")
    statements = parse_code_snippet(code=code, code_lines=code_lines)
    if not statements:
        raise ValueError("Parsed code produced no statements")
    new_source = cst.Module(
        body=cast(
            List[Union[cst.SimpleStatementLine, cst.BaseCompoundStatement]],
            statements,
        )
    ).code
    node.source = new_source
    _propagate_source_to_ancestors(tree, node)


def _insert_at_parent(
    tree: MutableTree,
    parent_node_id: str,
    code: Optional[str] = None,
    code_lines: Optional[List[str]] = None,
    position: str = "last",
    position_after_index: Optional[int] = None,
) -> None:
    """Insert parsed statements into parent's children at position."""
    parent_id = parent_node_id.strip() if parent_node_id else ROOT_NODE_ID_SENTINEL
    if parent_id == ROOT_NODE_ID_SENTINEL:
        parent = tree.root
    else:
        p = tree.get_node(parent_id)
        if p is None:
            raise ValueError(f"Parent node not found: {parent_id}")
        parent = p

    raw = join_code_lines(code_lines) if code_lines else (code or "")
    if not raw.strip():
        raise ValueError("code or code_lines required for insert")

    new_statements = parse_code_snippet_or_comment(code=code, code_lines=code_lines)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    insert_index: int
    pos = (position or "last").strip().lower()
    if pos == "first":
        insert_index = 0
    elif pos == "after" and position_after_index is not None:
        insert_index = min(position_after_index + 1, len(parent.children))
    else:
        insert_index = len(parent.children)

    dummy_span = Span(0, 0, 0, 0)
    new_nodes: List[MutableNode] = []
    for stmt in new_statements:
        stmt_id = str(uuid.uuid4())
        if isinstance(stmt, cst.EmptyLine):
            stmt_source = (
                (stmt.comment.value if stmt.comment else "") + "\n"
            ).strip() or "\n"
        else:
            try:
                stmt_source = cst.Module(
                    body=cast(
                        List[Union[cst.SimpleStatementLine, cst.BaseCompoundStatement]],
                        [stmt],
                    )
                ).code
            except Exception:
                stmt_source = raw
        stmt_type = stmt.__class__.__name__
        name = None
        if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)):
            name = stmt.name.value
        mutable = MutableNode(
            node_id=stmt_id,
            type=stmt_type,
            name=name,
            source=stmt_source,
            span=dummy_span,
            parent=parent,
            children=[],
        )
        new_nodes.append(mutable)
        tree.node_map[stmt_id] = mutable

    for i, n in enumerate(new_nodes):
        parent.children.insert(insert_index + i, n)
    _propagate_source_to_ancestors(tree, parent)


def _delete_node(tree: MutableTree, node_id: str) -> None:
    """Remove node from parent's children and from node_map."""
    node = tree.get_node(node_id)
    if not node:
        raise ValueError(f"Node not found: {node_id}")
    parent = node.parent
    if parent is not None:
        try:
            parent.children.remove(node)
        except ValueError:
            pass
        _propagate_source_to_ancestors(tree, parent)
    tree.node_map.pop(node_id, None)


def _sort_operations(
    operations: List[TreeOperation],
    metadata_map: Dict[str, TreeNodeMetadata],
) -> List[TreeOperation]:
    """Sort by (end_line, end_col) descending for safe batch application."""
    keyed: List[tuple] = []
    for op in operations:
        if op.action == TreeOperationType.REPLACE and op.node_id:
            meta = metadata_map.get(op.node_id)
            end_line = meta.end_line if meta else 0
            end_col = meta.end_col if meta else 0
            keyed.append((-end_line, -end_col, op))
        elif op.action == TreeOperationType.DELETE and op.node_id:
            meta = metadata_map.get(op.node_id)
            end_line = meta.end_line if meta else 0
            end_col = meta.end_col if meta else 0
            keyed.append((-end_line, -end_col, op))
        elif op.action == TreeOperationType.INSERT and op.parent_node_id:
            pid = (
                op.parent_node_id.strip()
                if op.parent_node_id
                else ROOT_NODE_ID_SENTINEL
            )
            if pid == ROOT_NODE_ID_SENTINEL:
                keyed.append((0, 0, op))
            else:
                meta = metadata_map.get(pid)
                end_line = meta.end_line if meta else 0
                end_col = meta.end_col if meta else 0
                keyed.append((-end_line, -end_col, op))
        else:
            keyed.append((0, 0, op))
    keyed.sort(key=lambda x: (x[0], x[1]))
    return [op for (_, _, op) in keyed]


def apply_operations(
    tree: MutableTree,
    operations: List[TreeOperation],
    metadata_map: Dict[str, TreeNodeMetadata],
) -> None:
    """
    Apply replace/insert/delete operations in place.

    Operations are sorted by (end_line, end_col) descending, then applied.
    Replace and delete use node_id; insert uses parent_node_id and position.

    Args:
        tree: Mutable tree to modify in place.
        operations: List of TreeOperation (REPLACE, INSERT, DELETE only).
        metadata_map: Current metadata for sorting (node_id -> TreeNodeMetadata).
    """
    sorted_ops = _sort_operations(operations, metadata_map)
    for op in sorted_ops:
        if op.action == TreeOperationType.REPLACE:
            _replace_node_source(
                tree,
                op.node_id,
                code=op.code,
                code_lines=op.code_lines,
            )
        elif op.action == TreeOperationType.INSERT:
            parent_id = op.parent_node_id or ROOT_NODE_ID_SENTINEL
            position = op.position or "last"
            position_after_index = op.position_after_index
            if op.target_node_id:
                meta = metadata_map.get(op.target_node_id)
                if meta and meta.parent_id:
                    parent_id = meta.parent_id
                position = (op.position or "after").strip().lower()
                if position in ("before", "after"):
                    parent_node = (
                        tree.root
                        if parent_id == ROOT_NODE_ID_SENTINEL
                        else tree.get_node(parent_id)
                    )
                    if parent_node:
                        for i, ch in enumerate(parent_node.children):
                            if ch.node_id == op.target_node_id:
                                if position == "before":
                                    position_after_index = max(0, i - 1)
                                    if i == 0:
                                        position = "first"
                                    else:
                                        position = "after"
                                else:
                                    position_after_index = i
                                    position = "after"
                                break
            _insert_at_parent(
                tree,
                parent_id,
                code=op.code,
                code_lines=op.code_lines,
                position=position,
                position_after_index=position_after_index,
            )
        elif op.action == TreeOperationType.DELETE:
            _delete_node(tree, op.node_id)
