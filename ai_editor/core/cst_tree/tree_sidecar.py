"""
CST tree sidecar files: ``{dir}/{stem}.{ext}.tree`` next to ``{dir}/{stem}.{ext}``.

Persists node identity (path -> node_id) and full metadata for fast reload when
the source SHA-256 matches. Replaces trailing ``# cst-node-ids`` blocks in source.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ai_editor.tree.sibling_convention import sibling_tree_path

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import PersistedNodeIds, build_marker_path
from .node_stable_id import logical_source_from_module

logger = logging.getLogger(__name__)

SIDECAR_HEADER_PREFIX = "CST_TREE_V1 sha256="
SIDECAR_FORMAT_VERSION = 1


def compute_source_sha256_hex(logical_source: str) -> str:
    """SHA-256 hex of UTF-8 bytes of *logical* source (parsed text)."""
    return hashlib.sha256(logical_source.encode("utf-8")).hexdigest()


def verify_sidecar_against_source(logical_source: str, payload: Dict[str, Any]) -> bool:
    """Return True if payload ``source_sha256`` matches *logical* source."""
    expected = payload.get("source_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    return expected == compute_source_sha256_hex(logical_source)


def flatten_path_to_node_id(
    metadata_map: Dict[str, TreeNodeMetadata],
    root_node_id: Optional[str],
) -> Dict[str, str]:
    """path_indices string (via :func:`build_marker_path`) -> node_id.

    Used after rebuilding a module to re-run
    :func:`tree_builder._build_tree_index` with the same node_id layout.
    """
    out: Dict[str, str] = {}

    def walk(node_id: str, path_indices: tuple[int, ...]) -> None:
        meta = metadata_map.get(node_id)
        if meta is None:
            return
        out[build_marker_path(path_indices)] = meta.node_id
        for index, child_id in enumerate(meta.children_ids):
            walk(child_id, path_indices + (index,))

    if root_node_id and root_node_id in metadata_map:
        walk(root_node_id, (0,))
    return out


def tree_to_sidecar_payload(tree: CSTTree) -> Dict[str, Any]:
    """Serialize tree state for a ``.tree`` sidecar file (JSON-ready dict)."""
    logical = logical_source_from_module(tree.module)
    sha = compute_source_sha256_hex(logical)
    meta_blob: Dict[str, Any] = {
        nid: m.to_dict() for nid, m in tree.metadata_map.items()
    }
    # parent_map may have explicit None for root children — store separately
    parent_with_nulls: Dict[str, Optional[str]] = dict(tree.parent_map)
    return {
        "format_version": SIDECAR_FORMAT_VERSION,
        "source_sha256": sha,
        "root_node_id": tree.root_node_id,
        "path_to_node_id": flatten_path_to_node_id(
            tree.metadata_map, tree.root_node_id
        ),
        "metadata_map": meta_blob,
        "metadata_node_order": list(tree.metadata_map.keys()),
        "parent_map": parent_with_nulls,
        "node_id_aliases": dict(tree.node_id_aliases),
    }


def metadata_map_from_payload(
    blob: Any,
    preferred_key_order: Optional[list[str]] = None,
) -> Dict[str, TreeNodeMetadata]:
    """Rebuild ``metadata_map`` from sidecar JSON.

    ``preferred_key_order`` restores insertion order after JSON round-trip
    (``sort_keys=True`` reorders object keys lexicographically).
    """
    if not isinstance(blob, dict):
        return {}
    parsed: Dict[str, TreeNodeMetadata] = {}
    for nid, raw in blob.items():
        if not isinstance(nid, str) or not isinstance(raw, dict):
            continue
        try:
            parsed[nid] = TreeNodeMetadata.from_dict(raw)
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Skip bad metadata entry %s: %s", nid, e)
            continue
    if (
        preferred_key_order
        and len(preferred_key_order) == len(parsed)
        and all(k in parsed for k in preferred_key_order)
    ):
        return {k: parsed[k] for k in preferred_key_order}
    return parsed


def parse_sidecar_file(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse a ``.tree`` file: first line ``CST_TREE_V1 sha256=<hex>``, rest JSON.
    """
    content = content.strip("\ufeff")
    if not content.strip():
        return None
    lines = content.splitlines()
    if not lines:
        return None
    header = lines[0].strip()
    if not header.startswith(SIDECAR_HEADER_PREFIX):
        return None
    hex_part = header[len(SIDECAR_HEADER_PREFIX) :].strip()
    if len(hex_part) != 64:
        return None
    body = "\n".join(lines[1:]).lstrip("\n")
    if not body.strip():
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    # Header is authoritative for checksum (also inside JSON for verify)
    payload["source_sha256"] = hex_part
    return payload


def read_sidecar_payload(py_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse sibling tree file for ``py_path`` if it exists."""
    path = sibling_tree_path(py_path.resolve())
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Could not read sidecar %s: %s", path, e)
        return None
    return parse_sidecar_file(text)


def render_sidecar_file(payload: Dict[str, Any]) -> str:
    """Render full sidecar file text (header + JSON body)."""
    sha = payload.get("source_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise ValueError("payload must include valid source_sha256")
    body = dict(payload)
    # body JSON should not duplicate header hash if present
    body_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return f"{SIDECAR_HEADER_PREFIX}{sha}\n{body_json}\n"


def persist_tree_sidecar_after_edit(tree: CSTTree) -> Path:
    """Rewrite CST sidecar after each mutation (final or pending path)."""
    if not tree.file_path:
        raise ValueError("CSTTree.file_path is required to persist sidecar")
    return write_sidecar_atomic(Path(tree.file_path), tree)


def write_sidecar_atomic(py_path: Path, tree: CSTTree) -> Path:
    """Write sibling ``.tree`` sidecar next to source (atomic replace)."""
    py_path = py_path.resolve()
    target_path = sibling_tree_path(py_path)
    payload = tree_to_sidecar_payload(tree)
    parent_dir = target_path.parent
    text = render_sidecar_file(payload)
    fd, tmp_name = tempfile.mkstemp(suffix=".tree.tmp", dir=str(parent_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, str(target_path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target_path


def persisted_node_ids_from_payload(payload: Dict[str, Any]) -> PersistedNodeIds:
    """Extract path -> node_id map for :func:`_build_tree_index`."""
    raw = payload.get("path_to_node_id")
    if not isinstance(raw, dict):
        return {}
    out: PersistedNodeIds = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def parent_map_from_payload(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    raw = payload.get("parent_map")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Optional[str]] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        if v is None or (isinstance(v, str) and v):
            out[k] = v if isinstance(v, str) or v is None else None
        else:
            out[k] = None
    return out


def aliases_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    raw = payload.get("node_id_aliases")
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in raw.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def sidecar_matches_built_tree(tree: CSTTree, payload: Dict[str, Any]) -> bool:
    """True if rebuilt tree has the same path->node_id layout as sidecar."""
    expected = payload.get("path_to_node_id")
    if not isinstance(expected, dict):
        return False
    got = flatten_path_to_node_id(tree.metadata_map, tree.root_node_id)
    return got == expected
