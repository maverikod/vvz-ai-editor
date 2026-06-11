"""
Domain contracts for the marked-tree unification package.

Defines MarkerContract (C-001), NodeId integer short_id (C-002),
TreeNodeUuid MAP-only identity (C-024), and AddressableBlock (C-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, NewType, Optional
from uuid import UUID

NodeId = NewType("NodeId", int)
"""Per-file monotonic integer short_id handle (C-002). NOT str. NOT UUID."""

TreeNodeUuid = NewType("TreeNodeUuid", UUID)
"""Canonical UUID4 identity stored only in MAP section (C-024). Never in TREE or API."""


class Format(enum.Enum):
    """Enumeration of file formats supported by the marked-tree system."""

    TEXT = "text"
    MARKDOWN = "markdown"
    YAML = "yaml"
    JSON = "json"
    PYTHON = "python"


class UnknownNodeIdError(ValueError):
    """Raised when a short_id is not recognised in the current tree file (C-002)."""

    short_id: NodeId

    def __init__(self, short_id: NodeId) -> None:
        super().__init__(f"Unknown short_id: {short_id!r}")
        self.short_id = short_id


def validate_short_id(value: int) -> NodeId:
    """Return NodeId for a positive integer short_id; raise ValueError otherwise."""
    if type(value) is bool:
        raise ValueError(f"short_id must be int, got {type(value)!r}")
    if not isinstance(value, int):
        raise ValueError(f"short_id must be int, got {type(value)!r}")
    if value < 1:
        raise ValueError(f"short_id must be >= 1, got {value}")
    return NodeId(value)


class AddressableBlock:
    """Minimally-addressable logical unit a marker may name (C-005).

    Marker is placed at the END of the block when no metadata slot exists;
    never mid-lexeme or inside a literal or token.
    """

    FORMAT_GRANULARITY: dict[Format, str] = {
        Format.TEXT: "line",
        Format.MARKDOWN: "md block",
        Format.YAML: "yaml block",
        Format.JSON: "json element",
        Format.PYTHON: "py logical statement",
    }

    fmt: Format
    description: str

    def __init__(self, fmt: Format, description: str) -> None:
        self.fmt = fmt
        self.description = description

    @classmethod
    def granularity_for(cls, fmt: Format) -> str:
        return cls.FORMAT_GRANULARITY[fmt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"AddressableBlock(fmt={self.fmt!r}, description={self.description!r})"


class MarkerContract(ABC):
    """Three-operation marked-tree contract (C-001).

    Round-trip invariant: unmark(mark(source)) == source (SHA-256 verified by caller).
    Markers are integer short_id tokens embedded in the TREE section only.
    TreeNodeUuid (UUID4) lives in the MAP section only; external API uses
    (file_path, short_id int). FormatHandler implements operations in parallel
    but does NOT subclass this ABC.
    """

    @abstractmethod
    def mark(self, content: str) -> str:
        """Embed per-file monotonic integer short_id markers into TREE-section text.

        Input is unmarked SourceFile body; output is marked TREE body.
        Markers are placed at AddressableBlock boundaries only.
        """

    @abstractmethod
    def parse(self, marked_text: str) -> List["TreeNode"]:
        """Parse marked TREE-section text; return ordered TreeNode list (C-009).

        Distinct from FormatHandler.parse_content which takes unmarked source.
        Raises UnknownNodeIdError when marker references unrecognised short_id.
        """

    @abstractmethod
    def unmark(self, marked_text: str) -> str:
        """Strip short_id markers from TREE-section text; reproduce SourceFile bytes exactly."""


if TYPE_CHECKING:

    @dataclass
    class TreeNode:
        short_id: NodeId
        kind: str
        content: str
        attributes: Dict[str, Any] = field(default_factory=dict)
        parent_short_id: Optional[NodeId] = None
