"""Contract tests for the transactional batch API (concept C-007), per
{p012}, {p035}, {rgi6}: :class:`TransactionBatch` and
:class:`TransactionCoordinator` from ``src/tree_engine/core/transactions.py``.

All test support (node/document stand-ins, snapshot helper, in-batch call
counters) is declared directly in this file.

The coordinator runs every batch against a private, deep-copied overlay of
each touched document, so a node introduced earlier in the same batch is
reachable to a later operation only through the overlay's own
``nodes_by_id`` -- by ``node_id``, never by holding the original Python
object. Every test below addresses parents/siblings by ``node_id`` for
exactly that reason; a live node object in that position does not resolve.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional

import pytest

import tree_engine.core.transactions as transactions_module
from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.transactions import TransactionBatch, TransactionCoordinator, TransactionError
from tree_engine.errors import ErrorCode

_WAIT_TIMEOUT = 10.0
_JOIN_TIMEOUT = 10.0

# -- in-file test support ----------------------------------------------------

class _Node:
    """Duck-typed node stand-in: ``node_id``, ``short_id``, a settable
    ``children`` sequence, a ``parent`` back-link."""

    def __init__(self, node_id: Any, *, short_id: Any = None, children: Optional[List["_Node"]] = None) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self._children: List["_Node"] = list(children) if children else []
        self.parent: Optional["_Node"] = None
        self.buffer_range = None
        for child in self._children:
            child.parent = self

    @property
    def children(self) -> List["_Node"]:
        return self._children

    @children.setter
    def children(self, value: Any) -> None:
        self._children = list(value)

class _Document:
    """Duck-typed document stand-in: ``nodes_by_id``, ``short_id_index``,
    ``document_id``, ``root``, an int ``document_version`` counter."""

    def __init__(self, *, root: _Node, document_id: Optional[Any] = None, document_version: int = 0) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.root = root
        self.nodes_by_id: Dict[Any, _Node] = {}
        self.short_id_index: Dict[Any, Any] = {}
        self.document_version = document_version
        _register(self, root)

def _id() -> uuid.UUID:
    return uuid.uuid4()

def _register(document: _Document, root: _Node) -> None:
    stack = [root]
    while stack:
        node = stack.pop()
        document.nodes_by_id[node.node_id] = node
        if node.short_id is not None:
            document.short_id_index[node.short_id] = node.node_id
        stack.extend(node.children)

def _make_document(root: _Node, *, document_version: int = 0) -> _Document:
    return _Document(root=root, document_version=document_version)

def _snapshot(document: _Document) -> Dict[str, Any]:
    """Deep, order-preserving snapshot of every node, both index maps, and
    the public version -- proves byte-identical state across a failed or
    rolled-back batch."""
    nodes = {
        node_id: (
            node.short_id,
            node.parent.node_id if node.parent is not None else None,
            tuple(c.node_id for c in node.children),
        )
        for node_id, node in document.nodes_by_id.items()
    }
    return {
        "keys": frozenset(document.nodes_by_id.keys()),
        "nodes": nodes,
        "short_id_index": dict(document.short_id_index),
        "document_version": document.document_version,
        "root_children": tuple(c.node_id for c in document.root.children),
    }

class _CountingValidator:
    """Wraps the real ``validate_mutation``, counting calls routed through
    it. Installed in place of ``transactions_module.validate_mutation`` --
    the module's own imported name, used solely by its closing {p016}
    full-document check -- so it counts exactly those calls, never the
    separate calls ``operations.py`` makes through its own reference."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return self._real(*args, **kwargs)

class _TracedLock:
    """Wraps a real per-document lock, recording the document_id whose
    lock is acquired through it, in order, into a shared guarded list."""

    def __init__(self, inner: Any, document_id: Any, trace: List[Any], guard: threading.Lock) -> None:
        self._inner = inner
        self._document_id = document_id
        self._trace = trace
        self._guard = guard

    def acquire(self, *args: Any, **kwargs: Any) -> bool:
        result = self._inner.acquire(*args, **kwargs)
        if result:
            with self._guard:
                self._trace.append(self._document_id)
        return result

    def release(self) -> None:
        self._inner.release()

    def locked(self) -> bool:
        return self._inner.locked()

