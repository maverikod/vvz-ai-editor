"""
JsonFileHandler — FileHandler for .json files (C-018).

Root NodeKind depends on the top-level JSON value:
  dict   -> mapping
  list   -> sequence
  scalar -> scalar
Identifier source: node_id from list_json_blocks OR JSON Pointer string.
Lazy materialisation: only root and requested children are produced.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ....core.json_tree.tree_builder import build_tree_from_data

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from ..invalid_preview import invalid_source_node
from ..models import Node, NodeKind

logger = logging.getLogger(__name__)


def _source_line_count(raw: str) -> int:
    if not raw:
        return 0
    return raw.count("\n") + (1 if not raw.endswith("\n") else 0)


def _line_for_json_pointer(lines: list[str], pointer: str) -> int | None:
    if not lines:
        return None
    if pointer == "":
        for i, line in enumerate(lines, start=1):
            if line.strip():
                return i
        return 1
    parts = [
        p.replace("~1", "/").replace("~0", "~") for p in pointer.strip("/").split("/")
    ]
    if not parts:
        return 1
    last = parts[-1]
    key_pat = re.compile(rf'["\']{re.escape(last)}["\']\s*:')
    for i, line in enumerate(lines, start=1):
        if key_pat.search(line):
            return i
    if last.isdigit():
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if (
                stripped in ("{", "[")
                or stripped.endswith("{")
                or stripped.endswith("[")
            ):
                continue
            if stripped.startswith("{") or stripped.startswith("["):
                return i
    return None


def _pointer_in_subtree(ptr: str, root: str) -> bool:
    if root == "":
        return True
    if ptr == root:
        return True
    return ptr.startswith(root + "/")


def _line_span_for_pointer(
    metadata_map: dict[str, Any],
    source_lines: list[str],
    pointer: str,
) -> tuple[int, int] | None:
    lines: list[int] = []
    for meta in metadata_map.values():
        ptr = meta.json_pointer
        if not _pointer_in_subtree(ptr, pointer):
            continue
        start = getattr(meta, "start_line", None)
        if start is None:
            start = _line_for_json_pointer(source_lines, ptr)
        if start is not None:
            lines.append(start)
    if not lines:
        sole = _line_for_json_pointer(source_lines, pointer)
        if sole is None:
            return None
        return (sole, sole)
    return (min(lines), max(lines))


def _annotated_lines_in_range(
    source_lines: list[str],
    metadata_map: dict[str, Any],
    *,
    start_line: int,
    end_line: int,
    root_pointer: str,
) -> str:
    by_line: defaultdict[int, list[str]] = defaultdict(list)
    for meta in metadata_map.values():
        ptr = meta.json_pointer
        if not _pointer_in_subtree(ptr, root_pointer):
            continue
        line = getattr(meta, "start_line", None)
        if line is None:
            line = _line_for_json_pointer(source_lines, ptr)
        if line is None or line < start_line or line > end_line:
            continue
        by_line[line].append(ptr)
    line_to_ref = {line: max(refs, key=len) for line, refs in by_line.items()}
    out_lines: list[str] = []
    for i in range(start_line, end_line + 1):
        if i < 1 or i > len(source_lines):
            continue
        ref = line_to_ref.get(i)
        out_lines.append(
            f"[{ref}] {source_lines[i - 1]}" if ref else source_lines[i - 1]
        )
    return "\n".join(out_lines)


def _annotated_full_text_for_pointer(
    raw: str,
    metadata_map: dict[str, Any],
    budget: PreviewBudget,
    pointer: str,
) -> str | None:
    """Return node-scoped annotated source when span <= ``full_text_max_lines``."""
    if budget.full_text_max_lines <= 0:
        return None
    source_lines = raw.splitlines()
    span = _line_span_for_pointer(metadata_map, source_lines, pointer)
    if span is None:
        return None
    start_line, end_line = span
    if end_line - start_line + 1 > budget.full_text_max_lines:
        return None
    return _annotated_lines_in_range(
        source_lines,
        metadata_map,
        start_line=start_line,
        end_line=end_line,
        root_pointer=pointer,
    )


def _annotated_full_text(
    raw: str,
    metadata_map: dict[str, Any],
    budget: PreviewBudget,
) -> str | None:
    """Return source with JSON Pointer prefixes when file < ``full_text_max_lines``."""
    if budget.full_text_max_lines <= 0:
        return None
    if _source_line_count(raw) >= budget.full_text_max_lines:
        return None
    return _annotated_full_text_for_pointer(raw, metadata_map, budget, "")


class JsonFileHandler(FileHandler):
    """
    FileHandler for JSON files (.json) (C-018).

        Root NodeKind: mapping (object), sequence (array), or scalar.
        Identifier source: JSON Pointer (RFC 6901) or opaque node_id from
        list_json_blocks (same index as TreeSession metadata).
        Lazy materialisation: only root and needed children are produced.
    FILE_STRUCTURE_ERROR on invalid JSON with parser name 'json'.

    Attributes:
        supported_extensions: frozenset({'.json'}).
    """

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """
        Parse the JSON file and return the root Node.

        Root NodeKind is mapping, sequence, or scalar depending on the
        top-level JSON value type. On invalid JSON returns FILE_STRUCTURE_ERROR.

        Args:
            file_path: Project-relative path to the .json file.
            session: Existing JSON TreeSession or None.

        Returns:
            Root Node or PreviewError.
        """
        try:
            self._last_file_path = file_path
            self._last_budget = budget
            if session is not None:
                doc = session  # assume session is the parsed object
                raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
            else:
                raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
                doc = json.loads(raw)
            self._doc = doc
            self._last_raw = raw
            tree = build_tree_from_data(
                str(Path(file_path).resolve()),
                doc,
                register=False,
            )
            # Same node_id ⇄ JSON Pointer mapping as list_json_blocks / JSONTree.
            self._pointer_by_node_id = dict(tree.pointer_by_id)
            self._metadata_map = tree.metadata_map
            if budget is not None:
                annotated = _annotated_full_text(raw, tree.metadata_map, budget)
                if annotated is not None:
                    return Node(
                        node_kind=NodeKind.SCALAR,
                        node_ref="",
                        attributes={"text": annotated, "full_text": True},
                    )
            return _json_value_to_node(doc, "")
        except json.JSONDecodeError as exc:
            return invalid_source_node(file_path, exc)
        except Exception as exc:
            return invalid_source_node(file_path, exc)

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a JSON Pointer or node_id to the addressed JSON Node.

        Accepts either a JSON Pointer string (RFC 6901: '', '/foo', '/a/0/b')
        or an opaque node_id string from list_json_blocks (treated as JSON
        Pointer if it starts with '/', else looked up in _doc index).

        Args:
            node_ref: JSON Pointer or node_id string.
            session: JSON TreeSession or None.

        Returns:
            Resolved Node or PreviewError(UNKNOWN_NODE_REF).
        """
        doc = getattr(self, "_doc", None)
        if doc is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                "open_root must be called before resolve_node_ref.",
                details={"node_ref": node_ref},
            )
        _budget = getattr(self, "_last_budget", None)
        _raw = getattr(self, "_last_raw", None)
        _meta_map = getattr(self, "_metadata_map", None)
        if node_ref == "" or node_ref.startswith("/"):
            result = _resolve_json_pointer(doc, node_ref)
            if result is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"JSON Pointer {node_ref!r} does not exist in document.",
                    details={"node_ref": node_ref},
                )
            value, canon_pointer = result
        else:
            ptr_map_raw = getattr(self, "_pointer_by_node_id", None)
            pointer_map: dict[str, str] = dict(ptr_map_raw) if ptr_map_raw else {}
            pointer_opt = pointer_map.get(node_ref)
            if pointer_opt is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Unknown node_ref {node_ref!r}: not a JSON Pointer in this document "
                    "and not a listed node_id.",
                    details={"node_ref": node_ref},
                )
            result = _resolve_json_pointer(doc, pointer_opt)
            if result is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"node_id {node_ref!r} mapped to stale pointer {pointer_opt!r}; "
                    "re-open the preview.",
                    details={"node_ref": node_ref},
                )
            value, canon_pointer = result
        if _budget is not None and _raw is not None and _meta_map is not None:
            annotated = _annotated_full_text_for_pointer(
                _raw, _meta_map, _budget, canon_pointer
            )
            if annotated is not None:
                return Node(
                    node_kind=NodeKind.SCALAR,
                    node_ref=node_ref,
                    attributes={"text": annotated, "full_text": True},
                )
        return _json_value_to_node(value, canon_pointer)


