"""
Source marker block helpers for persisted CST node UUID4 identifiers.

The marker block is stored at the end of the Python file, outside the logical
code tree we expose to CST commands. This keeps runtime code readable while
making node identities part of the file data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from typing import Dict, Tuple
from uuid import UUID

from .models import TreeNodeMetadata

ExactNodeKey = Tuple[int, int, int, int, str]
ExactNodeIdMap = Dict[ExactNodeKey, str]
PersistedNodeIds = Dict[str, str]

MARKERS_BEGIN = "# cst-node-ids: begin"
MARKERS_VERSION = "# cst-node-ids: version=1"
MARKERS_VERSION_V2 = "# cst-node-ids: version=2"
MARKERS_END = "# cst-node-ids: end"
MARKER_PREFIX = "# cst-node-id "
_V2_DATA_PREFIX = "# cst-node-ids: data="

_MARKER_RE = re.compile(
    r"^# cst-node-id "
    r"(?P<path>\d+(?:\.\d+)*) "
    r"(?P<node_type>[A-Za-z_][A-Za-z0-9_]*) "
    r"(?P<uuid>[0-9a-fA-F-]{36})$"
)


def build_exact_node_key(
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
    node_type: str,
) -> ExactNodeKey:
    """Build the canonical exact-position key for a node."""
    return (start_line, start_col, end_line, end_col, node_type)


def build_exact_key_to_id_from_metadata(
    metadata_map: Dict[str, TreeNodeMetadata],
) -> ExactNodeIdMap:
    """Convert a metadata map into exact-position -> node_id lookup."""
    result: ExactNodeIdMap = {}
    for node_id, meta in metadata_map.items():
        result[
            build_exact_node_key(
                meta.start_line,
                meta.start_col,
                meta.end_line,
                meta.end_col,
                meta.type,
            )
        ] = node_id
    return result


def build_marker_path(path_indices: tuple[int, ...]) -> str:
    """Build the canonical path key used in the trailing marker block."""
    return ".".join(str(index) for index in path_indices)


def strip_persisted_node_ids(source: str) -> tuple[str, PersistedNodeIds]:
    """
    Remove the trailing CST node-id marker block from source and parse its data.

    Returns the logical Python source and traversal-path -> UUID4 mapping.
    """
    lines = source.splitlines()
    last_non_empty = _find_last_non_empty_line(lines)
    if last_non_empty < 0 or lines[last_non_empty].strip() != MARKERS_END:
        return source, {}

    begin_idx = _find_marker_begin(lines, last_non_empty)
    if begin_idx is None:
        return source, {}

    persisted = _parse_marker_lines(lines[begin_idx + 1 : last_non_empty])
    logical_lines = list(lines[:begin_idx])
    while logical_lines and not logical_lines[-1].strip():
        logical_lines.pop()
    logical_source = "\n".join(logical_lines)
    if logical_source:
        logical_source += "\n"
    return logical_source, persisted


def append_persisted_node_ids(
    source: str,
    metadata_map: Dict[str, TreeNodeMetadata],
    root_node_id: str | None,
) -> str:
    """Append a trailing marker block that persists UUID4 identifiers."""
    logical_source, _ = strip_persisted_node_ids(source)
    normalized_source = logical_source.rstrip("\n")
    marker_block = render_marker_block(metadata_map, root_node_id)
    if not normalized_source:
        return marker_block
    return f"{normalized_source}\n\n{marker_block}"
def _flatten_path_to_uuid(
    metadata_map: Dict[str, TreeNodeMetadata],
    root_node_id: str | None,
) -> Dict[str, str]:
    """Build path-string -> stable_id for compact v2 marker payload.

    stable_id is written (not node_id) so that after any rebuild the persisted
    value is always the original UUID assigned at node creation.
    """
    out: Dict[str, str] = {}

    def walk(node_id: str, path_indices: tuple[int, ...]) -> None:
        meta = metadata_map.get(node_id)
        if meta is None:
            return
        path_key = build_marker_path(path_indices)
        out[path_key] = str(meta.stable_id)
        for index, child_id in enumerate(meta.children_ids):
            walk(child_id, path_indices + (index,))

    if root_node_id and root_node_id in metadata_map:
        walk(root_node_id, (0,))
    return out


def render_marker_block(
    metadata_map: Dict[str, TreeNodeMetadata],
    root_node_id: str | None,
) -> str:
    """Render the marker block stored after the logical code (compact v2 JSON)."""
    flat = _flatten_path_to_uuid(metadata_map, root_node_id)
    payload = json.dumps(flat, sort_keys=True, separators=(",", ":"))
    rows = [
        MARKERS_BEGIN,
        MARKERS_VERSION_V2,
        f"{_V2_DATA_PREFIX}{payload}",
        MARKERS_END,
    ]
    return "\n".join(rows) + "\n"


def _find_last_non_empty_line(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            return index
    return -1


def _find_marker_begin(lines: list[str], end_idx: int) -> int | None:
    for index in range(end_idx - 1, -1, -1):
        if lines[index].strip() == MARKERS_BEGIN:
            return index
    return None


def _parse_marker_lines(lines: list[str]) -> PersistedNodeIds:
    if lines:
        first = lines[0].strip()
        if first == MARKERS_VERSION_V2:
            if len(lines) < 2:
                return {}
            data_line = lines[1].strip()
            if not data_line.startswith(_V2_DATA_PREFIX):
                return {}
            try:
                raw = json.loads(data_line[len(_V2_DATA_PREFIX) :])
            except json.JSONDecodeError:
                return {}
            if not isinstance(raw, dict):
                return {}
            persisted_v2: PersistedNodeIds = {}
            for k, v in raw.items():
                if not isinstance(v, str):
                    continue
                try:
                    parsed = UUID(v.strip())
                except ValueError:
                    continue
                if parsed.version != 4:
                    continue
                persisted_v2[str(k)] = str(parsed)
            return persisted_v2

    persisted: PersistedNodeIds = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == MARKERS_VERSION or stripped == MARKERS_VERSION_V2:
            continue
        match = _MARKER_RE.match(stripped)
        if match is None:
            continue
        uuid_value = match.group("uuid")
        try:
            parsed = UUID(uuid_value)
        except ValueError:
            continue
        if parsed.version != 4:
            continue
        persisted[match.group("path")] = str(parsed)
    return persisted
