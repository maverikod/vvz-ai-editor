"""Contract tests for DocumentLockCoordinator concurrency and locking
protocol (concept C-007, {p035}).

Covers per-document serialization under concurrent callers, ascending-UUID4
multi-document lock ordering, deadlock freedom under interleaved
multi-document transactions, lock release on the commit/rollback/exception
paths, and the blocking behavior of a thread contending for an already-held
document lock.

Every threading test synchronizes on events and joins with generous
timeouts rather than a bare sleep race, so results stay deterministic
regardless of machine load; a short ``time.sleep`` is only ever used to
widen a contention window for a guarded counter, never as the sole proof
of correctness.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import List

import pytest

from tree_engine.core.locking import DocumentLockCoordinator

_JOIN_TIMEOUT = 10.0
_WAIT_TIMEOUT = 10.0


class _TracedLock:
    """Wraps a real per-document lock, recording -- into a shared, guarded
    list -- the document_id whose lock is acquired through it, in the exact
    order acquisition happens. Used to observe the coordinator's actual
    internal acquisition order without altering its behavior."""

    def __init__(self, inner, document_id: uuid.UUID, trace: List[uuid.UUID], guard: threading.Lock) -> None:
        self._inner = inner
        self._document_id = document_id
        self._trace = trace
        self._guard = guard

    def acquire(self, *args, **kwargs) -> bool:
        result = self._inner.acquire(*args, **kwargs)
        if result:
            with self._guard:
                self._trace.append(self._document_id)
        return result

    def release(self) -> None:
        self._inner.release()

    def locked(self) -> bool:
        return self._inner.locked()


def _install_tracer(coordinator: DocumentLockCoordinator) -> List[uuid.UUID]:
    """Monkeypatch ``coordinator._lock_for`` (an instance attribute only --
    the module file itself is never touched) so the next ``acquire_locks``
    call(s) on this coordinator record their real internal acquisition
    order into the returned trace list. Safe to call repeatedly on the same
    coordinator: it always wraps the pristine, un-traced method, never a
    previously installed wrapper, so traces from separate calls never
    stack or bleed into each other."""
    pristine = getattr(coordinator, "_pristine_lock_for_for_tests", None)
    if pristine is None:
        pristine = coordinator._lock_for
        coordinator._pristine_lock_for_for_tests = pristine

    trace: List[uuid.UUID] = []
    guard = threading.Lock()

    def traced_lock_for(document_id):
        inner = pristine(document_id)
        return _TracedLock(inner, document_id, trace, guard)

    coordinator._lock_for = traced_lock_for
    return trace


def _reacquire_promptly(coordinator: DocumentLockCoordinator, document_id: uuid.UUID) -> bool:
    """True iff a separate thread can acquire document_id's now-released
    lock promptly -- used after a commit/rollback/exception release to
    confirm the lock is genuinely free, not merely reported as such."""
    acquired_event = threading.Event()

    def worker() -> None:
        with coordinator.acquire_locks([document_id]):
            acquired_event.set()

    t = threading.Thread(target=worker)
    t.start()
    ok = acquired_event.wait(timeout=_WAIT_TIMEOUT)
    t.join(timeout=_JOIN_TIMEOUT)
    return ok and not t.is_alive()


class TestDocumentLockCoordinator:
    # 1. per-document serialization -------------------------------------

    def test_per_document_serialization_concurrent_threads(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_id = uuid.uuid4()
        guard = threading.Lock()
        active = 0
        max_active = 0
        errors: List[BaseException] = []

        def worker() -> None:
            nonlocal active, max_active
            try:
                with coordinator.acquire_locks([document_id]):
                    with guard:
                        active += 1
                        max_active = max(max_active, active)
                    time.sleep(0.02)
                    with guard:
                        active -= 1
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_JOIN_TIMEOUT)

        assert not any(t.is_alive() for t in threads), "a thread failed to finish"
        assert not errors
        assert max_active == 1
        assert not coordinator.is_locked(document_id)

    # 2. ascending UUID4 multi-document lock order -----------------------

    def test_multi_document_lock_order_ascending_uuid(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_ids = [uuid.uuid4() for _ in range(6)]
        expected = sorted(document_ids, key=lambda d: d.int)
        request_orders = [
            list(reversed(document_ids)),
            document_ids[::2] + document_ids[1::2],
            [document_ids[3], document_ids[0], document_ids[5], document_ids[1], document_ids[4], document_ids[2]],
        ]

        for order in request_orders:
            trace = _install_tracer(coordinator)
            with coordinator.acquire_locks(order) as acquired:
                assert acquired == expected
            assert trace == expected
            for document_id in document_ids:
                assert not coordinator.is_locked(document_id)

    # 3. no deadlock across interleaved multi-document transactions ------

    def test_no_deadlock_interleaved_multi_document_transactions(self) -> None:
        coordinator = DocumentLockCoordinator()
        a, b, c, d = (uuid.uuid4() for _ in range(4))
        combos = [
            [a, b], [b, a], [b, c], [c, b], [c, d], [d, c],
            [a, d], [d, a], [a, b, c, d], [d, c, b, a],
        ]
        errors: List[BaseException] = []
        completed: List[List[uuid.UUID]] = []
        completed_guard = threading.Lock()

        def worker(ids: List[uuid.UUID]) -> None:
            try:
                with coordinator.acquire_locks(ids):
                    time.sleep(0.01)
                with completed_guard:
                    completed.append(ids)
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(combo,)) for combo in combos for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20.0)

        assert not any(t.is_alive() for t in threads), "deadlock: a thread never finished"
        assert not errors
        assert len(completed) == len(threads)
        for document_id in (a, b, c, d):
            assert not coordinator.is_locked(document_id)

    # 4. lock release after commit ----------------------------------------

    def test_lock_release_after_commit(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_id = uuid.uuid4()

        with coordinator.acquire_locks([document_id]):
            pass  # simulated successful commit: normal exit

        assert not coordinator.is_locked(document_id)
        assert _reacquire_promptly(coordinator, document_id)

    # 5. lock release after rollback --------------------------------------

    def test_lock_release_after_rollback(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_id = uuid.uuid4()
        published = {"value": "original"}

        with coordinator.acquire_locks([document_id]):
            working_copy = dict(published)
            working_copy["value"] = "modified"
            # simulated rollback: the working copy is discarded and never
            # published; the block still exits normally (no exception).

        assert published == {"value": "original"}
        assert not coordinator.is_locked(document_id)
        assert _reacquire_promptly(coordinator, document_id)

    # 6. lock release on the exception path --------------------------------

    def test_lock_release_on_exception_path(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_ids = [uuid.uuid4(), uuid.uuid4()]

        class _SimulatedFailure(Exception):
            pass

        with pytest.raises(_SimulatedFailure):
            with coordinator.acquire_locks(document_ids):
                raise _SimulatedFailure("failure raised during commit/rollback")

        for document_id in document_ids:
            assert not coordinator.is_locked(document_id)
            assert _reacquire_promptly(coordinator, document_id)

    # 7. a single-document operation blocks until the lock frees up --------

    def test_single_document_operation_waits_for_lock(self) -> None:
        coordinator = DocumentLockCoordinator()
        document_id = uuid.uuid4()
        holder_acquired = threading.Event()
        waiter_attempting = threading.Event()
        release_signal = threading.Event()
        order: List[str] = []
        order_guard = threading.Lock()

        def holder() -> None:
            with coordinator.acquire_locks([document_id]):
                with order_guard:
                    order.append("holder_acquired")
                holder_acquired.set()
                release_signal.wait(timeout=_WAIT_TIMEOUT)
            with order_guard:
                order.append("holder_released")

        def waiter() -> None:
            assert holder_acquired.wait(timeout=_WAIT_TIMEOUT)
            waiter_attempting.set()
            with coordinator.acquire_locks([document_id]):
                with order_guard:
                    order.append("waiter_acquired")

        t_holder = threading.Thread(target=holder)
        t_waiter = threading.Thread(target=waiter)
        t_holder.start()
        assert holder_acquired.wait(timeout=_WAIT_TIMEOUT)
        assert coordinator.is_locked(document_id)

        t_waiter.start()
        assert waiter_attempting.wait(timeout=_WAIT_TIMEOUT)
        time.sleep(0.2)  # generous window for the waiter to reach the blocking acquire
        with order_guard:
            assert order == ["holder_acquired"], "waiter must still be blocked on the held lock"

        release_signal.set()
        t_holder.join(timeout=_JOIN_TIMEOUT)
        t_waiter.join(timeout=_JOIN_TIMEOUT)
        assert not t_holder.is_alive() and not t_waiter.is_alive()
        assert order[0] == "holder_acquired"
        assert "waiter_acquired" in order
        assert not coordinator.is_locked(document_id)

    # 8. mixed single- and multi-document operations ------------------------

    def test_concurrent_single_and_multi_document_operations(self) -> None:
        coordinator = DocumentLockCoordinator()
        docs = [uuid.uuid4() for _ in range(5)]
        errors: List[BaseException] = []
        completed = 0
        completed_guard = threading.Lock()

        def run(ids: List[uuid.UUID]) -> None:
            nonlocal completed
            try:
                with coordinator.acquire_locks(ids):
                    time.sleep(0.005)
                with completed_guard:
                    completed += 1
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        jobs: List[List[uuid.UUID]] = [[doc] for doc in docs]
        jobs.append([docs[0], docs[1], docs[2]])
        jobs.append([docs[2], docs[1], docs[0]])
        jobs.append([docs[1], docs[3], docs[4]])
        jobs.append(list(reversed(docs)))
        jobs = jobs * 3

        threads = [threading.Thread(target=run, args=(job,)) for job in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20.0)

        assert not any(t.is_alive() for t in threads)
        assert not errors
        assert completed == len(threads)
        for doc in docs:
            assert not coordinator.is_locked(doc)