def _install_tracer(lock_coordinator: DocumentLockCoordinator) -> List[Any]:
    """Monkeypatch ``lock_coordinator._lock_for`` (instance attribute
    only) so its real internal acquisition order becomes observable."""
    original_lock_for = lock_coordinator._lock_for
    trace: List[Any] = []
    guard = threading.Lock()

    def traced_lock_for(document_id: Any) -> Any:
        return _TracedLock(original_lock_for(document_id), document_id, trace, guard)

    lock_coordinator._lock_for = traced_lock_for
    return trace

def _pause_call(monkeypatch: pytest.MonkeyPatch, name: str):
    """Monkeypatch ``transactions_module.<name>`` so its first call blocks
    until the returned ``release`` event is set, signalling the returned
    ``entered`` event the instant it is reached. Lets a test observe the
    live document from another thread while a batch is paused mid-flight,
    without any bare-sleep race."""
    entered = threading.Event()
    release = threading.Event()
    real = getattr(transactions_module, name)

    def paused(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(timeout=_WAIT_TIMEOUT)
        return real(*args, **kwargs)

    monkeypatch.setattr(transactions_module, name, paused)
    return entered, release

def _run_in_thread(coordinator: TransactionCoordinator, documents: Dict[Any, _Document], batch: TransactionBatch):
    """Run ``coordinator.execute`` on a background thread, capturing its
    return value under ``outcome["result"]`` or a raised exception under
    ``outcome["error"]``. Caller starts/joins the returned thread."""
    outcome: Dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = coordinator.execute(documents, batch)
        except Exception as exc:
            outcome["error"] = exc

    return threading.Thread(target=run), outcome

# -- tests --------------------------------------------------------------

def test_in_batch_visibility_sees_prior_operations() -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    node_a, node_b, node_c = _Node(_id(), short_id="A"), _Node(_id(), short_id="B"), _Node(_id(), short_id="C")

    batch = (
        TransactionBatch(document_id=document.document_id)
        .insert(node_a, position="last_child", parent=root.node_id)
        .insert(node_b, position="after", sibling=node_a.node_id)
        .insert(node_c, position="after", sibling=node_b.node_id)
    )
    result = coordinator.execute({document.document_id: document}, batch)

    # After commit, document.root is the published overlay clone, not the
    # original `root` object: operations only ever mutate the overlay.
    assert [c.node_id for c in document.root.children] == [node_a.node_id, node_b.node_id, node_c.node_id]
    assert result.results[1].position == 1
    assert result.results[2].position == 2

def test_external_reader_isolation_during_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    new_node = _Node(_id(), short_id="NEW")
    entered, release = _pause_call(monkeypatch, "insert")

    batch = TransactionBatch(document_id=document.document_id).insert(new_node, position="last_child", parent=root.node_id)
    worker, outcome = _run_in_thread(coordinator, {document.document_id: document}, batch)
    worker.start()
    assert entered.wait(timeout=_WAIT_TIMEOUT)

    # Paused mid-flight, before the closing check/commit: an external read
    # of the live document must show only the pre-batch state.
    assert new_node.node_id not in document.nodes_by_id
    assert document.document_version == 0

    release.set()
    worker.join(timeout=_JOIN_TIMEOUT)
    assert not worker.is_alive()
    assert "result" in outcome
    assert new_node.node_id in document.nodes_by_id
    assert document.document_version == 1

def test_commit_advances_version_exactly_once() -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    nodes = [_Node(_id(), short_id=f"N{i}") for i in range(4)]

    batch = TransactionBatch(document_id=document.document_id)
    for node in nodes:
        batch.insert(node, position="last_child", parent=root.node_id)
    result = coordinator.execute({document.document_id: document}, batch)

    assert document.document_version == 1
    assert result.document_versions[document.document_id] == (0, 1)
    assert len(result.results) == 4

def test_rollback_discards_all_batch_changes() -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    good_node = _Node(_id(), short_id="GOOD")
    before = _snapshot(document)

    batch = (
        TransactionBatch(document_id=document.document_id)
        .insert(good_node, position="last_child", parent=root.node_id)
        .delete("does-not-exist")  # unresolvable target: raises before any write
    )
    with pytest.raises(Exception):
        coordinator.execute({document.document_id: document}, batch)

    assert _snapshot(document) == before
    assert good_node.node_id not in document.nodes_by_id
    assert good_node.short_id not in document.short_id_index

def test_rollback_forbids_partial_publication(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    node_a = _Node(_id(), short_id="A")
    before = _snapshot(document)
    entered, release = _pause_call(monkeypatch, "delete")

    batch = (
        TransactionBatch(document_id=document.document_id)
        .insert(node_a, position="last_child", parent=root.node_id)
        .delete("does-not-exist")
    )
    worker, outcome = _run_in_thread(coordinator, {document.document_id: document}, batch)
    worker.start()
    assert entered.wait(timeout=_WAIT_TIMEOUT)

    # op 1 already ran against the private overlay; the live document must
    # still be untouched while the batch is paused mid-flight.
    assert _snapshot(document) == before

    release.set()
    worker.join(timeout=_JOIN_TIMEOUT)
    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), Exception)
    assert _snapshot(document) == before

