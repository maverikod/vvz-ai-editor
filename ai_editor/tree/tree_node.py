"""In-memory tree node produced by FormatHandler.parse_content (C-009).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ai_editor.tree.contracts import NodeId


@dataclass
class TreeNode:
    short_id: NodeId
    kind: str
    content: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    parent_short_id: Optional[NodeId] = None

    def __post_init__(self) -> None:
        """Validate short_id and kind invariants (C-002, C-009)."""
        if not isinstance(self.short_id, int):
            raise TypeError("TreeNode.short_id must be int")
        if self.short_id < 1:
            raise ValueError("TreeNode.short_id must be a positive integer")
        if not self.kind:
            raise ValueError("TreeNode.kind must be a non-empty string")
        if self.parent_short_id is not None:
            if not isinstance(self.parent_short_id, int):
                raise TypeError("TreeNode.parent_short_id must be int or None")
            if self.parent_short_id < 1:
                raise ValueError(
                    "TreeNode.parent_short_id must be a positive integer when set"
                )
