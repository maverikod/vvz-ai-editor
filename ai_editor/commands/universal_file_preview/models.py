"""
Domain models for universal_file_preview.

Defines the closed NodeKind enumeration (C-004), the Block (C-005),
the Node (uniform in-memory representation), and NavigationResult
(output of the navigation procedure).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class NodeKind(str, enum.Enum):
    """
    Closed enumeration of node classifications (C-004).

    Exactly five values. The kind is intrinsic to the node;
    it does not depend on the parent or on the file type.
    """

    SCALAR = "scalar"
    LINES = "lines"
    MAPPING = "mapping"
    SEQUENCE = "sequence"
    TREE_NODE = "tree_node"


@dataclass
class Node:
    """
    Uniform in-memory representation of any file node.

    Produced by a FileHandler (C-003); consumed by NavigationProcedure (C-006).

    Attributes:
        node_kind: Classification of this node (C-004).
        node_ref: StableIdentifier string (opaque to dispatcher).
        type_label: Optional type label (e.g. 'FunctionDef' for tree_node).
        name: Optional name carried by the node.
        attributes: Optional compact metadata dict (e.g. params, returns).
        _children_loader: Callable that lazily loads children; None if already loaded.
        _children: Loaded children list; empty list means no children.
    """

    node_kind: NodeKind
    node_ref: str
    is_invalid: bool = False
    type_label: str | None = None
    name: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    _children_loader: Any = field(default=None, repr=False, compare=False)
    _children: list[Node] = field(default_factory=list, repr=False, compare=False)

    @property
    def children(self) -> list[Node]:
        """Return children lazily, calling _children_loader on first access."""
        if self._children_loader is not None:
            self._children = self._children_loader()
            self._children_loader = None
        return self._children


@dataclass
class Block:
    """
    Self-contained unit of a focus node's ordered block set (C-005).

    A Block is exactly one element of the block set. It carries its own
    NodeKind, node_ref, and rendered summary (after BlockHandler runs).
    For a mapping focus, a Block is one complete key-value pair.

    Attributes:
        node_kind: NodeKind of this block.
        node_ref: StableIdentifier for drill-down.
        summary: Rendered compact summary from BlockHandler.
        text: Optional pre-rendered structured text from PythonNodeRenderer (C-022).
              When present, callers should use this instead of generic summary fields.
    """

    node_kind: NodeKind
    node_ref: str
    summary: dict[str, Any] = field(default_factory=dict)
    text: str | None = None


@dataclass
class NavigationResult:
    """
    Output of the NavigationProcedure (C-006) for one request.

    Attributes:
        focus_node: The focus Node (file root or resolved node_ref).
        total_blocks: Total count of blocks in the focus node's block set.
        selected_blocks: Ordered list of rendered Blocks after selector applied.
        tree_id: tree_id of an internally-created TreeSession, or None.
    """

    focus_node: Node
    total_blocks: int
    selected_blocks: list[Block]
    tree_id: str | None = None
    short_id_refs: bool = False
