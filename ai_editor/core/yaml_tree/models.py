"""
In-memory YAML document model (session tree).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class YamlNodeMetadata:
    """Metadata for one addressable YAML value (parallel to JsonNodeMetadata)."""

    node_id: str
    yaml_pointer: str
    kind: str
    parent_id: Optional[str]
    key: Optional[str]
    index: Optional[int]
    children_ids: List[str] = field(default_factory=list)
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "yaml_pointer": self.yaml_pointer,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "key": self.key,
            "index": self.index,
            "children_ids": list(self.children_ids),
            "children_count": len(self.children_ids),
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


ROOT_POINTER = ""


@dataclass
class YamlTree:
    """Loaded YAML document with indexed nodes (in-memory session)."""

    tree_id: str
    file_path: str
    root_data: Any
    metadata_map: Dict[str, YamlNodeMetadata] = field(default_factory=dict)
    parent_map: Dict[str, Optional[str]] = field(default_factory=dict)
    pointer_by_id: Dict[str, str] = field(default_factory=dict)
    root_node_id: Optional[str] = None

    @classmethod
    def create(cls, file_path: str, root_data: Any) -> YamlTree:
        import uuid

        tid = str(uuid.uuid4())
        return cls(tree_id=tid, file_path=file_path, root_data=root_data)
