"""
YamlFileHandler — FileHandler for .yaml, .yml files (C-020).

Root NodeKind depends on the top-level YAML value:
  mapping  -> mapping
  sequence -> sequence
  scalar   -> scalar
YAML anchors and aliases are resolved before producing the node tree.
Identifier source:
  YAML tree index (JSON Pointer paths, stable node_id / uuid5 of pointer).
  JSON-pointer-style path traversal when resolving by path string.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from typing import Any

from ....core.yaml_tree.models import YamlTree
from ....core.yaml_tree.resolve import resolve_yaml_node
from ....core.yaml_tree.tree_builder import build_yaml_tree_from_text

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from ..invalid_preview import invalid_source_node
from ..models import Node, NodeKind


def _source_line_count(raw: str) -> int:
    if not raw:
        return 0
    return raw.count("\n") + (1 if not raw.endswith("\n") else 0)


def _line_for_yaml_pointer(lines: list[str], pointer: str) -> int | None:
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
    key_pat = re.compile(rf"^\s*{re.escape(last)}\s*:")
    quoted_pat = re.compile(rf'^\s*["\']{re.escape(last)}["\']\s*:')
    for i, line in enumerate(lines, start=1):
        if key_pat.search(line) or quoted_pat.search(line):
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
        ptr = meta.yaml_pointer
        if not _pointer_in_subtree(ptr, pointer):
            continue
        start = meta.start_line
        if start is not None:
            lines.append(start)
            end = meta.end_line
            if end is not None:
                lines.append(end)
            continue
        fallback = _line_for_yaml_pointer(source_lines, ptr)
        if fallback is not None:
            lines.append(fallback)
    if not lines:
        sole = _line_for_yaml_pointer(source_lines, pointer)
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
        ptr = meta.yaml_pointer
        if not _pointer_in_subtree(ptr, root_pointer):
            continue
        line = meta.start_line
        if line is None:
            line = _line_for_yaml_pointer(source_lines, ptr)
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
    """Return source with YAML pointer prefixes when file < ``full_text_max_lines``."""
    if budget.full_text_max_lines <= 0:
        return None
    if _source_line_count(raw) >= budget.full_text_max_lines:
        return None
    return _annotated_full_text_for_pointer(raw, metadata_map, budget, "")


class YamlFileHandler(FileHandler):
    """
    FileHandler for YAML files (.yaml, .yml) (C-020).

    Root NodeKind: mapping, sequence, or scalar.
    Anchors and aliases resolved before tree production.
        node_ref: JSON-pointer-style path (``""``, ``/key``) or opaque node_id
        from list_yaml_blocks (stable id for the path).

        Attributes:
            supported_extensions: frozenset({'.yaml', '.yml'}).
    """

    def _try_infra_resolve(
        self,
        node_ref: str,
        session: Any | None,
    ) -> "Node | PreviewError | None":
        """
        Resolve via in-memory :class:`~ai_editor.core.yaml_tree.models.YamlTree`.

        Returns a Node or PreviewError when ``session`` is a registered tree;
        None when the session is not a YAML tree (caller uses pointer fallback).
        """
        if session is None or not isinstance(session, YamlTree):
            return None
        value = resolve_yaml_node(session, node_ref)
        if value is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"YAML tree infra could not resolve {node_ref!r}.",
                details={"node_ref": node_ref},
            )
        if node_ref == "" or node_ref.startswith("/"):
            canon = node_ref
        else:
            _ptr = session.pointer_by_id.get(node_ref)
            if _ptr is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Opaque node_ref {node_ref!r} has no pointer in tree session.",
                    details={"node_ref": node_ref},
                )
            canon = _ptr
        return _yaml_value_to_node(value, canon)

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports."""
        return frozenset({".yaml", ".yml"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """Parse the YAML file and return the root Node.

        Root NodeKind is mapping, sequence, or scalar depending on the
        top-level YAML value. Anchors and aliases are resolved. On invalid
        YAML returns FILE_STRUCTURE_ERROR with parser 'yaml'.

        When *budget* is provided and ``budget.full_text_max_lines`` is a
        positive integer, and the file has fewer lines than that threshold,
        returns a ``NodeKind.SCALAR`` node whose ``text`` attribute holds
        annotated source (each line prefixed with ``[yaml_pointer]`` when
        the line starts a node).  Mirrors the Python handler full-text mode.

        Args:
            file_path: Project-relative path to the .yaml/.yml file.
            session: :class:`~ai_editor.core.yaml_tree.models.YamlTree` or None.
            budget: Optional PreviewBudget; when provided, full_text_max_lines
                    is honoured.

        Returns:
            Root Node or PreviewError.
        """
        try:
            import yaml  # PyYAML

            self._last_file_path = file_path
            resolved_path = str(Path(file_path).resolve())

            if session is not None and isinstance(session, YamlTree):
                doc = session.root_data
                self._doc = doc
                self._pointer_by_node_id = dict(session.pointer_by_id)
                self._metadata_map = session.metadata_map
                self._last_budget = budget
                raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
                self._last_raw = raw
                if budget is not None:
                    annotated = _annotated_full_text(raw, session.metadata_map, budget)
                    if annotated is not None:
                        return Node(
                            node_kind=NodeKind.SCALAR,
                            node_ref="",
                            attributes={"text": annotated, "full_text": True},
                        )
                return _yaml_value_to_node(doc, "")

            raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
            self._last_budget = budget
            self._last_raw = raw

            doc = yaml.safe_load(raw)
            if doc is None:
                doc = {}
            self._doc = doc
            tree = build_yaml_tree_from_text(resolved_path, raw, register=False)
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
            return _yaml_value_to_node(doc, "")
        except yaml.YAMLError as exc:
            return invalid_source_node(file_path, exc)
        except Exception as exc:
            return invalid_source_node(file_path, exc)

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a JSON Pointer or opaque node_id to the addressed YAML Node.

        Same rules as ``JsonFileHandler`` / ``list_yaml_blocks`` indexing.

        Args:
            node_ref: JSON Pointer or node_id string.
            session: Ignored for resolution (index is from ``open_root``).

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
            result = _resolve_yaml_pointer(doc, node_ref)
            if result is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Path {node_ref!r} does not exist in YAML document.",
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
            result = _resolve_yaml_pointer(doc, pointer_opt)
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
        return _yaml_value_to_node(value, canon_pointer)


def _yaml_value_to_node(value: Any, pointer: str) -> Node:
    """Convert a YAML value to a preview Node with JSON-pointer path as node_ref.

    For mapping children whose value is a scalar (not a dict or list),
    the scalar value is included as ``value`` in the child's ``attributes``
    dict alongside ``value_kind``.  This allows ``_render_mapping`` to surface
    leaf values inline without a separate drill-down call.
    """
    if isinstance(value, dict):

        def _load_mapping() -> list[Node]:
            children = []
            for k, v in value.items():
                child_pointer = f"{pointer}/{k}"
                attrs: dict[str, Any] = {"value_kind": type(v).__name__}
                if not isinstance(v, (dict, list)):
                    attrs["value"] = str(v)
                children.append(
                    Node(
                        node_kind=NodeKind.MAPPING,
                        node_ref=child_pointer,
                        name=str(k),
                        attributes=attrs,
                    )
                )
            return children

        return Node(
            node_kind=NodeKind.MAPPING,
            node_ref=pointer,
            _children_loader=_load_mapping,
        )
    if isinstance(value, list):

        def _load_seq() -> list[Node]:
            return [
                _yaml_value_to_node(v, f"{pointer}/{i}") for i, v in enumerate(value)
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


def _resolve_yaml_pointer(doc: Any, pointer: str) -> tuple[Any, str] | None:
    """Traverse YAML doc following JSON-pointer-style path."""
    if pointer == "":
        return (doc, "")
    if not pointer.startswith("/"):
        return None
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]
    current: Any = doc
    path: str = ""
    for part in parts:
        path = f"{path}/{part}"
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                try:
                    current = current[int(part)]
                except (ValueError, KeyError, TypeError):
                    return None
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return (current, path)
