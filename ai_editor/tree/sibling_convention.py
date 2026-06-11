"""
Sibling storage convention for TreeFile (C-003) and SourceFile (C-004).

Co-located placement: TreeFile path is ``<source_name>.tree`` in the same directory
as the SourceFile. On-disk TreeFile layout uses three sections (CHECKSUMS, MAP, TREE)
written by TreeBuilder; this module provides the path formula only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

TREE_FILE_SUFFIX: str = ".tree"
SOURCE_FILE_INVARIANT: str = (
    "The tree system must never modify a SourceFile. "
    "SourceFile is the source of truth outside any active edit session."
)


def sibling_tree_path(source_abs: Path) -> Path:
    if not source_abs.name:
        raise ValueError(
            f"source_abs must be a file path with a name, got: {source_abs!r}"
        )
    return source_abs.parent / (source_abs.name + TREE_FILE_SUFFIX)


__all__ = ["TREE_FILE_SUFFIX", "SOURCE_FILE_INVARIANT", "sibling_tree_path"]
