"""
Per-format FormatHandler abstract base (C-007).

Handlers embed integer short_id markers in TREE content only.
Canonical UUID4 identity lives in the MAP section via NodeIdMap (C-025);
handlers never call uuid.uuid4() for markers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import UUID

from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.tree_node import TreeNode


class ShortIdAllocator:
    def __init__(self, start: int = 1) -> None:
        if start < 1:
            raise ValueError("ShortIdAllocator start must be >= 1")
        self._next = start

    def allocate(self) -> int:
        """Return current short_id and increment internal counter by 1."""
        sid = self._next
        self._next += 1
        return sid

    @property
    def next_free(self) -> int:
        """Lowest short_id not yet issued (for MAP next_free metadata)."""
        return self._next


@runtime_checkable
class NodeIdMapResolveResult(Protocol):
    short_id: int
    uuid: str


@runtime_checkable
class NodeIdMapResolver(Protocol):
    def resolve(
        self,
        *,
        short_id: Optional[int] = None,
        uuid: Optional[str] = None,
    ) -> NodeIdMapResolveResult:
        """Bidirectional short_id↔UUID lookup within one loaded map; exactly one argument must be provided."""


class FormatHandler(ABC):
    def __init__(self, id_map: Optional[NodeIdMapResolver] = None) -> None:
        self._id_map = id_map

    @abstractmethod
    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        """Parse unmarked source content and return ordered TreeNode list."""

    @abstractmethod
    def mark(self, content: str) -> str:
        """Embed integer short_id markers into TREE-section text from unmarked source."""

    @abstractmethod
    def unmark(self, marked_text: str) -> str:
        """Strip markers from TREE-section text; reproduce original source bytes exactly."""

    @abstractmethod
    def sidecar_path(self, source_abs: Path) -> Path:
        """Return sibling ``<name>.tree`` path for the given absolute source file."""

    def node_id_for(self, raw: str) -> NodeId:
        """Parse decimal integer short_id from raw marker token."""
        try:
            sid = int(raw.strip())
        except ValueError as exc:
            raise ValueError(f"short_id must be int, got {raw!r}") from exc
        if sid < 1:
            raise UnknownNodeIdError(NodeId(sid))
        return NodeId(sid)

    def resolve_uuid_for_short_id(self, short_id: NodeId) -> UUID:
        if self._id_map is None:
            raise RuntimeError("NodeIdMap required for UUID resolution")
        from ai_editor.core.tree_lifecycle.node_id_map import UnknownShortIdError

        try:
            result = self._id_map.resolve(short_id=short_id)
        except UnknownShortIdError as exc:
            raise UnknownNodeIdError(NodeId(exc.short_id)) from exc
        return UUID(result.uuid)

    def resolve_short_id_for_uuid(self, node_uuid: UUID) -> NodeId:
        if self._id_map is None:
            raise RuntimeError("NodeIdMap required for UUID resolution")
        result = self._id_map.resolve(uuid=str(node_uuid))
        return NodeId(result.short_id)

    def verify_byte_round_trip(self, source: str) -> bool:
        """Return True when unmark(mark(source)) equals source byte-for-byte."""
        return self.unmark(self.mark(source)) == source

    def verify_checksum_round_trip(self, source: str) -> bool:
        from ai_editor.core.tree_lifecycle.checksum import compute_content_checksum

        marked = self.mark(source)
        restored = self.unmark(marked)
        return compute_content_checksum(restored) == compute_content_checksum(source)

    @abstractmethod
    def op_insert(
        self,
        marked_text: str,
        anchor_short_id: NodeId,
        position: str,
        new_content: str,
        next_free: int,
    ) -> str:
        """Insert a new addressable block relative to anchor (C-015, {h002}, {a007}).

        Assign fresh short_id equal to next_free; caller updates MAP next_free after.
        Validates new_content syntactically for this format at insertion point.

        Args:
            marked_text: Current marked TREE-section text.
            anchor_short_id: Existing short_id the insertion is relative to.
            position: One of "before", "after", "first_child", "last_child".
            new_content: Unmarked content of the new block.
            next_free: Lowest unused short_id from MAP (per {a007}).

        Returns:
            New marked TREE text with inserted block and integer short_id marker.

        Raises:
            UnknownNodeIdError: anchor_short_id not found in marked_text.
            ValueError: invalid position or syntactically invalid new_content.
        """

    @abstractmethod
    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        """Delete block and subtree; preserve format validity ({h003}, {a007}).

        Retired short_id is never reused. Raises UnknownNodeIdError when short_id missing.
        """

    @abstractmethod
    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        """Replace block content preserving short_id ({h004})."""

    @abstractmethod
    def op_move(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
    ) -> str:
        """Relocate block atomically preserving short_id ({h005})."""

    @abstractmethod
    def op_edit_attributes(
        self, marked_text: str, short_id: NodeId, attributes: Dict[str, Any]
    ) -> str:
        """Change node metadata only; content and position unchanged ({h006})."""

    @abstractmethod
    def op_edit_content(
        self, marked_text: str, short_id: NodeId, new_content: str
    ) -> str:
        """Change leaf-block text only; reject non-leaf targets ({h007})."""

    @abstractmethod
    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        """Return unmarked block content for delete-then-insert move ({h005})."""

    _SHORT_ID_SCAN_PATTERNS = (
        re.compile(r'"___id___"\s*:\s*(\d+)'),
        re.compile(r"<!-- id:(\d+) -->"),
        re.compile(r"^(\d+):", re.MULTILINE),
    )

    def peak_short_id_in_marked(self, marked_text: str) -> int:
        """Return the highest short_id present in marked TREE text."""
        best = 0
        for pattern in self._SHORT_ID_SCAN_PATTERNS:
            for match in pattern.finditer(marked_text):
                best = max(best, int(match.group(1)))
        return best

    def op_move_via_delete_insert(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
        next_free: int,
    ) -> str:
        """Relocate block by extracting payload, deleting source, then inserting."""
        if int(short_id) == int(anchor_short_id):
            raise ValueError("cannot move block relative to itself")
        payload = self.extract_move_payload(marked_text, short_id)
        marked_after = self.op_delete(marked_text, short_id)
        return self.op_insert(
            marked_after,
            anchor_short_id,
            position,
            payload,
            next_free,
        )
