"""
CST tree finder - find nodes in tree using simple or XPath-like queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import logging

from typing import List, Optional


from ...cst_query import query_source

from .models import CSTTree, TreeNodeMetadata

from .node_id_markers import build_exact_key_to_id_from_metadata

from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def find_nodes(
    tree_id: str,
    query: Optional[str] = None,
    search_type: str = "xpath",
    node_type: Optional[str] = None,
    name: Optional[str] = None,
    qualname: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    include_code: bool = False,
) -> List[TreeNodeMetadata]:
    """
    Find nodes in tree.

    Supports three search modes:
    1. Simple search: by node_type, name, qualname, line range; or by query
      (when query is provided with search_type=simple, it is evaluated as xpath).
    2. XPath-like search: using CSTQuery selector syntax
    3. Text search: substring match in each node's source slice

    Args:
        tree_id: Tree ID
        query: CSTQuery selector (xpath/text) or substring (text)
        search_type: "simple", "xpath" (default), or "text"
        node_type: Node type filter (for simple search)
        name: Node name filter (for simple search)
        qualname: Qualified name filter (for simple search)
        start_line: Start line filter (for simple search)
        end_line: End line filter (for simple search)
        include_code: If True, populate the ``code`` field on each returned
            TreeNodeMetadata by calling ``tree.module.code_for_node``.

    Returns:
        List of TreeNodeMetadata for matching nodes
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    if search_type == "xpath":
        if not query:
            raise ValueError("query parameter required for xpath search")
        matches = _find_nodes_xpath(tree, query)
    elif search_type == "simple":
        if query and query.strip():
            matches = _find_nodes_xpath(tree, query)
        else:
            matches = _find_nodes_simple(
                tree, node_type, name, qualname, start_line, end_line
            )
    elif search_type == "text":
        if not query:
            raise ValueError("query parameter required for text search")
        matches = _find_nodes_text(tree, query, start_line, end_line)
    else:
        raise ValueError(
            f"Invalid search_type: {search_type}. Must be 'simple', 'xpath', or 'text'"
        )

    if not include_code:
        return matches

    # Enrich matches with source code of each node
    enriched: List[TreeNodeMetadata] = []
    for meta in matches:
        node = tree.node_map.get(meta.node_id)
        if node is not None:
            try:
                code = tree.module.code_for_node(node)
            except Exception:
                code = None
        else:
            code = None
        if code is not None:
            import dataclasses

            meta = dataclasses.replace(meta, code=code)
        enriched.append(meta)
    return enriched


def _find_nodes_xpath(tree: CSTTree, selector: str) -> List[TreeNodeMetadata]:
    """Find nodes using CSTQuery selector."""
    matches = query_source(
        tree.module.code,
        selector,
        include_code=False,
        node_ids_by_exact_key=build_exact_key_to_id_from_metadata(tree.metadata_map),
    )
    return [
        tree.metadata_map[match.node_id]
        for match in matches
        if match.node_id in tree.metadata_map
    ]


def _find_nodes_simple(
    tree: CSTTree,
    node_type: Optional[str] = None,
    name: Optional[str] = None,
    qualname: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TreeNodeMetadata]:
    """Find nodes using simple filters."""
    result: List[TreeNodeMetadata] = []

    for metadata in tree.metadata_map.values():
        # Apply filters
        if node_type and metadata.type != node_type:
            continue
        if name and metadata.name != name:
            continue
        if qualname and metadata.qualname != qualname:
            continue
        if start_line is not None and metadata.start_line < start_line:
            continue
        if end_line is not None and metadata.end_line > end_line:
            continue

        result.append(metadata)

    return result


def _metadata_source_slice(tree: CSTTree, metadata: TreeNodeMetadata) -> str:
    """Return source text for one metadata node's line span."""
    lines = tree.module.code.splitlines()
    start_idx = max(metadata.start_line - 1, 0)
    end_idx = min(metadata.end_line, len(lines))
    if start_idx >= end_idx:
        return ""
    return "\n".join(lines[start_idx:end_idx])


def _is_strict_ancestor(
    outer: TreeNodeMetadata,
    inner: TreeNodeMetadata,
) -> bool:
    """True when ``outer`` strictly contains ``inner`` by line span."""
    if outer.node_id == inner.node_id:
        return False
    outer_span = outer.end_line - outer.start_line
    inner_span = inner.end_line - inner.start_line
    return (
        outer.start_line <= inner.start_line
        and outer.end_line >= inner.end_line
        and outer_span > inner_span
    )


def _dedupe_most_specific(matches: List[TreeNodeMetadata]) -> List[TreeNodeMetadata]:
    """Keep only nodes that are not strict ancestors of another match."""
    return [
        meta
        for meta in matches
        if not any(
            _is_strict_ancestor(meta, other)
            for other in matches
            if other.node_id != meta.node_id
        )
    ]


def _find_nodes_text(
    tree: CSTTree,
    query: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TreeNodeMetadata]:
    """Find nodes whose source slice contains ``query`` as a substring."""
    raw_matches: List[TreeNodeMetadata] = []
    for metadata in tree.metadata_map.values():
        if start_line is not None and metadata.start_line < start_line:
            continue
        if end_line is not None and metadata.end_line > end_line:
            continue
        node_source = _metadata_source_slice(tree, metadata)
        if query in node_source:
            raw_matches.append(metadata)
    return _dedupe_most_specific(raw_matches)
