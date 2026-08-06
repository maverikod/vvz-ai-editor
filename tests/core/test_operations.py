"""Contract tests for tree_engine.core.operations: insert, delete, and
replace_range (concept C-006, {p010}, {p107}, {p108}).

Covers: every {p107} insert addressing mode with both short_id- and
UUID4-based reference normalization; delete of a single node, a contiguous
range, and a subtree, asserting parent links, sibling order, and
buffer_range; a rejected non-contiguous delete target; replace_range's
one-combined-splice atomicity (no intermediate range-missing state) and
its removed/inserted/remap result; and, per operation, a preflight (or
resolution) failure that leaves the tree and both index maps unchanged.

Deliberately excludes the reparse pipeline and any attribute, body,
source-fragment, or identifier update -- those belong to sibling files.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.operations import MutationError, delete, insert, replace_range
from tree_engine.core.validation import ShortIdReassignment
from tree_engine.errors import ErrorCode


# Minimal duck-typed node/document stand-ins


class _Node:
    """Node stand-in. ``children``'s setter logs every reassignment in
    ``children_writes``, proving an operation wrote it exactly once (atomic
    splice), never mid-way through a rejected call. Fixtures assign
    ``_children`` directly (bypassing the setter) so the log is empty right
    before the call under test."""

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
        self._children: List["_Node"] = list(children) if children else []
        self.parent = parent
        self.buffer_range = buffer_range
        self.children_writes: List[Tuple[Any, ...]] = []

    @property
    def children(self) -> List["_Node"]:
        return self._children

    @children.setter
    def children(self, value: Sequence["_Node"]) -> None:
        self._children = list(value)
        self.children_writes.append(tuple(n.node_id for n in self._children))


class _Document:
    def __init__(self, document_id: Optional[uuid.UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[Any, _Node] = {}
        self.short_id_index: Dict[Any, Any] = {}


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _register(document: _Document, *roots: _Node) -> None:
    """Register each root and its whole subtree, as a loader would first."""
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
            tuple(node.children_writes),
        )
        for node_id, node in document.nodes_by_id.items()
    }
    return {
        "keys": frozenset(document.nodes_by_id.keys()),
        "nodes": nodes,
        "short_id_index": dict(document.short_id_index),
    }


def _addr(document: _Document, node: _Node) -> NodeAddress:
    return NodeAddress(document_id=document.document_id, node_id=node.node_id)


# insert: every {p107} addressing mode, both reference-normalization forms


class TestInsertPositionalAddressingAndShortIdNormalization:
    def test_all_four_addressing_modes_with_mixed_reference_forms(self) -> None:
        parent = _Node(_id(), short_id="P")
        node_a = _Node(_id(), short_id="A", parent=parent)
        node_b = _Node(_id(), short_id="B", parent=parent)
        parent._children = [node_a, node_b]
        document = _Document()
        _register(document, parent)

        # first_child -- parent normalized from a short_id
        node_x = _Node(_id(), short_id="X")
        result_x = insert(document, node_x, position="first_child", parent="P")
        assert [c.node_id for c in parent.children] == [node_x.node_id, node_a.node_id, node_b.node_id]
        assert node_x.parent is parent
        assert result_x.position == 0
        assert result_x.node_id == node_x.node_id
        assert result_x.inserted == (_addr(document, node_x),)

        # last_child -- parent normalized from a UUID4
        node_y = _Node(_id(), short_id="Y")
        result_y = insert(document, node_y, position="last_child", parent=parent.node_id)
        assert [c.node_id for c in parent.children][-1] == node_y.node_id
        assert result_y.position == 3

        # child_index -- parent normalized from a short_id
        node_z = _Node(_id(), short_id="Z")
        result_z = insert(document, node_z, position="child_index", index=2, parent="P")
        assert [c.node_id for c in parent.children] == [
            node_x.node_id, node_a.node_id, node_z.node_id, node_b.node_id, node_y.node_id,
        ]
        assert result_z.position == 2

        # before -- sibling normalized from a UUID4, parent implied from it
        node_w = _Node(_id(), short_id="W")
        result_w = insert(document, node_w, position="before", sibling=node_a.node_id)
        ids = [c.node_id for c in parent.children]
        assert ids[ids.index(node_w.node_id) + 1] == node_a.node_id
        assert result_w.position == ids.index(node_w.node_id)

        # after -- sibling normalized from a short_id, parent implied from it
        node_v = _Node(_id(), short_id="V")
        result_v = insert(document, node_v, position="after", sibling="B")
        ids = [c.node_id for c in parent.children]
        assert ids[ids.index(node_b.node_id) + 1] == node_v.node_id
        assert result_v.position == ids.index(node_b.node_id) + 1

        for n in (node_x, node_y, node_z, node_w, node_v):
            assert document.nodes_by_id[n.node_id] is n
            assert document.short_id_index[n.short_id] == n.node_id


# delete: single node, contiguous range, subtree; rejected non-contiguous set


class TestDeleteSingleRangeAndSubtreeUpdates:
    def test_delete_single_node_updates_links_order_and_ranges(self) -> None:
        parent = _Node(_id(), buffer_range=(0, 20))
        a = _Node(_id(), parent=parent, buffer_range=(0, 5))
        b = _Node(_id(), parent=parent, buffer_range=(5, 10))
        c = _Node(_id(), parent=parent, buffer_range=(10, 20))
        parent._children = [a, b, c]
        document = _Document()
        _register(document, parent)

        result = delete(document, b.node_id)

        assert [n.node_id for n in parent.children] == [a.node_id, c.node_id]
        assert parent.buffer_range == (0, 15)
        assert a.buffer_range == (0, 5)
        assert c.buffer_range == (5, 15)
        assert b.parent is None
        assert b.node_id not in document.nodes_by_id
        assert result.position == 1
        assert result.removed == (_addr(document, b),)
        assert result.inserted == ()

    def test_delete_contiguous_sibling_range(self) -> None:
        parent = _Node(_id(), buffer_range=(0, 20))
        a = _Node(_id(), parent=parent, buffer_range=(0, 5))
        b = _Node(_id(), parent=parent, buffer_range=(5, 10))
        c = _Node(_id(), parent=parent, buffer_range=(10, 15))
        d = _Node(_id(), parent=parent, buffer_range=(15, 20))
        parent._children = [a, b, c, d]
        document = _Document()
        _register(document, parent)

        result = delete(document, [b.node_id, c.node_id])

        assert [n.node_id for n in parent.children] == [a.node_id, d.node_id]
        assert parent.buffer_range == (0, 10)
        assert a.buffer_range == (0, 5)
        assert d.buffer_range == (5, 10)
        assert b.node_id not in document.nodes_by_id
        assert c.node_id not in document.nodes_by_id
        assert result.removed == (_addr(document, b), _addr(document, c))

    def test_delete_subtree_purges_every_descendant(self) -> None:
        parent = _Node(_id(), buffer_range=(0, 30))
        keep = _Node(_id(), parent=parent, buffer_range=(0, 10))
        mid = _Node(_id(), parent=parent, buffer_range=(10, 25))
        g1 = _Node(_id(), parent=mid, buffer_range=(11, 15), short_id="G1")
        g2 = _Node(_id(), parent=mid, buffer_range=(15, 24), short_id="G2")
        mid._children = [g1, g2]
        after = _Node(_id(), parent=parent, buffer_range=(25, 30))
        parent._children = [keep, mid, after]
        document = _Document()
        _register(document, parent)

        result = delete(document, mid.node_id)

        assert [n.node_id for n in parent.children] == [keep.node_id, after.node_id]
        assert parent.buffer_range == (0, 15)
        assert after.buffer_range == (10, 15)
        for removed in (mid, g1, g2):
            assert removed.node_id not in document.nodes_by_id
        assert "G1" not in document.short_id_index
        assert "G2" not in document.short_id_index
        assert mid.parent is None
        assert result.removed == (_addr(document, mid),)

    def test_delete_rejects_noncontiguous_targets_and_leaves_tree_unchanged(self) -> None:
        parent = _Node(_id(), buffer_range=(0, 15))
        a = _Node(_id(), parent=parent, buffer_range=(0, 5))
        b = _Node(_id(), parent=parent, buffer_range=(5, 10))
        c = _Node(_id(), parent=parent, buffer_range=(10, 15))
        parent._children = [a, b, c]
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)

        with pytest.raises(MutationError) as excinfo:
            delete(document, [a.node_id, c.node_id])  # skips b: not contiguous

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_POSITION]
        assert _snapshot(document) == before


# replace_range: one-combined-splice atomicity and removed/inserted/remap shape


class TestReplaceRangeAtomicityAndResultShape:
    def test_only_the_intended_span_changes_in_one_combined_splice(self) -> None:
        parent = _Node(_id(), short_id="P")
        a = _Node(_id(), short_id="A", parent=parent)
        b = _Node(_id(), short_id="B", parent=parent)
        c = _Node(_id(), short_id="C", parent=parent)
        d = _Node(_id(), short_id="D", parent=parent)
        parent._children = [a, b, c, d]
        document = _Document()
        _register(document, parent)

        new_1 = _Node(_id(), short_id="N1")
        new_2 = _Node(_id(), short_id="N2")

        result = replace_range(document, [b.node_id, c.node_id], [new_1, new_2])

        assert [n.node_id for n in parent.children] == [a.node_id, new_1.node_id, new_2.node_id, d.node_id]
        assert parent.children[0] is a and parent.children[-1] is d
        assert new_1.parent is parent and new_2.parent is parent

        # exactly one children write: the combined splice -- no state where
        # b/c are gone and nothing yet replaces them is ever observable.
        assert parent.children_writes == [(a.node_id, new_1.node_id, new_2.node_id, d.node_id)]

        assert b.node_id not in document.nodes_by_id
        assert c.node_id not in document.nodes_by_id
        assert document.nodes_by_id[new_1.node_id] is new_1
        assert document.nodes_by_id[new_2.node_id] is new_2

        assert result.removed == (_addr(document, b), _addr(document, c))
        assert result.inserted == (_addr(document, new_1), _addr(document, new_2))
        assert isinstance(result.remap, tuple)
        assert result.position == 1

    def test_remap_carries_reassigned_short_ids_from_every_incoming_root(self) -> None:
        parent = _Node(_id(), short_id="P")
        only_child = _Node(_id(), short_id="ONLY", parent=parent)
        parent._children = [only_child]
        document = _Document()
        _register(document, parent)

        conflicting = _Node(_id(), short_id="ONLY")  # collides with only_child's short_id
        fresh = _Node(_id())  # arrives without a short_id at all
        calls = iter([777, 778])

        result = replace_range(
            document, only_child.node_id, [conflicting, fresh],
            used_short_ids=["ONLY"], next_short_id=lambda: next(calls),
        )

        by_node = {entry.node_id: entry for entry in result.remap}
        assert by_node[conflicting.node_id] == ShortIdReassignment(
            node_id=conflicting.node_id, old_short_id="ONLY", new_short_id=777
        )
        assert by_node[fresh.node_id] == ShortIdReassignment(node_id=fresh.node_id, old_short_id=None, new_short_id=778)
        assert conflicting.short_id == 777
        assert fresh.short_id == 778
        assert result.removed == (_addr(document, only_child),)
        assert result.inserted == (_addr(document, conflicting), _addr(document, fresh))


# every operation: a preflight/resolution failure leaves the tree and index
# maps byte-for-byte unchanged


class TestOperationsValidationFailureLeavesStateUnchanged:
    def test_insert_rejects_type_incompatible_node_without_mutating_tree(self) -> None:
        parent = _Node(_id(), short_id="P")
        a = _Node(_id(), short_id="A", parent=parent)
        parent._children = [a]
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)

        incoming = _Node(_id())
        with pytest.raises(MutationError) as excinfo:
            insert(
                document, incoming, position="last_child", parent=parent.node_id,
                is_type_compatible=lambda p, pos, n: False,
            )

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_PARENT_TYPE]
        assert incoming.node_id not in document.nodes_by_id
        assert incoming.parent is None
        assert _snapshot(document) == before

    def test_insert_rejects_unresolvable_parent_reference_without_mutating_tree(self) -> None:
        parent = _Node(_id())
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)
        incoming = _Node(_id())

        with pytest.raises(MutationError) as excinfo:
            insert(document, incoming, position="last_child", parent="does-not-exist")

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.NODE_NOT_FOUND]
        assert _snapshot(document) == before

    def test_delete_rejects_unresolvable_target_without_mutating_tree(self) -> None:
        parent = _Node(_id(), short_id="P")
        a = _Node(_id(), short_id="A", parent=parent)
        parent._children = [a]
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)

        with pytest.raises(MutationError) as excinfo:
            delete(document, "unknown-short-id")

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.NODE_NOT_FOUND]
        assert _snapshot(document) == before

    def test_replace_range_rejects_preflight_failure_on_any_incoming_root_without_mutating_anything(self) -> None:
        parent = _Node(_id(), short_id="P")
        a = _Node(_id(), short_id="A", parent=parent)
        parent._children = [a]
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)

        good = _Node(_id())
        bad = _Node("not-a-uuid4")  # fails the preflight validator's UUID4 check
        with pytest.raises(MutationError) as excinfo:
            replace_range(document, a.node_id, [good, bad])

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_SELECTOR]
        assert good.node_id not in document.nodes_by_id
        assert a.node_id in document.nodes_by_id
        assert _snapshot(document) == before

    def test_replace_range_rejects_same_batch_node_id_collision_without_mutating_anything(self) -> None:
        parent = _Node(_id(), short_id="P")
        a = _Node(_id(), short_id="A", parent=parent)
        parent._children = [a]
        document = _Document()
        _register(document, parent)
        before = _snapshot(document)

        shared_id = _id()
        first = _Node(shared_id)
        second = _Node(shared_id)  # repeats first's node_id within the batch

        with pytest.raises(MutationError) as excinfo:
            replace_range(document, a.node_id, [first, second])

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.NODE_ID_CONFLICT]
        assert _snapshot(document) == before
