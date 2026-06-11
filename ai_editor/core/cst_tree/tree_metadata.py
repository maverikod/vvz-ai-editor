"""
CST tree metadata utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import libcst as cst

from .models import CSTTree, ROOT_NODE_ID_SENTINEL, TreeNodeMetadata
from .tree_builder import get_tree


def get_node_by_stable_id(session: Any, stable_id: str) -> Optional[cst.CSTNode]:
    """
    Resolve ``stable_id`` to the LibCST node from a :class:`CSTTree` session.

    When ``session`` is not a :class:`CSTTree` (e.g. a bare :class:`cst.Module`
    from :func:`libcst.parse_module`), returns ``None``.
    """
    if not isinstance(session, CSTTree):
        return None
    meta = session.find_by_stable_id(stable_id)
    if meta is None:
        return None
    return session.node_map.get(meta.node_id)


def _resolve_node_id(tree: Optional[CSTTree], node_id: str) -> str:
    """
    Resolve ``__root__``, span ``node_id`` aliases, or ``stable_id`` to current span id.

    Preview and edit pass ``stable_id`` (persistent). Internal ``node_id`` may change
    after each libcst rebuild; ``node_id_aliases`` maps retired span ids forward.
    """
    if node_id == ROOT_NODE_ID_SENTINEL and tree and tree.root_node_id:
        return tree.root_node_id
    if not tree:
        return node_id

    resolved = node_id
    if tree.node_id_aliases:
        seen: set[str] = set()
        while resolved in tree.node_id_aliases and resolved not in seen:
            seen.add(resolved)
            resolved = tree.node_id_aliases[resolved]

    if resolved in tree.metadata_map:
        return resolved

    meta = tree.find_by_stable_id(resolved)
    if meta is not None:
        return meta.node_id

    return resolved


def get_node_metadata(
    tree_id: str, node_id: str, include_code: bool = False
) -> Optional[TreeNodeMetadata]:
    """
    Get metadata for a node.

    Accepts either node_id or stable_id - both are resolved transparently.

    Args:
        tree_id: Tree ID
        node_id: Node ID or stable_id
        include_code: Whether to include code snippet

    Returns:
        TreeNodeMetadata or None if not found
    """
    tree = get_tree(tree_id)
    if not tree:
        return None
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    if include_code:
        node = tree.node_map.get(node_id)
        if node:
            code: Optional[str] = None
            try:
                code = tree.module.code_for_node(node)
            except Exception:
                try:
                    source_lines = tree.module.code.splitlines(keepends=True)
                    start = (metadata.start_line or 1) - 1
                    end = metadata.end_line or len(source_lines)
                    code = "".join(source_lines[start:end])
                except Exception:
                    code = None
            if code is not None:
                return TreeNodeMetadata(
                    node_id=metadata.node_id,
                    stable_id=metadata.stable_id,
                    type=metadata.type,
                    kind=metadata.kind,
                    name=metadata.name,
                    qualname=metadata.qualname,
                    start_line=metadata.start_line,
                    start_col=metadata.start_col,
                    end_line=metadata.end_line,
                    end_col=metadata.end_col,
                    children_count=metadata.children_count,
                    children_ids=metadata.children_ids,
                    parent_id=metadata.parent_id,
                    code=code,
                )

    return metadata


def get_node_children(
    tree_id: str, node_id: str, include_code: bool = False
) -> List[TreeNodeMetadata]:
    """
    Get children of a node.

    Accepts either node_id or stable_id.

    Args:
        tree_id: Tree ID
        node_id: Node ID or stable_id
        include_code: Whether to include code snippets

    Returns:
        List of TreeNodeMetadata for children
    """
    tree = get_tree(tree_id)
    if not tree:
        return []
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return []

    children = []
    for child_id in metadata.children_ids:
        child_meta = get_node_metadata(tree_id, child_id, include_code=include_code)
        if child_meta:
            children.append(child_meta)
    return children


def get_node_descendants(
    tree_id: str,
    node_id: str,
    max_depth: int = 1,
    include_code: bool = False,
) -> List[Tuple[TreeNodeMetadata, int]]:
    """
    Get descendants of a node up to max_depth.

    Accepts either node_id or stable_id.

    Args:
        tree_id: Tree ID
        node_id: Node ID or stable_id
        max_depth: Maximum depth (0 = unlimited)
        include_code: Whether to include code snippets

    Returns:
        List of (TreeNodeMetadata, depth) tuples
    """
    tree = get_tree(tree_id)
    if not tree:
        return []
    node_id = _resolve_node_id(tree, node_id)

    result: List[Tuple[TreeNodeMetadata, int]] = []

    def _collect(nid: str, depth: int) -> None:
        if max_depth > 0 and depth > max_depth:
            return
        meta = get_node_metadata(tree_id, nid, include_code=include_code)
        if not meta:
            return
        result.append((meta, depth))
        for child_id in meta.children_ids:
            _collect(child_id, depth + 1)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return []
    for child_id in metadata.children_ids:
        _collect(child_id, 1)
    return result


def get_node_parent(tree_id: str, node_id: str) -> Optional[TreeNodeMetadata]:
    """
    Get parent of a node.

    Accepts either node_id or stable_id.

    Args:
        tree_id: Tree ID
        node_id: Node ID or stable_id

    Returns:
        TreeNodeMetadata of parent or None
    """
    tree = get_tree(tree_id)
    if not tree:
        return None
    node_id = _resolve_node_id(tree, node_id)

    parent_id = tree.parent_map.get(node_id)
    if not parent_id:
        return None
    return get_node_metadata(tree_id, parent_id)
