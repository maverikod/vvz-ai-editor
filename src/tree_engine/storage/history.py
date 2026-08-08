"""The engine's history port: checkpoints the engine records, in a store it does not own.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the interface, and nothing else. Recording the editing history of a document is part of the
ENGINE's lifecycle -- a checkpoint when a document is opened, and a checkpoint after every write --
because history that exists only as a side effect in one consumer's code is history no other
consumer has. But the engine must not own a history STORE: the shipped consumer already keeps an
ephemeral per-session repository with its own initialisation, revision log and rollback, and a
second implementation inside the engine would be a competing source of truth for the same fact.

So the engine declares :class:`HistoryPort`, calls it at exactly those two moments, and knows
nothing else. Its vocabulary is "checkpoint": this module names no version-control system, imports
nothing outside the standard library, and never creates, locates or reasons about a repository. An
implementation is free to be a git repository, an append-only log, or a database; the engine cannot
tell and must not care.

There is deliberately no default implementation here. A no-op recorder would be a stub in
production code, and worse, it would let a consumer believe history was being kept when nothing
was. A consumer that keeps no history -- a read-only preview is exactly one -- supplies no port at
all, and then the engine records nothing, which is the same rule as read-only writing nothing.

Two checkpoint shapes, and the difference is load-bearing. A FULL checkpoint carries both artefacts,
the rendered source and the serialized tree that holds node identity; a DEGRADED one carries the
source alone, because for this document there is no tree file -- the tree was rebuilt in memory and
not published, or the format's plugin cannot be serialized into one at all. An implementation that
records both alike would silently lose the ability to restore identity from a revision, so
:attr:`Checkpoint.full` states the difference rather than leaving it to be inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, Tuple, runtime_checkable
from uuid import UUID

__all__ = ["Checkpoint", "CheckpointKind", "HistoryPort"]


class CheckpointKind(str, Enum):
    """The two moments the engine records. ``OPEN`` is the baseline taken when a document is
    initialised, before any mutation, so a history has something to roll back TO; ``WRITE`` is
    taken after a publication has been verified on disk, never before it."""

    OPEN = "open"
    WRITE = "write"


@dataclass(frozen=True)
class Checkpoint:
    """One recordable state of a document, with the artefacts themselves.

    The bytes are carried, not just the paths, because an ``OPEN`` checkpoint describes state the
    engine did NOT write -- it read it, or it built the tree in memory -- and an implementation
    that re-read the paths would be recording whatever the filesystem happens to hold at that
    later instant instead of what the engine actually opened.

    ``written_paths`` is empty for every ``OPEN`` checkpoint, which is precisely the statement that
    opening a document changes no file. For a ``WRITE`` it is the exact set the engine published,
    in publication order, so an implementation that stages artefacts stages those and nothing else.
    ``branch`` is the open decision's own name for how the document was obtained, carried as a
    plain string so this module stays free of every other module in the package.
    """

    kind: CheckpointKind
    document_id: UUID
    document_version: int
    source_path: Optional[Path]
    source_bytes: bytes
    source_sha256: str
    tree_path: Optional[Path] = None
    tree_bytes: Optional[bytes] = None
    tree_payload_sha256: Optional[str] = None
    written_paths: Tuple[Path, ...] = ()
    branch: Optional[str] = None
    format_id: Optional[str] = None
    source_format_id: Optional[str] = None

    @property
    def full(self) -> bool:
        """True when this checkpoint carries the tree as well as the source, and can therefore
        restore node identity; False when it carries the source alone and cannot."""
        return self.tree_bytes is not None


@runtime_checkable
class HistoryPort(Protocol):
    """What a consumer supplies so the engine can record a document's history.

    One method, called by the engine and never by the consumer: at open, and after each verified
    write. An implementation maps the two :class:`Checkpoint` shapes onto its own store -- the
    shipped editor routes a full checkpoint to its tree-and-source commit and a degraded one to its
    source-only commit -- and returns the revision it created, or None if it names none. The
    engine only passes that value back to its caller; it never interprets it.

    An implementation must not raise for ordinary conditions: it is invoked inside an operation
    that has already succeeded, and a checkpoint failure must not be reported as a failure of the
    open or the write that had in fact completed.
    """

    def record_checkpoint(self, checkpoint: Checkpoint) -> Optional[str]:
        """Record ``checkpoint``, returning the revision identifier it created, if any."""
        ...
