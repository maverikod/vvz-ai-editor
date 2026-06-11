"""
ai_editor.tree — Marked-tree unification package.

Public API:
    MarkerContract     - Three-operation protocol (mark, parse, unmark) [C-001]
    NodeId             - Per-file integer short_id handle                 [C-002]
    TreeNodeUuid       - MAP-section canonical UUID4 identity             [C-024]
    AddressableBlock   - Per-format minimal addressable unit              [C-005]
    Format             - Enumeration of supported file formats
    UnknownNodeIdError - Raised when a short_id is not recognised         [C-002]
    validate_short_id  - Validate and coerce int to NodeId

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ai_editor.tree.contracts import (
    AddressableBlock,
    Format,
    MarkerContract,
    NodeId,
    TreeNodeUuid,
    UnknownNodeIdError,
    validate_short_id,
)

__all__ = [
    "AddressableBlock",
    "Format",
    "MarkerContract",
    "NodeId",
    "TreeNodeUuid",
    "UnknownNodeIdError",
    "validate_short_id",
]
