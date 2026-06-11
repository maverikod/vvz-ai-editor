"""
Build mutable tree from LibCST Module with node_ids aligned to existing index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from ai_editor.core.cst_tree.models import TreeNodeMetadata

from .models import MutableNode, MutableTree, Span


def _build_id_to_node_id(
    node_map: Dict[str, cst.CSTNode],
) -> Dict[int, str]:
    """Build id(libcst_node) -> node_id from tree.node_map for same-object resolution."""
    return {id(n): nid for nid, n in node_map.items()}


def _build_exact_key_to_id(
    metadata_map: Dict[str, TreeNodeMetadata],
) -> Dict[Tuple[int, int, int, int, str], str]:
    """Build (start_line, start_col, end_line, end_col, type) -> node_id."""
    key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    for nid, meta in metadata_map.items():
        key = (
            meta.start_line,
            meta.start_col,
            meta.end_line,
            meta.end_col,
            meta.type,
        )
        key_to_id[key] = nid
    return key_to_id


def _get_node_name(node: cst.CSTNode) -> Optional[str]:
    """Get node name for ClassDef/FunctionDef."""
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return node.name.value
    return None


def build_from_libcst(
    module: cst.Module,
    metadata_map: Dict[str, TreeNodeMetadata],
    node_map: Optional[Dict[str, cst.CSTNode]] = None,
) -> MutableTree:
    """
    Build a mutable tree from a LibCST Module with node_ids matching metadata_map.

    Single walk over the module using MetadataWrapper and PositionProvider.
    Each mutable node gets the same node_id as in metadata_map: first by
    id(libcst_node) from node_map (if provided), else by (start_line, start_col,
    end_line, end_col, type). Resulting tree has correct parent/children and spans.

    Args:
        module: Parsed LibCST Module.
        metadata_map: Current tree's node_id -> TreeNodeMetadata (from CSTTree).
        node_map: Optional tree.node_map (node_id -> CSTNode) to resolve by object id.

    Returns:
        MutableTree with root and node_map; every key in metadata_map
        appears in the tree's node_map when node_map is provided.
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    parents = wrapper.resolve(ParentNodeProvider)

    id_to_node_id: Dict[int, str] = {}
    if node_map:
        id_to_node_id = _build_id_to_node_id(node_map)
    exact_key_to_id = _build_exact_key_to_id(metadata_map)
    node_to_mutable: Dict[int, MutableNode] = {}
    stack: List[MutableNode] = []

    def visit(node: cst.CSTNode) -> None:
        node_type = node.__class__.__name__
        pos = positions.get(node)
        if pos is None:
            for child in node.children:
                visit(child)
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            for child in node.children:
                visit(child)
            return

        key = (start_line, start_col, end_line, end_col, node_type)
        node_id = id_to_node_id.get(id(node))
        if node_id is None:
            node_id = exact_key_to_id.get(key)
        if node_id is None:
            node_id = str(uuid.uuid4())

        try:
            source = module.code_for_node(node)
        except Exception:
            source = ""

        span = Span(
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
        )
        name = _get_node_name(node)
        parent_node = stack[-1] if stack else None
        mutable = MutableNode(
            node_id=node_id,
            type=node_type,
            name=name,
            source=source,
            span=span,
            parent=parent_node,
            children=[],
        )
        node_to_mutable[id(node)] = mutable
        stack.append(mutable)

        for child in node.children:
            visit(child)

        stack.pop()
        if parent_node is not None:
            parent_node.children.append(mutable)

    visit(module)

    root = node_to_mutable.get(id(module))
    if root is None:
        span = Span(1, 0, 1, 0)
        key = (1, 0, 1, 0, "Module")
        root_id = exact_key_to_id.get(key)
        if root_id is None:
            root_id = str(uuid.uuid4())
        try:
            source = module.code
        except Exception:
            source = ""
        root = MutableNode(
            node_id=root_id,
            type="Module",
            name=None,
            source=source,
            span=span,
            parent=None,
            children=[],
        )
        node_to_mutable[id(module)] = root
        for child in module.children:
            if id(child) in node_to_mutable:
                child_m = node_to_mutable[id(child)]
                child_m.parent = root
                root.children.append(child_m)

    mutable_node_map: Dict[str, MutableNode] = {}

    def collect(n: MutableNode) -> None:
        mutable_node_map[n.node_id] = n
        for ch in n.children:
            collect(ch)

    collect(root)
    return MutableTree(root=root, node_map=mutable_node_map)
