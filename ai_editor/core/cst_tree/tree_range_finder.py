"""
CST tree range finder - find node by line range.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .models import TreeNodeMetadata
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def find_node_by_range(
    tree_id: str,
    start_line: int,
    end_line: int,
    prefer_exact: bool = True,
) -> Optional[TreeNodeMetadata]:
    """
    Find node that covers the specified line range.

    Args:
        tree_id: Tree ID
        start_line: Start line (1-based, inclusive)
        end_line: End line (1-based, inclusive)
        prefer_exact: If True, prefer node that exactly matches the range.
                      If False, return smallest node that contains the range.

    Returns:
        TreeNodeMetadata for the node covering the range, or None if not found.

    Algorithm:
    1. Find all nodes that contain the range (start_line <= node.start_line <= end_line <= node.end_line)
    2. If prefer_exact=True, prefer node that exactly matches (node.start_line == start_line && node.end_line == end_line)
    3. Otherwise, return smallest node (by span size) that contains the range
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    if start_line > end_line:
        raise ValueError(
            f"Invalid range: start_line ({start_line}) > end_line ({end_line})"
        )

    # Find all nodes that contain or match the range
    candidates: List[TreeNodeMetadata] = []

    for metadata in tree.metadata_map.values():
        # Node contains the range if:
        # - node.start_line <= start_line AND end_line <= node.end_line
        if metadata.start_line <= start_line and end_line <= metadata.end_line:
            candidates.append(metadata)

    if not candidates:
        return None

    # If prefer_exact, look for exact match first
    if prefer_exact:
        for candidate in candidates:
            if candidate.start_line == start_line and candidate.end_line == end_line:
                return candidate

    # Return smallest node (by span size) that contains the range
    # This gives us the most specific node covering the range
    best = min(
        candidates,
        key=lambda m: (
            (m.end_line - m.start_line),  # Span size (smaller is better)
            m.start_line,  # If same size, prefer earlier
        ),
    )

    return best


def find_nodes_by_range(
    tree_id: str,
    start_line: int,
    end_line: int,
) -> List[TreeNodeMetadata]:
    """
    Find all nodes that intersect with the specified line range.

    Args:
        tree_id: Tree ID
        start_line: Start line (1-based, inclusive)
        end_line: End line (1-based, inclusive)

    Returns:
        List of TreeNodeMetadata for nodes that intersect with the range.

    A node intersects with the range if:
    - node.start_line <= end_line AND node.end_line >= start_line
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    if start_line > end_line:
        raise ValueError(
            f"Invalid range: start_line ({start_line}) > end_line ({end_line})"
        )

    result: List[TreeNodeMetadata] = []

    for metadata in tree.metadata_map.values():
        # Node intersects with range if:
        # - node.start_line <= end_line AND node.end_line >= start_line
        if metadata.start_line <= end_line and metadata.end_line >= start_line:
            result.append(metadata)

    # Sort by start_line, then by end_line
    result.sort(key=lambda m: (m.start_line, m.end_line))

    return result
