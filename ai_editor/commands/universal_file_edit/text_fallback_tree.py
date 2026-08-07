"""
Paragraph/line tree for the parse-error fallback of ``universal_file_edit``.

The fallback is entered ONLY when the source format genuinely fails to parse.
In that mode the draft is still a TREE, not an unstructured buffer: a document
root holding paragraph and blank blocks, each block holding its lines. Every
line of the draft belongs to exactly one line node, so a line number is a real
node address rather than an offset into a raw slice.

Addresses resolve against this tree and nothing else:

- ``node_ref: ""``      -> the document root (the whole document)
- ``node_ref: "<int>"`` -> the i-th line node, zero-based
- ``start_line``/``end_line`` -> the contiguous run of line nodes they name

An address the tree cannot resolve is refused by construction with its
documented stable error code; it never degrades into a buffer slice.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional, Sequence

DOCUMENT = "document"
PARAGRAPH = "paragraph"
BLANK = "blank"
LINE = "line"

ROOT_NODE_REF = ""


@dataclasses.dataclass(frozen=True)
class FallbackNode:
    """One node of the fallback tree, spanning 1-based inclusive source lines."""

    kind: str
    start_line: int
    end_line: int
    node_ref: str = ROOT_NODE_REF

    @property
    def line_span(self) -> tuple[int, int]:
        return self.start_line, self.end_line


class FallbackDocumentTree:
    """The draft of a parse-error fallback session, modelled as a tree.

    ``blocks`` are the root's children in source order: a ``paragraph`` block is
    a run of consecutive non-blank lines, a ``blank`` block a run of consecutive
    blank ones. ``line_nodes`` are the leaves, one per source line and in source
    order, so ``line_nodes[i]`` is the node addressed by the zero-based
    ``node_ref`` ``str(i)`` and covers source line ``i + 1``.
    """

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines: List[str] = list(lines)
        self.line_nodes: List[FallbackNode] = [
            FallbackNode(kind=LINE, start_line=i + 1, end_line=i + 1, node_ref=str(i))
            for i in range(len(self._lines))
        ]
        self.blocks: List[FallbackNode] = self._build_blocks()
        self.root = FallbackNode(
            kind=DOCUMENT,
            start_line=1,
            end_line=len(self._lines),
            node_ref=ROOT_NODE_REF,
        )

    @classmethod
    def from_source(cls, source: str) -> "FallbackDocumentTree":
        """Build the tree from raw draft text, keeping line endings intact."""
        return cls(source.splitlines(keepends=True))

    def _build_blocks(self) -> List[FallbackNode]:
        """Group the lines into alternating paragraph and blank blocks."""
        blocks: List[FallbackNode] = []
        start: Optional[int] = None
        current = ""
        for index, raw in enumerate(self._lines):
            kind = BLANK if raw.strip() == "" else PARAGRAPH
            if start is None:
                start, current = index + 1, kind
                continue
            if kind != current:
                blocks.append(
                    FallbackNode(kind=current, start_line=start, end_line=index)
                )
                start, current = index + 1, kind
        if start is not None:
            blocks.append(
                FallbackNode(kind=current, start_line=start, end_line=len(self._lines))
            )
        return blocks

    @property
    def line_count(self) -> int:
        """Number of line nodes, i.e. the root's line extent."""
        return len(self._lines)

    def line_node(self, index: int) -> Optional[FallbackNode]:
        """The line node at a zero-based index, or None when out of the tree."""
        if index < 0 or index >= len(self.line_nodes):
            return None
        return self.line_nodes[index]

    def covers(self, start_line: int, end_line: int) -> bool:
        """True when the 1-based inclusive range names only real line nodes."""
        if start_line < 1 or end_line < start_line:
            return False
        return end_line <= self.line_count

    def accepts_insert_at(self, line: int) -> bool:
        """True when a new node may be attached before ``line``.

        ``line_count + 1`` is the root's tail boundary: appending at end of
        document is a position in the tree, not a line node of its own.
        """
        return 1 <= line <= self.line_count + 1

    def block_at_line(self, line: int) -> Optional[FallbackNode]:
        """The paragraph or blank block owning a 1-based source line."""
        for block in self.blocks:
            if block.start_line <= line <= block.end_line:
                return block
        return None
