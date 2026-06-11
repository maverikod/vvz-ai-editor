"""
Statement-level ancestor walk for CST trees (cst_get_node_at_line).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional, Tuple

from .models import CSTTree

# LibCST CSTNode type names — first match walking from leaf toward root.
STATEMENT_TYPES = frozenset(
    {
        "Assign",
        "AugAssign",
        "AnnAssign",
        "If",
        "For",
        "While",
        "Try",
        "With",
        "Return",
        "Raise",
        "Assert",
        "Delete",
        "Expr",
        "FunctionDef",
        "AsyncFunctionDef",
        "ClassDef",
        "Import",
        "ImportFrom",
        "Global",
        "Nonlocal",
        "Pass",
        "Break",
        "Continue",
    }
)


def find_statement_ancestor_node_id(
    tree: CSTTree, leaf_node_id: str
) -> Tuple[str, bool]:
    """Walk parent chain from leaf; return first statement-level node id.

    If none is found, return the nearest ancestor with a non-empty ``name``,
    or the leaf id, and set fallback to True.

    Args:
        tree: Loaded CST tree.
        leaf_node_id: Deepest node at the requested line.

    Returns:
        (statement_node_id, fallback) where fallback is True when no
        ``STATEMENT_TYPES`` ancestor was found.
    """
    chain: list[str] = []
    current_id: Optional[str] = leaf_node_id
    while current_id:
        meta = tree.metadata_map.get(current_id)
        if not meta:
            break
        chain.append(current_id)
        if meta.type in STATEMENT_TYPES:
            return current_id, False
        current_id = meta.parent_id

    for nid in chain:
        m = tree.metadata_map.get(nid)
        if m and m.name:
            return nid, True
    return leaf_node_id, True


def annotate_statement_source(source: str, start_line: int, max_lines: int = 60) -> str:
    """Prefix each source line with ``<abs_line>\\t``; optionally truncate middle.

    Args:
        source: Raw statement source (no line-number prefixes).
        start_line: 1-based line number of the first line of ``source``.
        max_lines: Maximum lines in the output; middle may be replaced by a marker.

    Returns:
        Annotated text joined with newlines.
    """
    lines = source.splitlines()
    annotated = [f"{start_line + i}\t{line}" for i, line in enumerate(lines)]
    if len(annotated) <= max_lines:
        return "\n".join(annotated)

    # Reserve one line for the omission marker.
    remaining = max_lines - 1
    half = remaining // 2
    head = annotated[:half]
    tail = annotated[-half:]
    omitted = len(annotated) - len(head) - len(tail)
    middle = [f"... ({omitted} lines omitted) ..."]
    return "\n".join(head + middle + tail)
