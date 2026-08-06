"""Canonical piece-table byte buffer for concept C-005 (IncrementalSourceBuffer).

This module implements ``SourceBuffer``: the document's canonical byte
buffer, represented as a piece table seeded from the original source bytes.
Every applied edit only touches the pieces that overlap the edited byte
range; all other pieces are left untouched (same object, same list slot
outside the spliced region), which keeps the cost of a single edit
proportional to the number of overlapping pieces and the size of the edit
itself, never to the size of the document or the total piece count.

Piece-count bound: the piece list starts at length 1 (or 0 for an empty
source) and each ``apply_edit`` call can, at most, remove the pieces fully
covered by the edited range and add up to three new ones (a left
remainder, a replacement piece, a right remainder). So after K edits the
piece list has O(K) entries, never O(document size). Locating the pieces
that overlap a given edit therefore only requires a linear scan bounded by
the *current* piece count (O(K)), not by the byte length of the document,
which satisfies the {p017} local-cost bound without needing a balanced
tree or rope index. If profiling ever shows the linear scan itself is a
bottleneck (very large K), the sibling ``positions.py`` module may layer a
faster piece locator (e.g. an index keyed by cumulative offsets) on top of
this piece list; that is explicitly out of scope here.

Unchanged regions are never re-copied or reformatted: ``iter_regions``
yields each piece's bytes verbatim from either the original source or the
append-only "added" buffer, which is the byte-preservation guarantee of
{p014}/{p022}.

This file is self-contained on the standard library. It does not import,
and must not be imported by, any sibling module in this package other than
through the public API defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Literal, Optional, Protocol, Tuple

__all__ = [
    "Piece",
    "EditNotification",
    "BufferEditListener",
    "SourceBuffer",
]


@dataclass(frozen=True)
class Piece:
    """A contiguous run of bytes referencing either the original source or
    the append-only "added" buffer.

    ``start`` and ``length`` are offsets *within the referenced origin
    buffer* (``source`` when ``origin == 'original'``, the internal
    ``_added`` bytearray when ``origin == 'added'``) -- not absolute
    positions in the document. This is what makes pieces before and after
    an edit immune to renumbering: an edit never needs to touch a piece's
    ``start``/``length`` unless that specific piece is being split or
    replaced.
    """

    origin: Literal["original", "added"]
    start: int
    length: int


@dataclass(frozen=True)
class EditNotification:
    """The exact payload delivered to listeners after one applied edit.

    ``byte_range`` is the ``(start, end)`` span in the buffer's coordinate
    space at the moment of the edit (before the edit was applied).
    ``replacement`` is the fragment that was spliced in. ``node_path`` is
    the affected node's path in the common tree, as supplied by the
    mutation engine (C-006, G-002).
    """

    byte_range: Tuple[int, int]
    replacement: bytes
    node_path: Tuple[str, ...]


class BufferEditListener(Protocol):
    """Interface implemented by consumers that want to react to edits.

    Sibling ``positions.py`` implements this to drive its lazy offset
    index and its ``subtree_bytes`` aggregate. This module defines the
    interface only; it does not implement or instantiate any listener.
    """

    def on_buffer_edit(self, notification: EditNotification) -> None:
        ...


class SourceBuffer:
    """The canonical piece-table byte buffer for a single document.

    Seeded from the original source bytes ({p014}). Local edits are
    applied via :meth:`apply_edit`, which mutates only the pieces
    overlapping the edited range and notifies registered listeners with an
    :class:`EditNotification`. Serialization (:meth:`iter_regions`,
    :meth:`serialize`) reproduces untouched regions byte-for-byte.
    """

    def __init__(self, source: bytes) -> None:
        self.source: bytes = bytes(source)
        self._added: bytearray = bytearray()
        self._pieces: List[Piece] = []
        if len(self.source) > 0:
            self._pieces.append(Piece(origin="original", start=0, length=len(self.source)))
        self._length: int = len(self.source)
        self._listeners: List[BufferEditListener] = []

    # -- listener registration -------------------------------------------------

    def add_listener(self, listener: BufferEditListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: BufferEditListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    # -- size --------------------------------------------------------------

    def __len__(self) -> int:
        # Maintained incrementally in apply_edit; never recomputed by a
        # full scan of the piece list or the document bytes.
        return self._length

    # -- edit application ----------------------------------------------------

    def apply_edit(
        self,
        start: int,
        end: int,
        replacement: bytes,
        node_path: Tuple[str, ...],
    ) -> EditNotification:
        """Apply one local edit and notify listeners.

        Replaces the byte range ``[start, end)`` with ``replacement``.
        ``start == end`` is a pure insertion; ``replacement == b''`` is a
        pure deletion. Only the pieces overlapping ``[start, end)`` are
        touched: at most the two boundary pieces are split into a
        surviving left/right remainder, any pieces fully covered by the
        range are dropped, and one new piece is inserted for
        ``replacement`` (appended to the internal "added" buffer). Pieces
        entirely before ``start`` or entirely after ``end`` are left
        exactly as they are -- not recreated, not re-offset.
        """
        current_length = self._length
        if not (0 <= start <= end <= current_length):
            raise ValueError(
                f"invalid edit range [{start}, {end}) for buffer of length {current_length}"
            )
        replacement = bytes(replacement)
        pieces = self._pieces

        lo: Optional[int] = None
        hi: Optional[int] = None
        left_remainder: Optional[Piece] = None
        right_remainder: Optional[Piece] = None

        offset = 0
        i = 0
        n = len(pieces)
        while i < n:
            piece = pieces[i]
            piece_start = offset
            piece_end = offset + piece.length
            if piece_end <= start:
                # Entirely before the edit: untouched, skip cheaply.
                offset = piece_end
                i += 1
                continue
            if piece_start >= end:
                # Entirely after the edit: stop scanning, nothing further
                # overlaps -- this piece and all later ones are untouched.
                break
            # This piece overlaps [start, end).
            if lo is None:
                lo = i
            hi = i + 1
            if piece_start < start:
                left_remainder = Piece(
                    origin=piece.origin,
                    start=piece.start,
                    length=start - piece_start,
                )
            if piece_end > end:
                right_remainder = Piece(
                    origin=piece.origin,
                    start=piece.start + (end - piece_start),
                    length=piece_end - end,
                )
            offset = piece_end
            i += 1

        if lo is None:
            # No piece overlapped [start, end): either start == end (pure
            # insertion at a piece boundary) or the buffer is empty. ``i``
            # is already the correct insertion index: the number of
            # pieces fully before ``start``.
            lo = hi = i

        new_pieces: List[Piece] = []
        if left_remainder is not None:
            new_pieces.append(left_remainder)
        if replacement:
            new_pieces.append(
                Piece(origin="added", start=len(self._added), length=len(replacement))
            )
            self._added.extend(replacement)
        if right_remainder is not None:
            new_pieces.append(right_remainder)

        # Splice only the affected slice of the piece list; pieces outside
        # [lo, hi) keep their identity and position untouched.
        pieces[lo:hi] = new_pieces

        self._length = current_length - (end - start) + len(replacement)

        notification = EditNotification(
            byte_range=(start, end),
            replacement=replacement,
            node_path=tuple(node_path),
        )
        for listener in self._listeners:
            listener.on_buffer_edit(notification)
        return notification

    # -- serialization -------------------------------------------------------

    def iter_regions(self) -> Iterator[Tuple[bool, bytes]]:
        """Yield ``(is_original, chunk_bytes)`` per piece, in order.

        A serializer built on this can emit ``chunk_bytes`` verbatim for
        every region, guaranteeing byte-for-byte reproduction of anything
        the mutation engine did not touch ({p014}, {p022}).
        """
        for piece in self._pieces:
            if piece.origin == "original":
                chunk = self.source[piece.start : piece.start + piece.length]
                yield True, chunk
            else:
                chunk = bytes(self._added[piece.start : piece.start + piece.length])
                yield False, chunk

    def serialize(self) -> bytes:
        """Materialize the full current buffer contents.

        Convenience full materialization used for initial-load round-trip
        checks and full-document reconstruction -- not for the normal
        per-edit path, which should rely on :meth:`iter_regions` and only
        re-emit what changed.
        """
        return b"".join(chunk for _is_original, chunk in self.iter_regions())
