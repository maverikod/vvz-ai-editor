"""Stable positions, local fragments, and the lazy offset index for
concept C-005 (IncrementalSourceBuffer), layered on top of the piece-table
buffer in ``src/tree_engine/core/buffer.py``.

Per {p014}, a common-tree node anchors to a *stable position* in the
canonical buffer instead of an absolute integer offset, so it never needs
renumbering when an edit happens elsewhere in the document. Per {p017},
the cost of a local operation must scale with the size of the edited
fragment, its path depth, and the number of shifted ranges -- never with
the total node count of the document -- and a batch of K operations must
not perform K full traversals. Per {p067}, ``subtree_bytes`` is a locally
updated aggregate on a node and its ancestors, not something re-derived by
re-serializing a subtree; when the cached value is missing or stale,
callers must be able to detect that rather than trust a wrong number. The
four-case rule ({p016}) permits a full parse/traversal rebuild only at
initial document load, on an explicit full check, during recovery after
an external modification, and as the control check of a completed
operation batch -- never on the normal per-edit path, never per element.

How the {p017} bound is met: :meth:`LazyOffsetIndex.record_edit` (driven
by :meth:`PositionIndex.on_edit_applied`) is O(1) -- it appends one
compact edit record to an append-only log and touches no registered
:class:`StablePosition`. Absolute offsets are reconstructed lazily, in
:meth:`LazyOffsetIndex.resolve`, by replaying only the edits recorded
since that specific position was last resolved -- cost bounded by that
count, never by how many other positions exist or how large the document
is. That is what makes an edit near the start of a huge document cheap:
it never walks, shifts, or even looks at positions after it.

This file owns position resolution, offset laziness, and the
``subtree_bytes`` aggregate only. It imports ``buffer.py``'s public
interface (``SourceBuffer``, ``EditNotification``, ``BufferEditListener``)
and never reimplements or forks the byte-storage layer.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from tree_engine.core.buffer import BufferEditListener, EditNotification, SourceBuffer

__all__ = [
    "StablePosition",
    "LocalFragment",
    "LazyOffsetIndex",
    "SubtreeBytesAggregate",
    "FullReindexReason",
    "PositionIndex",
]


# --------------------------------------------------------------------------
# StablePosition / LocalFragment
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StablePosition:
    """An immutable anchor a common-tree node stores instead of an
    absolute integer offset ({p014}). ``token`` is an opaque handle
    assigned by the :class:`LazyOffsetIndex` that created it -- unique for
    that index's lifetime, never reused. ``node_path`` locates the
    matching :class:`SubtreeBytesAggregate` entry; it plays no part in
    offset resolution. Storing no absolute offset itself is exactly what
    keeps a ``StablePosition`` valid without renumbering across edits
    elsewhere in the buffer.
    """

    token: int
    node_path: Tuple[str, ...]


@dataclass(frozen=True)
class LocalFragment:
    """A resolved view of a :class:`StablePosition` against the current
    buffer state: ``[start, end)`` plus a lazy bytes accessor. Building a
    ``LocalFragment`` never reads the buffer -- ``start``/``end`` are
    already-resolved values from :meth:`PositionIndex.resolve_fragment`.
    ``bytes()`` performs the actual on-demand slice, never eagerly.
    """

    start: int
    end: int
    is_exact: bool
    _buffer: SourceBuffer = field(repr=False, compare=False)

    def __len__(self) -> int:
        return self.end - self.start

    def bytes(self) -> bytes:
        """Materialize this fragment's bytes on demand: O(overlapping
        piece count), never O(document size)."""
        return _slice_buffer(self._buffer, self.start, self.end)


def _slice_buffer(buffer: SourceBuffer, start: int, end: int) -> bytes:
    length = len(buffer)
    if start < 0 or end < start or end > length:
        raise ValueError(f"invalid fragment range [{start}, {end}) for buffer of length {length}")
    if start == end:
        return b""
    chunks: List[bytes] = []
    offset = 0
    for _is_original, chunk in buffer.iter_regions():
        chunk_start = offset
        chunk_end = offset + len(chunk)
        offset = chunk_end
        if chunk_end <= start:
            continue
        if chunk_start >= end:
            break
        lo = max(start, chunk_start) - chunk_start
        hi = min(end, chunk_end) - chunk_start
        chunks.append(chunk[lo:hi])
    return b"".join(chunks)


# --------------------------------------------------------------------------
# LazyOffsetIndex
# --------------------------------------------------------------------------


@dataclass
class _EditRecord:
    """One compact log entry for a past edit, in buffer coordinates at the
    time it was applied. ``delta`` is the net length change."""

    start: int
    end: int
    delta: int


@dataclass
class _PositionEntry:
    """Mutable bookkeeping for one registered :class:`StablePosition`.
    ``cached_seq`` is the edit-log index through which ``start``/
    ``length``/``is_exact`` are already accurate; stale exactly when it
    lags the index's current log length."""

    position: StablePosition
    start: int
    length: int
    is_exact: bool
    cached_seq: int


