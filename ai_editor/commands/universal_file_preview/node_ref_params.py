"""
Optional ``node_ref`` normalization for universal_file_preview.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


def normalize_optional_node_ref(node_ref: str | None) -> str | None:
    """Treat blank ``node_ref`` as absent (focus = file root from ``open_root``)."""
    if node_ref is None:
        return None
    if not str(node_ref).strip():
        return None
    return str(node_ref)
