"""
JsonLinesFileHandler — FileHandler for .jsonl, .ndjson files (C-019).

Root-level: lines Node; each line is a scalar Block (raw text).
No JSON parsing at the root level — lines are opaque text.
Drill-in: caller supplies integer line index as node_ref; that line
is then parsed as a standalone JSON document.
JSON parse errors on drill-in return FILE_STRUCTURE_ERROR.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    PreviewError,
    file_structure_error,
    input_error,
    INPUT_ERROR_UNKNOWN_NODE_REF,
)
from ..models import Node, NodeKind

# Drill-in delegates JSON parsing to json_handler._json_value_to_node
# (C-019: no duplicate JSON parser; same NodeKind structure as a
# standalone .json file of the same JSON value type).
from .json_handler import _json_value_to_node

logger = logging.getLogger(__name__)


class JsonLinesFileHandler(FileHandler):
    """
    FileHandler for JSON Lines files (.jsonl, .ndjson) (C-019).

    Root NodeKind: lines. Each line is a scalar block (raw text, not parsed).
    Drill-in: node_ref is a zero-based integer line index; that line is
    parsed as a JSON document and its root NodeKind follows JSON value type.
    FILE_STRUCTURE_ERROR returned for individual invalid JSON lines on drill-in.

    Attributes:
        supported_extensions: frozenset({'.jsonl', '.ndjson'}).
    """

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports."""
        return frozenset({".jsonl", ".ndjson"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """
        Read file line-by-line without JSON parsing and return a lines root.

        Each line becomes a scalar Block with its raw text as value and
        its zero-based index as node_ref. No JSON content is parsed here.

        Args:
            file_path: Project-relative path to the .jsonl/.ndjson file.
            session: Ignored.

        Returns:
            Lines root Node.
        """
        self._last_file_path = file_path

        def _load_lines() -> list[Node]:
            try:
                text = Path(file_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            return [
                Node(
                    node_kind=NodeKind.SCALAR,
                    node_ref=str(i),
                    attributes={"value": line},
                )
                for i, line in enumerate(text.splitlines())
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
        Parse the addressed line as a standalone JSON document (C-019 drill-in).

        node_ref is a zero-based integer line index string. The line is read
        and parsed as JSON; its root NodeKind follows the JSON value type.
        Out-of-range index returns UNKNOWN_NODE_REF.
        Invalid JSON on that line returns FILE_STRUCTURE_ERROR.

        Args:
            node_ref: str(line_index), zero-based.
            session: Ignored.

        Returns:
            JSON root Node for the line, or PreviewError.
        """
        try:
            idx = int(node_ref)
        except ValueError:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"node_ref {node_ref!r} is not a valid integer.",
                details={"node_ref": node_ref},
            )
        fp = getattr(self, "_last_file_path", None)
        if fp is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                "open_root must be called before resolve_node_ref.",
            )
        try:
            lines = Path(fp).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return file_structure_error(parser="json", message=str(exc))
        if idx < 0 or idx >= len(lines):
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Line index {idx} out of range [0, {len(lines)}).",
                details={"node_ref": node_ref},
            )
        line_text = lines[idx]
        try:
            doc = json.loads(line_text)
        except json.JSONDecodeError as exc:
            return file_structure_error(
                parser="json",
                message=str(exc),
                line_start=idx + 1,
                line_end=idx + 1,
            )
        return _json_value_to_node(doc, "")
