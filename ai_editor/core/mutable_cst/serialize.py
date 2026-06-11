"""
Serialize mutable tree to full source code string.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .models import MutableTree


def serialize_to_source(tree: MutableTree) -> str:
    """
    Walk the mutable tree and output full file source.

    For the root (Module), the source is the concatenation of each
    top-level child's source (with newlines). Each child's source
    is the full fragment for that node (e.g. entire class or function).

    Args:
        tree: MutableTree built from LibCST or after edits.

    Returns:
        Full Python source code string.
    """
    parts = [c.source for c in tree.root.children]
    return "\n".join(parts)