def _apply_edit_to_span(
    start: int, length: int, is_exact: bool, rec: _EditRecord
) -> Tuple[int, int, bool]:
    """Fold one past edit into a resolved ``(start, length, is_exact)``."""
    end = start + length
    if rec.end <= start:
        # Edit entirely before the span: shift, nothing else changes.
        return start + rec.delta, length, is_exact
    if rec.start >= end:
        # Edit entirely after the span: no effect at all.
        return start, length, is_exact
    if rec.start >= start and rec.end <= end:
        # Edit fully inside the span: only its length changes.
        return start, length + rec.delta, is_exact
    # Partial boundary overlap, or the edit fully contains the span: the
    # relationship is no longer unambiguous. Clamp to the edit's own
    # start and flag the result inexact so callers know to re-derive the
    # position from the tree instead of trusting it ({p067}).
    new_start = rec.start if rec.start >= start else start + rec.delta
    return new_start, max(length + rec.delta, 0), False


class LazyOffsetIndex:
    """Maps :class:`StablePosition` handles to current absolute offsets,
    with lazy, on-demand resolution ({p014}, {p017}). ``record_edit`` is
    the only method the per-edit path calls, and it is O(1): it appends to
    an append-only log and touches no registered position. ``resolve`` is
    where the deferred work happens, charged only to the position being
    resolved, bounded by the edits recorded since it was last resolved.
    """

    def __init__(self) -> None:
        self._next_token = itertools.count(1)
        self._entries: Dict[int, _PositionEntry] = {}
        self._edits: List[_EditRecord] = []

    @property
    def edit_count(self) -> int:
        return len(self._edits)

    @property
    def position_count(self) -> int:
        return len(self._entries)

    def create_position(
        self, start: int, length: int, node_path: Tuple[str, ...]
    ) -> StablePosition:
        """Register a new stable anchor at the current ``[start, start +
        length)`` and return its opaque handle."""
        token = next(self._next_token)
        position = StablePosition(token=token, node_path=tuple(node_path))
        self._entries[token] = _PositionEntry(
            position=position, start=start, length=length, is_exact=True, cached_seq=len(self._edits)
        )
        return position

    def _entry(self, position: StablePosition) -> _PositionEntry:
        entry = self._entries.get(position.token)
        if entry is None:
            raise KeyError(f"unknown or forgotten StablePosition token {position.token}")
        return entry

    def is_stale(self, position: StablePosition) -> bool:
        """True when ``position`` has unreplayed edits pending -- an O(1)
        check that itself performs no replay."""
        return self._entry(position).cached_seq != len(self._edits)

    def record_edit(self, start: int, end: int, replacement_length: int) -> None:
        """Record one applied edit. O(1): no registered position is read
        or written by this call."""
        delta = replacement_length - (end - start)
        self._edits.append(_EditRecord(start=start, end=end, delta=delta))

    def resolve(self, position: StablePosition) -> Tuple[int, int, bool]:
        """Return the current ``(start, length, is_exact)`` for
        ``position``, replaying only the edits recorded since it was last
        resolved, then memoizing the result."""
        entry = self._entry(position)
        pending = self._edits[entry.cached_seq :]
        if pending:
            start, length, is_exact = entry.start, entry.length, entry.is_exact
            for rec in pending:
                start, length, is_exact = _apply_edit_to_span(start, length, is_exact, rec)
            entry.start, entry.length, entry.is_exact = start, length, is_exact
            entry.cached_seq = len(self._edits)
        return entry.start, entry.length, entry.is_exact

    def forget(self, position: StablePosition) -> None:
        """Drop a position's bookkeeping (e.g. its node was removed)."""
        self._entries.pop(position.token, None)

    def full_resync(self) -> int:
        """Force-resolve every still-registered position and compact the
        edit log, returning the number of edits compacted. Cost is
        O(registered positions + edit-log length): a genuine full
        traversal, only ever called from :meth:`PositionIndex.
        full_reindex`, never from the per-edit path."""
        for entry in list(self._entries.values()):
            self.resolve(entry.position)
        compacted = len(self._edits)
        self._edits.clear()
        for entry in self._entries.values():
            entry.cached_seq = 0
        return compacted


# --------------------------------------------------------------------------
# SubtreeBytesAggregate
# --------------------------------------------------------------------------


