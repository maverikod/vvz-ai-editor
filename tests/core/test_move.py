"""Contract tests for tree_engine.core.move: the structural half of the
atomic subtree move operation (concept C-020, {p009}, {p039}, {p079}).

Covers: UUID4 node_id preservation across both an intra-document move and a
cross-document move, together with the atomic update of parent links,
sibling order, and buffer_range text ranges that comes with it; the
deterministic ascending document_id lock ordering a cross-document move
takes through the real ``DocumentLockCoordinator`` (C-007), paired with a
UUID4 collision reported by the shared preflight validator rejecting the
whole move with ``NODE_ID_CONFLICT`` while leaving both documents
byte-for-byte unchanged; and the target-document short_id reassignment
plan -- a free short_id preserved untouched, a conflicting one reassigned
through the caller-supplied allocator, with the exact old->new remap
returned to the caller.

Deliberately excludes the cross-document reference-conversion outcomes
(the NodeAddress internal/incoming/outgoing rewrites and index-map refresh
of {p080}/{p081}) -- those belong to the sibling test_move_cross_document.py
file, per this step's own scope.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.move import MoveError, MoveResult, move
from tree_engine.core.validation import ShortIdReassignment
from tree_engine.errors import ErrorCode


# ---------------------------------------------------------------------------
# Minimal duck-typed node/document stand-ins, mirrored from test_operations.py
# ---------------------------------------------------------------------------


class _Node:
    def __init__(
        self,
        node_id: Any,
        *,
        short_id: Any = None,
        children: Optional[Sequence["_Node"]] = None,
        parent: Optional["_Node"] = None,
        buffer_range: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self.children: List["_Node"] = list(children) if children else []
        self.parent = parent
        self.buffer_range = buffer_range


class _Document:
    def __init__(self, document_id: Optional[uuid.UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[Any, _Node] = {}
        self.short_id_index: Dict[Any, Any] = {}


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _register(document: _Document, *roots: _Node) -> None:
    stack = list(roots)
    while stack:
        node = stack.pop()
        document.nodes_by_id[node.node_id] = node
        if node.short_id is not None:
            document.short_id_index[node.short_id] = node.node_id
        stack.extend(node.children)


def _snapshot(document: _Document) -> Dict[str, Any]:
    """Snapshot of every node plus both index maps: byte-for-byte proof."""
    nodes = {
        node_id: (
            node.short_id,
            node.parent.node_id if node.parent is not None else None,
            tuple(c.node_id for c in node.children),
            node.buffer_range,
        )
        for node_id, node in document.nodes_by_id.items()
    }
    return {
        "keys": frozenset(document.nodes_by_id.keys()),
        "nodes": nodes,
        "short_id_index": dict(document.short_id_index),
    }


# ---------------------------------------------------------------------------
# UUID4 identity preservation: intra-document and cross-document, plus the
# atomic parent/sibling/buffer_range updates that accompany it.
# ---------------------------------------------------------------------------


def test_move_uuid_preservation_intra_and_cross_document() -> None:
    # --- intra-document move -------------------------------------------
    doc = _Document()
    root = _Node(_id(), buffer_range=(0, 100))
    src_parent = _Node(_id(), parent=root, buffer_range=(0, 40))
    tgt_parent = _Node(_id(), parent=root, buffer_range=(40, 100))
    root.children = [src_parent, tgt_parent]
    moved = _Node(_id(), short_id=1, parent=src_parent, buffer_range=(10, 20))
    other = _Node(_id(), parent=src_parent, buffer_range=(20, 40))
    src_parent.children = [moved, other]
    tgt_child = _Node(_id(), parent=tgt_parent, buffer_range=(40, 100))
    tgt_parent.children = [tgt_child]
    _register(doc, root)

    original_id = moved.node_id
    result = move(doc, moved.node_id, position="last_child", parent=tgt_parent.node_id)

    assert isinstance(result, MoveResult)
    assert moved.node_id == original_id  # UUID4 identity preserved
    assert moved.parent is tgt_parent
    assert [c.node_id for c in tgt_parent.children] == [tgt_child.node_id, moved.node_id]
    assert [c.node_id for c in src_parent.children] == [other.node_id]
    assert src_parent.buffer_range == (0, 30)  # 10-byte moved fragment removed
    assert other.buffer_range == (10, 30)  # later sibling shifted left by 10
    assert doc.nodes_by_id[original_id] is moved
    assert result.removed == (NodeAddress(document_id=doc.document_id, node_id=original_id),)
    assert result.inserted == (NodeAddress(document_id=doc.document_id, node_id=original_id),)

    # --- cross-document move --------------------------------------------
    src_doc = _Document()
    tgt_doc = _Document()
    src_root = _Node(_id(), buffer_range=(0, 50))
    moved2 = _Node(_id(), short_id=5, parent=src_root, buffer_range=(10, 30))
    remaining = _Node(_id(), parent=src_root, buffer_range=(30, 50))
    src_root.children = [moved2, remaining]
    _register(src_doc, src_root)

    tgt_root = _Node(_id(), buffer_range=(0, 20))
    _register(tgt_doc, tgt_root)

    moved2_id = moved2.node_id
    result2 = move(
        src_doc, moved2.node_id, position="last_child",
        target_document=tgt_doc, parent=tgt_root.node_id,
    )

    assert moved2.node_id == moved2_id  # UUID4 identity preserved across the boundary
    assert moved2.parent is tgt_root
    assert tgt_doc.nodes_by_id[moved2_id] is moved2
    assert moved2_id not in src_doc.nodes_by_id
    assert [c.node_id for c in src_root.children] == [remaining.node_id]
    assert src_root.buffer_range == (0, 30)  # 20-byte moved fragment removed
    assert remaining.buffer_range == (10, 30)  # shifted left by 20
    assert result2.removed == (NodeAddress(document_id=src_doc.document_id, node_id=moved2_id),)
    assert result2.inserted == (NodeAddress(document_id=tgt_doc.document_id, node_id=moved2_id),)
    # Same UUID4 both sides -- per {p039} only document_id changes.
    assert result2.removed[0].node_id == result2.inserted[0].node_id
    assert result2.removed[0].document_id != result2.inserted[0].document_id


# ---------------------------------------------------------------------------
# Deterministic ascending lock ordering (via the real DocumentLockCoordinator)
# and NODE_ID_CONFLICT rejection leaving both documents byte-identical.
# ---------------------------------------------------------------------------


def test_move_lock_ordering_and_conflict_rejection() -> None:
    # --- lock ordering: ascending document_id (UUID4), through the real
    # coordinator, regardless of which document happens to sort first -----
    coordinator = DocumentLockCoordinator()
    acquired_orders: List[List[uuid.UUID]] = []

    @contextmanager
    def recording_lock_coordinator(document_ids):
        with coordinator.acquire_locks(document_ids) as acquired:
            acquired_orders.append(list(acquired))
            yield acquired

    src_doc = _Document()
    tgt_doc = _Document()
    # Force the source document_id to sort *after* the target's, so a
    # caller-order (rather than sorted-order) acquisition would be
    # observably descending if lock ordering were not enforced.
    while not src_doc.document_id.int > tgt_doc.document_id.int:
        src_doc = _Document()

    root = _Node(_id(), buffer_range=(0, 10))
    moved = _Node(_id(), parent=root, buffer_range=(0, 10))
    root.children = [moved]
    _register(src_doc, root)

    tgt_root = _Node(_id())
    _register(tgt_doc, tgt_root)

    move(
        src_doc, moved.node_id, position="last_child",
        target_document=tgt_doc, parent=tgt_root.node_id,
        lock_coordinator=recording_lock_coordinator,
    )

    assert len(acquired_orders) == 1
    expected_order = sorted([src_doc.document_id, tgt_doc.document_id], key=lambda d: d.int)
    assert acquired_orders[0] == expected_order
    assert coordinator.is_locked(src_doc.document_id) is False
    assert coordinator.is_locked(tgt_doc.document_id) is False

    # --- NODE_ID_CONFLICT: rejects the whole move, both documents
    # left completely unchanged -------------------------------------------
    conflicting_id = _id()
    src_doc2 = _Document()
    tgt_doc2 = _Document()
    src_root2 = _Node(_id(), buffer_range=(0, 10))
    moved2 = _Node(conflicting_id, short_id=9, parent=src_root2, buffer_range=(0, 10))
    src_root2.children = [moved2]
    _register(src_doc2, src_root2)

    tgt_root2 = _Node(_id())
    colliding_node = _Node(conflicting_id, short_id=99)  # same UUID4, different object
    colliding_node.parent = tgt_root2
    tgt_root2.children = [colliding_node]
    _register(tgt_doc2, tgt_root2)

    before_src = _snapshot(src_doc2)
    before_tgt = _snapshot(tgt_doc2)

    with pytest.raises(MoveError) as excinfo:
        move(
            src_doc2, moved2.node_id, position="last_child",
            target_document=tgt_doc2, parent=tgt_root2.node_id,
        )

    assert [e.code for e in excinfo.value.errors] == [ErrorCode.NODE_ID_CONFLICT]
    assert _snapshot(src_doc2) == before_src
    assert _snapshot(tgt_doc2) == before_tgt
    assert moved2.parent is src_root2  # never detached


# ---------------------------------------------------------------------------
# short_id remap: free values preserved, conflicting ones reassigned, with
# the correct old_short_id -> new_short_id remap returned to the caller.
# ---------------------------------------------------------------------------


def test_move_short_id_remap() -> None:
    src_doc = _Document()
    tgt_doc = _Document()
    src_root = _Node(_id(), buffer_range=(0, 10))
    free_node = _Node(_id(), short_id=7, parent=src_root, buffer_range=(0, 5))
    conflicting_node = _Node(_id(), short_id=3, parent=src_root, buffer_range=(5, 10))
    src_root.children = [free_node, conflicting_node]
    _register(src_doc, src_root)

    tgt_root = _Node(_id())
    existing = _Node(_id(), short_id=3, parent=tgt_root)  # occupies short_id 3 in target
    tgt_root.children = [existing]
    _register(tgt_doc, tgt_root)

    calls = iter([101])
    result = move(
        src_doc, [free_node.node_id, conflicting_node.node_id], position="last_child",
        target_document=tgt_doc, parent=tgt_root.node_id,
        used_short_ids=list(tgt_doc.short_id_index.keys()),
        next_short_id=lambda: next(calls),
    )

    assert free_node.short_id == 7  # free in target: preserved untouched
    assert conflicting_node.short_id == 101  # conflicting: reassigned

    remap_by_node = {entry.node_id: entry for entry in result.remap}
    assert free_node.node_id not in remap_by_node  # a free short_id never appears in the plan
    assert remap_by_node[conflicting_node.node_id] == ShortIdReassignment(
        node_id=conflicting_node.node_id, old_short_id=3, new_short_id=101,
    )

    assert tgt_doc.short_id_index[7] == free_node.node_id
    assert tgt_doc.short_id_index[101] == conflicting_node.node_id
    assert tgt_doc.short_id_index[3] == existing.node_id  # target's own entry untouched
