"""
Mutable CST node and tree model for in-place batch edits.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Span:
    """Source span (1-based line, 0-based column)."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass
class MutableNode:
    """
    A single mutable node: type, optional name, parent, children, span, source.

    Identity is the stable node_id (UUID). Source is the full source fragment
    for this node (e.g. for FunctionDef, the entire "def ..." block).
    """

    node_id: str
    type: str
    source: str
    span: Span
    name: Optional[str] = None
    parent: Optional[MutableNode] = field(default=None, repr=False)
    children: List[MutableNode] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure children list is mutable."""
        if not isinstance(self.children, list):
            self.children = list(self.children)


@dataclass
class MutableTree:
    """
    Mutable tree: root node and node_id -> node map for O(1) resolution.
    """

    root: MutableNode
    node_map: Dict[str, MutableNode] = field(default_factory=dict)

    def get_node(self, node_id: str) -> Optional[MutableNode]:
        """Resolve node by id."""
        return self.node_map.get(node_id)