class SubtreeBytesAggregate:
    """Locally updated ``subtree_bytes`` running total per node path
    ({p067}). Never recomputed by re-serializing a subtree:
    :meth:`apply_delta` only adjusts already-tracked totals along one
    node's ancestor chain, in O(path depth). A node whose total was never
    registered (or was invalidated) reads back as ``None`` -- the
    stale/missing sentinel callers (e.g. drill_down auto-expansion) must
    check for instead of trusting an absent or stale number."""

    def __init__(self) -> None:
        self._totals: Dict[Tuple[str, ...], int] = {}

    def initialize(self, node_path: Tuple[str, ...], byte_count: int) -> None:
        """Seed (or overwrite) the known-good total for ``node_path``."""
        self._totals[tuple(node_path)] = byte_count

    def get(self, node_path: Tuple[str, ...]) -> Optional[int]:
        """Return the cached total, or ``None`` if missing/invalidated."""
        return self._totals.get(tuple(node_path))

    def invalidate(self, node_path: Tuple[str, ...]) -> None:
        """Mark ``node_path``'s total unknown until re-derived."""
        self._totals.pop(tuple(node_path), None)

    def apply_delta(self, node_path: Tuple[str, ...], delta: int) -> Tuple[Tuple[str, ...], ...]:
        """Adjust ``node_path`` and every ancestor prefix (including the
        root, the empty path) by ``delta``. Only entries with a known
        total are touched; an untracked ancestor is left absent rather
        than guessed at. Returns the prefixes actually adjusted. O(path
        depth) -- never O(total node count), no other subtree touched."""
        if delta == 0:
            return ()
        path = tuple(node_path)
        touched: List[Tuple[str, ...]] = []
        for i in range(len(path), -1, -1):
            prefix = path[:i]
            current = self._totals.get(prefix)
            if current is not None:
                self._totals[prefix] = current + delta
                touched.append(prefix)
        return tuple(touched)


# --------------------------------------------------------------------------
# full_reindex / FullReindexReason
# --------------------------------------------------------------------------


class FullReindexReason(Enum):
    """The exhaustive four-case whitelist ({p016}) for when a full
    parse/traversal rebuild of the offset index and ``subtree_bytes``
    aggregate is permitted."""

    INITIAL_LOAD = "initial_load"
    EXPLICIT_FULL_CHECK = "explicit_full_check"
    EXTERNAL_MODIFICATION_RECOVERY = "external_modification_recovery"
    BATCH_CONTROL_CHECK = "batch_control_check"


# --------------------------------------------------------------------------
# PositionIndex -- the per-edit notification entry point
# --------------------------------------------------------------------------


class PositionIndex:
    """Bundles a :class:`LazyOffsetIndex` and a
    :class:`SubtreeBytesAggregate` over one :class:`SourceBuffer`, and is
    the natural ``BufferEditListener`` consumer of its edit notifications.
    Register with ``buffer.add_listener(index)`` so every
    ``SourceBuffer.apply_edit`` call drives :meth:`on_buffer_edit`, which
    forwards to :meth:`on_edit_applied` -- the per-edit notification entry
    point the downstream mutation engine (C-006, G-002) is expected to
    drive after each applied operation."""

    def __init__(self, buffer: SourceBuffer) -> None:
        self._buffer = buffer
        self.offsets = LazyOffsetIndex()
        self.subtree_bytes = SubtreeBytesAggregate()

    # -- BufferEditListener protocol ---------------------------------------

    def on_buffer_edit(self, notification: EditNotification) -> None:
        self.on_edit_applied(notification.byte_range, notification.replacement, notification.node_path)

    # -- the per-edit notification entry point ------------------------------

    def on_edit_applied(
        self,
        edit_range: Tuple[int, int],
        replacement_fragment: bytes,
        node_path: Tuple[str, ...],
    ) -> None:
        """Handle one applied edit ({p017}, {p067}). (a) Records the shift
        in the :class:`LazyOffsetIndex` in O(1); no offset-index entry is
        walked or touched here, only reconciled lazily on the next
        :meth:`LazyOffsetIndex.resolve` of that position. (b) Adjusts the
        ``subtree_bytes`` total on ``node_path`` and its ancestors only,
        in O(path depth). Never performs a full-document traversal and
        never calls :meth:`full_reindex`."""
        start, end = edit_range
        delta = len(replacement_fragment) - (end - start)
        self.offsets.record_edit(start, end, len(replacement_fragment))
        self.subtree_bytes.apply_delta(node_path, delta)

    # -- convenience wrappers over the offset index --------------------------

    def create_position(self, start: int, length: int, node_path: Tuple[str, ...]) -> StablePosition:
        return self.offsets.create_position(start, length, node_path)

    def resolve_fragment(self, position: StablePosition) -> LocalFragment:
        start, length, is_exact = self.offsets.resolve(position)
        return LocalFragment(start=start, end=start + length, is_exact=is_exact, _buffer=self._buffer)

    # -- the only sanctioned full-traversal entry point ({p016}) ------------

    def full_reindex(self, reason: FullReindexReason) -> None:
        """Rebuild the offset index and compact its edit log. The only
        function in this file allowed to perform work proportional to the
        number of registered positions rather than to one edit's local
        footprint. ``reason`` must be one of the four
        :class:`FullReindexReason` members -- anything else is a hard
        error. Never called by :meth:`on_edit_applied`."""
        if not isinstance(reason, FullReindexReason):
            raise TypeError(
                f"full_reindex requires a FullReindexReason (one of the four {{p016}} "
                f"cases), got {reason!r}"
            )
        self.offsets.full_resync()