def _json_value_to_node(value: Any, pointer: str) -> Node:
    """Convert a JSON value to a preview Node with JSON Pointer as node_ref."""
    if isinstance(value, dict):

        def _load_mapping() -> list[Node]:
            return [
                _json_pair_to_node(k, v, f"{pointer}/{k}") for k, v in value.items()
            ]

        return Node(
            node_kind=NodeKind.MAPPING,
            node_ref=pointer,
            _children_loader=_load_mapping,
        )
    if isinstance(value, list):

        def _load_seq() -> list[Node]:
            return [
                _json_value_to_node(v, f"{pointer}/{i}") for i, v in enumerate(value)
            ]

        return Node(
            node_kind=NodeKind.SEQUENCE,
            node_ref=pointer,
            _children_loader=_load_seq,
        )
    return Node(
        node_kind=NodeKind.SCALAR,
        node_ref=pointer,
        attributes={"value": str(value)},
    )


def _json_pair_to_node(key: str, value: Any, pointer: str) -> Node:
    """One mapping key-value pair as a single Block Node."""
    return Node(
        node_kind=NodeKind.MAPPING,
        node_ref=pointer,
        name=key,
        attributes={"value_kind": type(value).__name__},
    )


def _resolve_json_pointer(doc: Any, pointer: str) -> tuple[Any, str] | None:
    """Traverse doc following RFC-6901 pointer; return (value, pointer) or None."""
    if pointer == "":
        return (doc, "")
    if not pointer.startswith("/"):
        return None  # invalid pointer (non-RFC-6901 strings handled as None)
    parts = pointer[1:].split("/")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    current = doc
    path = ""
    for part in parts:
        path = f"{path}/{part}"
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return (current, path)
