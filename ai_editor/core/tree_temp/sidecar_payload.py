"""JSON Sidecar payload load path for tree-temp sources (.trees/*.tree).

Decodes persisted Sidecar documents (C-002): hex source_sha256 plus root array whose
elements are TreeNode-shaped dicts (C-001). Also supports serializing Sidecar documents for persistence.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from ai_editor.core.tree_temp.tree_node import (
    TreeNode,
    tree_node_from_json_dict,
    tree_node_to_json_dict,
    validate_node_constraints,
)


class SidecarParseError(ValueError):
    """Raised when Sidecar JSON is malformed or TreeNode validation fails."""


_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DIGEST_FORMAT_LOWER_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class SidecarDocument:
    """Sidecar file top-level shape (C-002) for tooling and tests."""

    source_sha256: str
    root_nodes: List[TreeNode]


def dumps_sidecar(doc: SidecarDocument) -> str:
    """Serialize a Sidecar document to JSON text (pretty-printed, trailing newline)."""
    return serialize_sidecar_to_json_text(doc.source_sha256, doc.root_nodes)


def loads_sidecar(text: str) -> SidecarDocument:
    """Parse Sidecar JSON text into a document object."""
    sha, roots = parse_sidecar_json_text(text)
    return SidecarDocument(source_sha256=sha, root_nodes=roots)


def validate_sidecar_digest_format(digest: str) -> None:
    """Require a 64-char lowercase hex SHA-256 string; else ValueError with digest_format."""
    if not isinstance(digest, str) or not _DIGEST_FORMAT_LOWER_HEX64.match(digest):
        raise ValueError("digest_format: SHA-256 must be 64 lowercase hex characters")


def _require_object(value: Any, context: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise SidecarParseError(
            f"{context}: expected JSON object, got {type(value).__name__}"
        )
    return value


def validate_sidecar_source_sha256_field(raw: Any) -> str:
    """Validate and normalize Sidecar source_sha256 to lowercase hex."""
    if not isinstance(raw, str) or not _SHA256_HEX_RE.match(raw):
        raise SidecarParseError(
            "source_sha256 must be a 64-character hexadecimal SHA-256 digest string"
        )
    return raw.lower()


def serialize_sidecar_to_json_text(source_sha256: str, root: List[TreeNode]) -> str:
    """Build valid Sidecar JSON text with source_sha256 and root (C-002)."""
    sha = validate_sidecar_source_sha256_field(source_sha256)
    for node in root:
        validate_node_constraints(node)
    payload: Dict[str, Any] = {
        "source_sha256": sha,
        "root": [tree_node_to_json_dict(n) for n in root],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def parse_sidecar_document(doc: Dict[str, Any]) -> Tuple[str, List[TreeNode]]:
    """Decode top-level Sidecar mapping to digest and ordered root TreeNode list.

    Permitted top-level keys are exactly ``source_sha256`` and ``root``.
    """
    extra_keys = set(doc.keys()) - {"source_sha256", "root"}
    if extra_keys:
        raise SidecarParseError(f"unexpected top-level keys: {sorted(extra_keys)}")
    sha = validate_sidecar_source_sha256_field(doc.get("source_sha256"))
    root_raw = doc.get("root")
    if not isinstance(root_raw, list):
        raise SidecarParseError("root must be a JSON array")
    nodes: List[TreeNode] = []
    for index, item in enumerate(root_raw):
        if not isinstance(item, dict):
            raise SidecarParseError(f"root[{index}] must be a JSON object")
        node = tree_node_from_json_dict(item)
        validate_node_constraints(node)
        nodes.append(node)
    return sha, nodes


def parse_sidecar_json_text(text: str) -> Tuple[str, List[TreeNode]]:
    """Parse a UTF-8 Sidecar JSON document from text."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SidecarParseError(f"invalid JSON: {exc}") from exc
    doc = _require_object(loaded, "sidecar root")
    return parse_sidecar_document(doc)


def parse_sidecar_json_bytes(raw: bytes) -> Tuple[str, List[TreeNode]]:
    """Decode UTF-8 bytes and parse Sidecar JSON."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SidecarParseError(f"sidecar must be UTF-8: {exc}") from exc
    return parse_sidecar_json_text(text)
