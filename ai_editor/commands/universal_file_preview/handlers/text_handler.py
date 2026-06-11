"""
TextFileHandler — FileHandler for .md, .txt, .rst, .adoc files (C-017).

Root NodeKind is 'lines'. Each child line is a 'scalar' Block with
its zero-based index as node_ref. No external tree infrastructure.
Text files are never structurally invalid (empty files are valid).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import PreviewError, input_error, INPUT_ERROR_UNKNOWN_NODE_REF
from ..models import Node, NodeKind

logger = logging.getLogger(__name__)


class TextFileHandler(FileHandler):
    """
    FileHandler for text files (.md, .txt, .rst, .adoc) (C-017).

    Root NodeKind: lines.
    Children: scalar Nodes, one per line.
    node_ref: zero-based integer line index (serialised as str).
    Lazy materialisation: reads only lines needed by the request.
    No FILE_STRUCTURE_ERROR: any readable file is accepted.

    Attributes:
        supported_extensions: Frozenset of .md, .txt, .rst, .adoc.
    """

    def __init__(self) -> None:
        """Initialise TextFileHandler state."""
        self._last_file_path: str | None = None

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports."""
        return frozenset({".md", ".txt", ".rst", ".adoc"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """
        Read the text file and return a lines root Node.

        Root block set is the ordered sequence of all text lines.
        Each line is a scalar Node with node_ref == str(line_index).
        Lazy: reads line list once on first children access.

        Args:
            file_path: Project-relative path to the file.
            session: Ignored for text files.

        Returns:
            Lines root Node.
        """
        self._last_file_path = file_path

        def _load_lines() -> list[Node]:
            try:
                text = Path(file_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            raw_lines = text.splitlines()
            return [
                Node(
                    node_kind=NodeKind.SCALAR,
                    node_ref=str(i),
                    attributes={"value": line},
                )
                for i, line in enumerate(raw_lines)
            ]

        return Node(
            node_kind=NodeKind.LINES,
            node_ref="",
            _children_loader=_load_lines,
        )

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a zero-based integer line index to the corresponding line Node.

        node_ref must be a string representation of a non-negative integer
        in [0, total_line_count). Out-of-range returns UNKNOWN_NODE_REF.

        Args:
            node_ref: str(line_index), zero-based.
            session: Ignored for text files.

        Returns:
            Scalar Node for the addressed line, or PreviewError.
        """
        try:
            idx = int(node_ref)
        except ValueError:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"node_ref {node_ref!r} is not a valid integer line index.",
                details={"node_ref": node_ref},
            )
        fp = self._last_file_path
        if fp is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                "open_root must be called before resolve_node_ref "
                "(TextFileHandler needs the file path).",
                details={"node_ref": node_ref},
            )
        root_result = self.open_root(fp, session)
        if isinstance(root_result, PreviewError):
            return root_result
        lines = root_result.children
        if idx < 0 or idx >= len(lines):
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Line index {idx} out of range [0, {len(lines)}).",
                details={"node_ref": node_ref, "total_lines": len(lines)},
            )
        line_no = idx + 1
        line_node = lines[idx]
        attrs = dict(line_node.attributes or {})
        attrs["start_line"] = str(line_no)
        attrs["end_line"] = str(line_no)
        return Node(
            node_kind=line_node.node_kind,
            node_ref=line_node.node_ref,
            attributes=attrs,
        )
