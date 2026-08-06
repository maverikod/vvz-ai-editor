"""Tests for the short_id lifecycle (concept C-004, {p097}).

Covers :mod:`tree_engine.core.short_id`: the document-local bidirectional
short_id <-> UUID4 node_id map, its monotonic allocator, its 0x-prefixed
hex rendering, and its rekey / bulk-assign / cross-document merge
building blocks.

Per the module's own docstring, ``short_id.py`` is standalone and knows
nothing about tree position, ``NodeAddress``, or ``replace_node_id`` --
those live in sibling modules that use :meth:`ShortIdMap.allocate`,
:meth:`ShortIdMap.release`, and :meth:`ShortIdMap.rekey` as building
blocks. Tests below that describe a "move" or "replace_node_id" from the
{p097} plan prompt are therefore expressed against ``rekey`` (identity
replacement) or against the invariant that unrelated map activity never
disturbs an untouched node's entry (intra-document move).
"""

from __future__ import annotations

import uuid

import pytest

from tree_engine.core.short_id import (
    DuplicateNodeIdError,
    InvalidShortIdHexError,
    ShortIdMap,
    UnknownShortIdError,
    from_hex,
    to_hex,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def short_id_map() -> ShortIdMap:
    """A fresh, empty document-local short_id map."""

    return ShortIdMap()


class TestShortIdMonotonicAllocation:
    def test_allocation_is_monotonic_increasing(self, short_id_map):
        node_ids = [_uuid() for _ in range(5)]
        allocated = [short_id_map.allocate(n) for n in node_ids]

        assert all(isinstance(sid, int) and sid > 0 for sid in allocated)
        assert len(set(allocated)) == len(allocated)
        for prev, nxt in zip(allocated, allocated[1:]):
            assert nxt > prev

    def test_gaps_allowed_after_delete(self, short_id_map):
        node_a, node_b = _uuid(), _uuid()
        short_a = short_id_map.allocate(node_a)
        short_id_map.allocate(node_b)

        short_id_map.release(node_a)
        assert short_id_map.get_node_id(short_a) is None
        assert short_id_map.get_short_id(node_a) is None

        node_c = _uuid()
        short_c = short_id_map.allocate(node_c)
        assert short_c > short_a
        assert short_c != short_a
        # The freed slot stays retired: still never handed out.
        assert short_id_map.get_node_id(short_a) is None

    def test_no_reuse_after_rollback(self, short_id_map):
        kept_nodes = [_uuid(), _uuid()]
        for n in kept_nodes:
            short_id_map.allocate(n)

        snapshot = short_id_map.snapshot()
        undone_node = _uuid()
        undone_short = short_id_map.allocate(undone_node)

        short_id_map.restore(snapshot)
        assert short_id_map.get_short_id(undone_node) is None
        assert short_id_map.get_node_id(undone_short) is None

        node_after = _uuid()
        short_after = short_id_map.allocate(node_after)
        assert short_after != undone_short
        assert short_after > undone_short
        for n in kept_nodes:
            assert short_id_map.get_short_id(n) is not None


class TestShortIdHexRoundTrip:
    def test_short_id_renders_as_0x_prefixed_hex(self, short_id_map):
        node_id = _uuid()
        short_id = short_id_map.allocate(node_id)

        hex_value = to_hex(short_id)
        assert hex_value == f"0x{short_id:x}"
        assert hex_value.startswith("0x")

    def test_hex_round_trips_to_same_uuid(self, short_id_map):
        node_id = _uuid()
        short_id = short_id_map.allocate(node_id)

        hex_value = to_hex(short_id)
        resolved = short_id_map.resolve_hex(hex_value)
        assert resolved == node_id

    @pytest.mark.parametrize("short_id", [1, 15, 16, 255, 256])
    def test_round_trip_for_boundary_values(self, short_id):
        hex_value = to_hex(short_id)
        assert hex_value == f"0x{short_id:x}"
        assert from_hex(hex_value) == short_id

    def test_resolve_hex_unknown_raises(self, short_id_map):
        with pytest.raises(UnknownShortIdError):
            short_id_map.resolve_hex("0x1")

    def test_from_hex_rejects_malformed_input(self):
        with pytest.raises(InvalidShortIdHexError):
            from_hex("1")
        with pytest.raises(InvalidShortIdHexError):
            from_hex("0xzz")


class TestShortIdPreservationOnMove:
    def test_preserved_on_intra_document_move(self, short_id_map):
        # ShortIdMap has no parent/position concept: an intra-document
        # move never calls any of its methods for the moved node, so its
        # entry must be untouched by unrelated map activity around it.
        moved_node = _uuid()
        moved_short = short_id_map.allocate(moved_node)

        other_a, other_b = _uuid(), _uuid()
        short_id_map.allocate(other_a)
        short_id_map.release(other_b)  # no-op: other_b was never in the map

        assert short_id_map.get_short_id(moved_node) == moved_short
        assert short_id_map.get_node_id(moved_short) == moved_node

    def test_preserved_on_replace_node_id(self, short_id_map):
        old_node_id = _uuid()
        new_node_id = _uuid()
        short_id = short_id_map.allocate(old_node_id)

        short_id_map.rekey(old_node_id, new_node_id)

        assert short_id_map.get_short_id(new_node_id) == short_id
        assert short_id_map.get_node_id(short_id) == new_node_id
        assert short_id_map.get_short_id(old_node_id) is None

    def test_rekey_unknown_old_node_raises(self, short_id_map):
        with pytest.raises(UnknownShortIdError):
            short_id_map.rekey(_uuid(), _uuid())

    def test_rekey_onto_existing_node_raises(self, short_id_map):
        node_a, node_b = _uuid(), _uuid()
        short_id_map.allocate(node_a)
        short_id_map.allocate(node_b)
        with pytest.raises(DuplicateNodeIdError):
            short_id_map.rekey(node_a, node_b)


class TestShortIdCopySubtreeReassignment:
    def test_reassigned_on_copy_subtree_new_document(self, short_id_map):
        source_nodes = [_uuid() for _ in range(3)]
        for n in source_nodes:
            short_id_map.allocate(n)

        destination = ShortIdMap()
        assigned = destination.assign_bulk(source_nodes)

        assert set(assigned) == set(source_nodes)
        assigned_shorts = [assigned[n] for n in source_nodes]
        assert assigned_shorts == sorted(assigned_shorts)
        assert len(set(assigned_shorts)) == len(assigned_shorts)
        for n in source_nodes:
            assert destination.get_short_id(n) == assigned[n]
        # next_short_id advanced past every freshly assigned id
        fresh_node = _uuid()
        next_short = destination.allocate(fresh_node)
        assert next_short > max(assigned_shorts)

    def test_source_document_short_ids_unaffected_by_copy(self, short_id_map):
        source_nodes = [_uuid() for _ in range(2)]
        source_before = {n: short_id_map.allocate(n) for n in source_nodes}
        snapshot_before = short_id_map.to_dict()

        destination = ShortIdMap()
        destination.assign_bulk(source_nodes)

        assert short_id_map.to_dict() == snapshot_before
        for n in source_nodes:
            assert short_id_map.get_short_id(n) == source_before[n]


class TestShortIdCrossDocumentInsertion:
    def test_free_short_ids_preserved_on_insertion(self, short_id_map):
        short_id_map.allocate(_uuid())  # occupies short_id 1
        node_x, node_y = _uuid(), _uuid()
        incoming = {node_x: 10, node_y: 11}

        result = short_id_map.merge_insert(incoming)

        assert result == {node_x: 10, node_y: 11}
        assert short_id_map.get_short_id(node_x) == 10
        assert short_id_map.get_node_id(10) == node_x
        assert short_id_map.get_short_id(node_y) == 11
        assert short_id_map.get_node_id(11) == node_y

    def test_conflicting_short_ids_remapped_on_insertion(self, short_id_map):
        existing_node = _uuid()
        existing_short = short_id_map.allocate(existing_node)  # short_id 1

        free_node = _uuid()
        colliding_node = _uuid()
        incoming = {free_node: 50, colliding_node: existing_short}

        result = short_id_map.merge_insert(incoming)

        assert result[free_node] == 50
        assert result[colliding_node] != existing_short
        assert short_id_map.get_node_id(existing_short) == existing_node
        assert short_id_map.get_short_id(colliding_node) == result[colliding_node]

        # next_short_id is consistent: a later allocation never collides
        # with any id already claimed by the merge.
        trailing_node = _uuid()
        trailing_short = short_id_map.allocate(trailing_node)
        assert trailing_short > max(existing_short, 50, result[colliding_node])

    def test_remap_result_is_bijective(self, short_id_map):
        existing_node = _uuid()
        existing_short = short_id_map.allocate(existing_node)

        free_node = _uuid()
        colliding_with_existing = _uuid()
        colliding_with_incoming = _uuid()
        incoming = {
            free_node: 42,
            colliding_with_existing: existing_short,
            colliding_with_incoming: 42,
        }

        short_id_map.merge_insert(incoming)

        entries = short_id_map.to_dict()["entries"]
        node_id_strs = list(entries.values())
        assert len(node_id_strs) == len(set(node_id_strs))
        assert len(entries) == len(set(entries.keys()))
        for short_id_str, node_id_str in entries.items():
            assert short_id_map.get_node_id(int(short_id_str)) == uuid.UUID(
                node_id_str
            )
            assert short_id_map.get_short_id(uuid.UUID(node_id_str)) == int(
                short_id_str
            )
