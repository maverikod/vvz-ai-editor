"""Document lock coordinator for transactional concurrency (C-007).

Scope (concept C-007, narrowed to the internal mutex/transaction
coordinator only): this module owns exactly one thing — the
:class:`DocumentLockCoordinator` that serializes operations on a single
document and, for a transaction spanning several documents, acquires all
of their locks in a deterministic order before any of them proceed.

Per {p035}: operations on one document are serialized by an internal
mutex/transaction coordinator. A transaction spanning several documents,
including cross-document move and reference propagation, takes the locks
of every participating document in a deterministic order by document_id
(UUID4) and releases them only after commit or rollback completes, so
that deadlock and partial publication are impossible. Automatic merging
of concurrent changes is forbidden — this module never merges anything,
it only orders and holds locks.

Out of scope here, delivered by the sibling step G-015/T-001/A-002: batch
execution, the isolated transactional working state, expected_version
checks, and the commit/rollback protocol itself. This module performs no
validation and no version bookkeeping; it only answers the question
"whose turn is it to touch this document" and does so in an order that
can never deadlock.

Source-of-truth requirement labels honored here: {p035}.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Dict, Iterable, Iterator, List
from uuid import UUID

__all__ = [
    "DocumentLockCoordinator",
    "LockOrderError",
]


class LockOrderError(Exception):
    """Raised when lock usage would violate the coordinator's invariants.

    Covers exactly two misuses that would otherwise silently break the
    deadlock-freedom and no-partial-release guarantees from {p035}:
    releasing a document that this coordinator did not report as locked,
    and re-entering :meth:`DocumentLockCoordinator.acquire_locks` for a
    document_id that is already held by the *same* acquire session before
    that session has released it (double-acquire within one call).
    """


class DocumentLockCoordinator:
    """Serializes per-document operations and orders multi-document locks.

    Holds one :class:`threading.Lock` per document_id, created lazily on
    first use and kept for the coordinator's lifetime (locks are cheap and
    reused, never removed, so that concurrent callers always synchronize
    on the same lock object for a given document_id).

    Thread-safety: the coordinator's own bookkeeping (the registry dict and
    the "currently held" set) is itself protected by a private guard lock.
    That guard is only ever held for the brief instant needed to look up or
    create a per-document lock, or to flip a "locked" flag — never while
    blocking on a document lock — so it cannot itself become a source of
    contention or deadlock.

    Deadlock freedom: :meth:`acquire_locks` always sorts the requested
    document_ids into strictly ascending UUID4 order before acquiring them
    one at a time in that order. Two transactions that both want documents
    A and B — regardless of which order the caller requested them in — end
    up trying to take A then B, never A-then-B in one thread and B-then-A
    in the other. That per-document total order is exactly what rules out
    the circular-wait condition required for deadlock.
    """

    def __init__(self) -> None:
        self._locks: Dict[UUID, threading.Lock] = {}
        self._held: set[UUID] = set()
        self._owner: Dict[UUID, int] = {}
        self._guard = threading.Lock()

    def _lock_for(self, document_id: UUID) -> threading.Lock:
        """Return the per-document lock for document_id, creating it if new."""
        with self._guard:
            lock = self._locks.get(document_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[document_id] = lock
            return lock

    def is_locked(self, document_id: UUID) -> bool:
        """Return True if document_id currently holds a lock via this coordinator."""
        with self._guard:
            return document_id in self._held

    @contextmanager
    def acquire_locks(self, document_ids: Iterable[UUID]) -> Iterator[List[UUID]]:
        """Acquire locks for all document_ids in ascending UUID4 order.

        Duplicate ids are acquired once. Locks are taken one at a time in
        sorted order — never all-at-once and never in caller-supplied
        order — which is what makes concurrent multi-document transactions
        deadlock-free: every caller converges on the same acquisition
        order for any given pair of documents.

        The context manager enters (yields) only once every requested lock
        is held. On normal exit *or* on an exception propagating out of
        the ``with`` block, it releases exactly the locks it acquired, via
        :meth:`release_locks`, satisfying "release only after commit or
        rollback completes, never partially" for the common case where the
        caller does commit/rollback work inside the ``with`` block.

        Callers that need to hold locks across a longer-lived commit or
        rollback sequence that does not fit a single ``with`` block may
        instead call :meth:`acquire_locks` as a plain function... but the
        supported, recommended shape is the context manager: do the
        commit/rollback work inside the block, then let it release.

        Args:
            document_ids: document_id values to lock for this transaction.

        Yields:
            The sorted, de-duplicated list of document_ids that were
            locked, in the exact order they were acquired.

        Raises:
            LockOrderError: if the *same thread* re-enters
                :meth:`acquire_locks` for a document_id it already holds
                and has not yet released. Ordinary contention — a
                different thread wanting the same document_id — is not an
                error: that thread simply blocks in this call until the
                holder releases it.
        """
        ordered = sorted(set(document_ids), key=lambda doc_id: doc_id.int)
        acquired: List[UUID] = []
        current_thread = threading.get_ident()
        try:
            for document_id in ordered:
                with self._guard:
                    if self._owner.get(document_id) == current_thread:
                        # This exact thread already holds this document's
                        # lock in an outer, unreleased session. A plain
                        # Lock.acquire() below would block forever on
                        # itself, so fail fast instead of self-deadlocking.
                        raise LockOrderError(
                            f"document {document_id} is already locked by "
                            "the current thread; release_locks() must be "
                            "called before it can be re-acquired"
                        )
                lock = self._lock_for(document_id)
                lock.acquire()
                with self._guard:
                    self._held.add(document_id)
                    self._owner[document_id] = current_thread
                acquired.append(document_id)
            yield list(acquired)
        finally:
            if acquired:
                self.release_locks(acquired)

    def release_locks(self, document_ids: Iterable[UUID]) -> None:
        """Release locks for the given document_ids.

        Must be called exactly once per :meth:`acquire_locks` session,
        only after the caller's commit or rollback has fully completed —
        never mid-transaction and never partially (all ids passed to one
        call are released together, in this call, with no early return on
        the first failure: every held id is unlocked even if one entry
        turns out to already be free).

        Releasing a document_id that this coordinator does not currently
        report as held is a no-op for that id: it is not an error, so that
        callers cleaning up in a ``finally`` block after a partial
        acquisition failure can safely pass the full requested set.

        Args:
            document_ids: document_id values to release.
        """
        for document_id in document_ids:
            with self._guard:
                if document_id not in self._held:
                    continue
                self._held.discard(document_id)
                self._owner.pop(document_id, None)
                lock = self._locks.get(document_id)
            if lock is not None and lock.locked():
                lock.release()
