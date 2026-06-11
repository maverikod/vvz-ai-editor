"""
In-memory JSON document model (session tree).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Stable namespace for uuid5-based node ids (RFC 4122 DNS namespace is arbitrary fixed id).
_JSON_NODE_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def stable_node_id_for_pointer(json_pointer: str) -> str:
    """Deterministic node id from JSON Pointer string (same document path -> same id)."""
    return str(uuid.uuid5(_JSON_NODE_NAMESPACE, json_pointer))


@dataclass
class JsonNodeMetadata:
    """Metadata for one addressable JSON value (mirrors CST node metadata shape loosely)."""

    node_id: str
    json_pointer: str
    kind: str
    parent_id: Optional[str]
    key: Optional[str]
    index: Optional[int]
    children_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "json_pointer": self.json_pointer,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "key": self.key,
            "index": self.index,
            "children_ids": list(self.children_ids),
            "children_count": len(self.children_ids),
        }


ROOT_POINTER = ""


@dataclass
class JSONTree:
    """Loaded JSON document with indexed nodes (in-memory session)."""

    tree_id: str
    file_path: str
    root_data: Any
    metadata_map: Dict[str, JsonNodeMetadata] = field(default_factory=dict)
    parent_map: Dict[str, Optional[str]] = field(default_factory=dict)
    pointer_by_id: Dict[str, str] = field(default_factory=dict)
    root_node_id: Optional[str] = None

    @classmethod
    def create(cls, file_path: str, root_data: Any) -> JSONTree:
        tid = str(uuid.uuid4())
        return cls(tree_id=tid, file_path=file_path, root_data=root_data)