def test_single_post_batch_control_check(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root)
    coordinator = TransactionCoordinator()
    nodes = [_Node(_id(), short_id=f"N{i}") for i in range(3)]
    counter = _CountingValidator(transactions_module.validate_mutation)
    monkeypatch.setattr(transactions_module, "validate_mutation", counter)

    batch = TransactionBatch(document_id=document.document_id)
    for node in nodes:
        batch.insert(node, position="last_child", parent=root.node_id)
    coordinator.execute({document.document_id: document}, batch)

    assert counter.calls == 1

def test_expected_version_checked_at_batch_start(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root, document_version=5)
    coordinator = TransactionCoordinator()
    node = _Node(_id(), short_id="N")
    before = _snapshot(document)
    call_count = {"n": 0}
    real_insert = transactions_module.insert

    def counting_insert(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        return real_insert(*args, **kwargs)

    monkeypatch.setattr(transactions_module, "insert", counting_insert)
    batch = TransactionBatch(
        document_id=document.document_id,
        expected_versions={document.document_id: 4},  # stale: current is 5
    ).insert(node, position="last_child", parent=root.node_id)

    with pytest.raises(TransactionError) as excinfo:
        coordinator.execute({document.document_id: document}, batch)

    assert excinfo.value.code == ErrorCode.DOCUMENT_VERSION_CONFLICT
    assert call_count["n"] == 0
    assert _snapshot(document) == before

def test_multi_document_batch_uses_lock_coordinator_ordering() -> None:
    doc_a = _make_document(_Node(_id(), short_id="ROOT_A"))
    doc_b = _make_document(_Node(_id(), short_id="ROOT_B"))
    doc_c = _make_document(_Node(_id(), short_id="ROOT_C"))
    documents = {d.document_id: d for d in (doc_a, doc_b, doc_c)}
    expected_order = sorted(documents.keys(), key=lambda d: d.int)

    lock_coordinator = DocumentLockCoordinator()
    trace = _install_tracer(lock_coordinator)
    coordinator = TransactionCoordinator(lock_coordinator=lock_coordinator)

    batch = (
        TransactionBatch(document_id=doc_a.document_id)
        .insert(_Node(_id(), short_id="A"), position="last_child", parent=doc_a.root.node_id)
        .insert(_Node(_id(), short_id="B"), position="last_child", parent=doc_b.root.node_id, document_id=doc_b.document_id)
        .insert(_Node(_id(), short_id="C"), position="last_child", parent=doc_c.root.node_id, document_id=doc_c.document_id)
    )
    coordinator.execute(documents, batch)

    assert trace == expected_order
    for document_id in documents:
        assert not lock_coordinator.is_locked(document_id)

def test_no_automatic_merge_of_concurrent_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _Node(_id(), short_id="ROOT")
    document = _make_document(root, document_version=0)
    coordinator = TransactionCoordinator()
    node = _Node(_id(), short_id="N")
    entered, release = _pause_call(monkeypatch, "insert")

    batch = TransactionBatch(
        document_id=document.document_id,
        expected_versions={document.document_id: 0},
    ).insert(node, position="last_child", parent=root.node_id)
    worker, outcome = _run_in_thread(coordinator, {document.document_id: document}, batch)
    worker.start()
    assert entered.wait(timeout=_WAIT_TIMEOUT)

    # An out-of-band write that bypasses the coordinator entirely, made
    # while the batch is in flight -- already past the batch-start
    # expected_version check, still holding the document's lock.
    document.document_version = 7

    release.set()
    worker.join(timeout=_JOIN_TIMEOUT)
    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), TransactionError)
    assert outcome["error"].code == ErrorCode.CONCURRENT_TREE_MODIFICATION
    assert node.node_id not in document.nodes_by_id
    assert document.document_version == 7  # left exactly as the bypass set it: never auto-merged
