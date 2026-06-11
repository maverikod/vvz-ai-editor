"""
Helpers for previewing syntactically invalid source files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from .models import Node, NodeKind


def invalid_source_node(file_path: str, exc: BaseException) -> Node:
    """Build a scalar root node carrying raw source and a parse-error description."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return Node(
        node_kind=NodeKind.SCALAR,
        node_ref="",
        is_invalid=True,
        attributes={
            "text": source,
            "full_text": True,
            "parse_error": str(exc),
        },
    )
