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

    Supports two search modes:
    1. Simple search: by node_type, name, qualname, line range; or by query
      (when query is provided with search_type=simple, it is evaluated as xpath).
    2. XPath-like search: using CSTQuery selector syntax

    Args:
        tree_id: Tree ID
        query: CSTQuery selector string (for xpath; with simple, if set, same as xpath)
        search_type: "simple" or "xpath" (default: "xpath")
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
            matches = _find_nodes_simple(tree, node_type, name, qualname, start_line, end_line)
    else:
        raise ValueError(
            f"Invalid search_type: {search_type}. Must be 'simple' or 'xpath'"
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
