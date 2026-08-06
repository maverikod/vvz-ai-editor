"""Document-local short_id bidirectional map and lifecycle.

Scope (concept C-004, narrowed to the short_id subsystem only): this module
owns the positive-integer ``short_id`` <-> canonical ``uuid.UUID`` node_id
bidirectional map, its monotonic allocator, and its hex rendering. Per
{p097}, a short_id is document-local, persisted as a bidirectional map with
a monotonic ``next_short_id`` counter, rendered externally as 0x-prefixed
hex, and -- once issued -- is never reused after a delete or a rollback
(gaps are allowed).

This module is standalone: it depends only on the standard library
(``uuid``, ``dataclasses``, ``typing``) and imports nothing from any
sibling project module, including ``identity.py``. It operates purely on
``uuid.UUID`` node ids passed in by callers; ``NodeAddress``,
``replace_node_id``, and ``normalize_node_address`` are out of scope here
and belong to sibling artifacts, which use ``allocate``/``release``/
``rekey`` as building blocks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence

__all__ = [
    "ShortIdError",
    "UnknownShortIdError",
    "InvalidShortIdHexError",
    "DuplicateNodeIdError",
    "to_hex",
    "from_hex",
    "ShortIdMapSnapshot",
    "ShortIdMap",
]


class ShortIdError(Exception):
    """Base exception for the short_id subsystem (concept C-004, {p097})."""


class UnknownShortIdError(ShortIdError):
    """Raised when an int/hex short_id is not present in the map.

    Covers :meth:`ShortIdMap.resolve_hex` and :meth:`ShortIdMap.rekey`
    (when ``old_node_id`` has no short_id) per {p097}.
    """


class InvalidShortIdHexError(ShortIdError):
    """Raised by :func:`from_hex` when its input is malformed ({p097})."""


class DuplicateNodeIdError(ShortIdError):
    """Raised when allocating or merging a node_id already in the map.

    Covers :meth:`ShortIdMap.allocate`, :meth:`ShortIdMap.assign_bulk`,
    :meth:`ShortIdMap.rekey` (when ``new_node_id`` already has a short_id),
    and :meth:`ShortIdMap.merge_insert`, per {p097}.
    """


def to_hex(short_id: int) -> str:
    """Render a positive integer short_id as lowercase 0x-prefixed hex.

    Per {p097}, short_id "is a positive integer and is rendered externally
    as 0x-prefixed hex" (e.g. ``1 -> '0x1'``, ``255 -> '0xff'``). Raises
    ``ValueError`` if ``short_id`` is not an ``int`` or is less than 1.
    """

    if isinstance(short_id, bool) or not isinstance(short_id, int):
        raise ValueError(f"short_id must be an int, got {short_id!r}")
    if short_id < 1:
        raise ValueError(f"short_id must be >= 1, got {short_id!r}")
    return f"0x{short_id:x}"


def from_hex(value: str) -> int:
    """Parse a 0x-prefixed hex string back into a positive integer.

    Accepts a case-insensitive ``0x`` prefix and hex digits of either
    case. Raises :class:`InvalidShortIdHexError` for a missing/invalid
    prefix, non-hex characters, or a decoded value less than 1, per
    {p097}'s hex rendering contract.
    """

    if not isinstance(value, str):
        raise InvalidShortIdHexError(f"short_id hex value must be a str, got {value!r}")
    if len(value) < 3 or value[:2].lower() != "0x":
        raise InvalidShortIdHexError(f"short_id hex value must start with '0x': {value!r}")
    digits = value[2:]
    try:
        decoded = int(digits, 16)
    except ValueError as exc:
        raise InvalidShortIdHexError(
            f"short_id hex value has non-hex digits: {value!r}"
        ) from exc
    if decoded < 1:
        raise InvalidShortIdHexError(f"short_id hex value must decode to >= 1: {value!r}")
    return decoded


@dataclass(frozen=True)
class ShortIdMapSnapshot:
    """Immutable capture of a :class:`ShortIdMap`'s state ({p097}).

    Produced only via :meth:`ShortIdMap.snapshot` and consumed only via
    :meth:`ShortIdMap.restore`, for transaction/rollback support.
    """

    by_short: Mapping[int, uuid.UUID]
    by_node: Mapping[uuid.UUID, int]
    next_short_id: int


class ShortIdMap:
    """Document-local bidirectional short_id <-> node_id map ({p097}).

    Maintains a monotonic ``next_short_id`` counter: a short_id, once
    issued, is never reused after a node delete (:meth:`release`) or a
    rollback (:meth:`restore` to an earlier snapshot). Gaps in the
    sequence are expected and allowed.
    """

    def __init__(self, next_short_id: int = 1) -> None:
        """Create an empty bidirectional map with the given start counter."""

        self._by_short: Dict[int, uuid.UUID] = {}
        self._by_node: Dict[uuid.UUID, int] = {}
        self._next_short_id: int = next_short_id

    def allocate(self, node_id: uuid.UUID) -> int:
        """Assign the next monotonic short_id to ``node_id`` and return it.

        Stores both map directions and advances the counter. Raises
        :class:`DuplicateNodeIdError` if ``node_id`` already has a
        short_id.
        """

        if node_id in self._by_node:
            raise DuplicateNodeIdError(
                f"node_id already has a short_id: {node_id!r}"
            )
        short_id = self._next_short_id
        self._by_short[short_id] = node_id
        self._by_node[node_id] = short_id
        self._next_short_id += 1
        return short_id

    def assign_bulk(self, node_ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, int]:
        """Allocate fresh short_ids for each of ``node_ids``, in order.

        Used for ``copy_subtree``, where {p097} requires short_ids to
        always be freshly assigned in the new document. Raises
        :class:`DuplicateNodeIdError` on the first repeated node_id,
        leaving earlier allocations made by this call intact.
        """

        assigned: Dict[uuid.UUID, int] = {}
        for node_id in node_ids:
            assigned[node_id] = self.allocate(node_id)
        return assigned

    def get_node_id(self, short_id: int) -> Optional[uuid.UUID]:
        """Return the node_id for ``short_id``, or ``None`` if absent."""

        return self._by_short.get(short_id)

    def get_short_id(self, node_id: uuid.UUID) -> Optional[int]:
        """Return the short_id for ``node_id``, or ``None`` if absent."""

        return self._by_node.get(node_id)

    def resolve_hex(self, hex_value: str) -> uuid.UUID:
        """Resolve a 0x-prefixed hex short_id to its canonical node_id.

        Raises :class:`InvalidShortIdHexError` (via :func:`from_hex`) for
        a malformed hex value, or :class:`UnknownShortIdError` if the
        decoded short_id is not present in this map.
        """

        short_id = from_hex(hex_value)
        node_id = self._by_short.get(short_id)
        if node_id is None:
            raise UnknownShortIdError(f"short_id not found: {hex_value!r}")
        return node_id

    def release(self, node_id: uuid.UUID) -> None:
        """Remove ``node_id``'s entry from both map directions.

        Used on node delete. A no-op if ``node_id`` is absent. Never
        decrements the internal counter: the freed integer is never
        reused, per {p097} "no reuse after delete".
        """

        short_id = self._by_node.pop(node_id, None)
        if short_id is not None:
            self._by_short.pop(short_id, None)

    def rekey(self, old_node_id: uuid.UUID, new_node_id: uuid.UUID) -> None:
        """Move a short_id from ``old_node_id`` to ``new_node_id`` intact.

        Used by ``replace_node_id`` to preserve the exact same short_id
        across an id replacement, per {p097}. Raises
        :class:`UnknownShortIdError` if ``old_node_id`` has no short_id,
        or :class:`DuplicateNodeIdError` if ``new_node_id`` already has
        one.
        """

        short_id = self._by_node.get(old_node_id)
        if short_id is None:
            raise UnknownShortIdError(
                f"old_node_id has no short_id: {old_node_id!r}"
            )
        if new_node_id in self._by_node:
            raise DuplicateNodeIdError(
                f"new_node_id already has a short_id: {new_node_id!r}"
            )
        del self._by_node[old_node_id]
        self._by_node[new_node_id] = short_id
        self._by_short[short_id] = new_node_id

    def snapshot(self) -> ShortIdMapSnapshot:
        """Return an immutable capture of this map's current state."""

        return ShortIdMapSnapshot(
            by_short=dict(self._by_short),
            by_node=dict(self._by_node),
            next_short_id=self._next_short_id,
        )

    def restore(self, snapshot: ShortIdMapSnapshot) -> None:
        """Restore this map's directions from ``snapshot``.

        The counter is set to ``max(current, snapshot.next_short_id)``:
        rollback must never lower it, so a short_id issued at any point
        (even one later undone by this restore) is never reused, per
        {p097} "no reuse ... after rollback".
        """

        self._by_short = dict(snapshot.by_short)
        self._by_node = dict(snapshot.by_node)
        self._next_short_id = max(self._next_short_id, snapshot.next_short_id)

    def merge_insert(self, incoming: Mapping[uuid.UUID, int]) -> Dict[uuid.UUID, int]:
        """Insert a cross-document batch of node_id -> candidate short_id.

        Iterated in ``incoming`` order. If a node_id is already present
        in this map, raises :class:`DuplicateNodeIdError`. If the
        candidate short_id is free here, it is kept (and the counter is
        advanced past it if needed); otherwise it conflicts and a fresh
        short_id is allocated via the normal monotonic counter instead.
        Returns the final ``node_id -> short_id`` mapping for the whole
        batch. Implements {p097} "cross-document insertion preserves free
        short_ids and remaps conflicting ones".
        """

        result: Dict[uuid.UUID, int] = {}
        for node_id, candidate_short_id in incoming.items():
            if node_id in self._by_node:
                raise DuplicateNodeIdError(
                    f"node_id already present in the map: {node_id!r}"
                )
            if candidate_short_id not in self._by_short:
                final_short_id = candidate_short_id
                self._by_short[final_short_id] = node_id
                self._by_node[node_id] = final_short_id
                if final_short_id >= self._next_short_id:
                    self._next_short_id = final_short_id + 1
            else:
                final_short_id = self.allocate(node_id)
            result[node_id] = final_short_id
        return result

    def to_dict(self) -> dict:
        """Serialize this map for the sibling persistence code ({p100})."""

        return {
            "entries": {
                str(short_id): str(node_id)
                for short_id, node_id in self._by_short.items()
            },
            "next_short_id": self._next_short_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShortIdMap":
        """Deserialize a map previously produced by :meth:`to_dict`."""

        result = cls(next_short_id=data["next_short_id"])
        for short_id_str, node_id_str in data["entries"].items():
            short_id = int(short_id_str)
            node_id = uuid.UUID(node_id_str)
            result._by_short[short_id] = node_id
            result._by_node[node_id] = short_id
        return result
