"""
Data models for non-vectorizing structure extraction.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

SourceKind = Literal["disk", "draft_session"]


@dataclass
class StructureWarning:
    code: str
    message: str
    file_path: Optional[str] = None


@dataclass
class PreviewRef:
    command: str = "universal_file_preview"
    file_path: str = ""
    node_ref: Optional[str] = None
    selector: Optional[str] = None
    session_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "command": self.command,
            "file_path": self.file_path,
        }
        if self.node_ref is not None:
            out["node_ref"] = self.node_ref
        if self.selector is not None:
            out["selector"] = self.selector
        if self.session_id is not None:
            out["session_id"] = self.session_id
        return out


@dataclass
class StructureBlock:
    block_id: str
    node_type: str
    start_line: int
    end_line: int
    node_ref: Optional[str] = None
    name: Optional[str] = None
    qualname: Optional[str] = None
    path: Optional[str] = None
    start_col: Optional[int] = None
    end_col: Optional[int] = None
    text: Optional[str] = None
    preview: Optional[PreviewRef] = None

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "block_id": self.block_id,
            "node_type": self.node_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }
        for key in (
            "node_ref",
            "name",
            "qualname",
            "path",
            "start_col",
            "end_col",
            "text",
        ):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        if self.preview is not None:
            out["preview"] = self.preview.as_dict()
        return out


@dataclass
class StructureDocument:
    file_path: str
    format_group: str
    source: SourceKind
    content_sha256: str
    blocks: List[StructureBlock] = field(default_factory=list)
    session_id: Optional[str] = None
    warnings: List[StructureWarning] = field(default_factory=list)
    ids_stable: bool = False
    preview_file_path: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "format_group": self.format_group,
            "source": self.source,
            "session_id": self.session_id,
            "content_sha256": self.content_sha256,
            "ids_stable": self.ids_stable,
            "blocks": [b.as_dict() for b in self.blocks],
            "warnings": [
                {"code": w.code, "message": w.message, "file_path": w.file_path}
                for w in self.warnings
            ],
        }
