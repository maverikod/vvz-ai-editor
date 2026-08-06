"""Unit tests for the C-008 reference subsystem.

Covers ``tree_engine.core.references`` (NodeAddress locality/serialization
helpers) and ``tree_engine.core.reference_cache`` (``ReferenceIndex``'s
synchronous index maps and ``CachedObjectRef``'s generation-tracked object
cache), exercised together against the canonical ``NodeAddress`` from
``tree_engine.core.identity``. Only the public API of the three modules is
used; nothing here reaches into private internals.

Three property groups, matching the three source concerns:

* Group 1 -- NodeAddress construction/serialization/parsing ({p080}).
* Group 2 -- synchronous index-map updates, no stale reads ({p042}).
* Group 3 -- generation-tracked object cache ({p084}).

The ``wired`` fixture below builds a minimal in-memory index with two
independent, related local nodes (``node_a`` is ``node_b``'s parent) plus
one external-document node identity that is deliberately never registered
in this index, so both the local and external ``NodeAddress`` paths are
exercised throughout.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest import mock

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.reference_cache import (
    CachedObjectRef,
    ReferenceIndex,
    ReferenceIntegrityError,
)
from tree_engine.core.references import (
    InvalidNodeAddressError,
    is_external,
    is_local,
    node_address_to_string,
    parse_node_address,
)


class _Record:
    """Minimal stand-in node record; only identity (not content) matters."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"_Record({self.label!r})"


def _fresh_ref(address: NodeAddress) -> CachedObjectRef:
    """Build an unresolved cache entry, mirroring a first-ever resolve."""

    return CachedObjectRef(node_address=address, cached_generation=-1, cached_object=None)


@pytest.fixture
def wired() -> Dict[str, Any]:
    """A minimal wired ``ReferenceIndex``: two local nodes, one external id.

    ``node_a`` and ``node_b`` are independent, registered records with
    ``node_b`` parented under ``node_a``. ``external_document_id`` /
    ``external_node_id`` identify a node that lives in a different
    document and is never registered here, so it can only ever be
    addressed via an explicit-document_id (external) ``NodeAddress``.
    """

    index = ReferenceIndex()
    document_id = uuid.uuid4()
    node_a_id = uuid.uuid4()
    node_b_id = uuid.uuid4()
    record_a = _Record("a")
    record_b = _Record("b")
    index.register_node(node_a_id, record_a)
    index.register_node(node_b_id, record_b, parent_id=node_a_id)

    return {
        "index": index,
        "document_id": document_id,
        "node_a_id": node_a_id,
        "node_b_id": node_b_id,
        "record_a": record_a,
        "record_b": record_b,
        "external_document_id": uuid.uuid4(),
        "external_node_id": uuid.uuid4(),
    }


# ---------------------------------------------------------------------------
# Group 1 -- NodeAddress construction/serialization/parsing ({p080})
# ---------------------------------------------------------------------------


def test_node_address_implicit_local_construction(wired: Dict[str, Any]) -> None:
    node_a_id = wired["node_a_id"]
    address = NodeAddress(node_id=node_a_id)

    assert address.document_id is None
    assert is_local(address) is True
    assert is_external(address) is False
    # resolves against the current document's nodes_by_id
    assert address.node_id in wired["index"].nodes_by_id
    assert wired["index"].nodes_by_id[address.node_id].record is wired["record_a"]


def test_node_address_explicit_external_construction(wired: Dict[str, Any]) -> None:
    external_document_id = wired["external_document_id"]
    external_node_id = wired["external_node_id"]
    address = NodeAddress(document_id=external_document_id, node_id=external_node_id)
    local_address = NodeAddress(node_id=wired["node_a_id"])

    assert address.document_id == external_document_id
    assert address.node_id == external_node_id
    assert is_external(address) is True
    assert is_local(address) is False
    # both fields are retained distinctly from a local address
    assert local_address.document_id is None
    assert address.document_id is not None
    assert address != local_address


def test_node_address_serialization_local_vs_external(wired: Dict[str, Any]) -> None:
    document_id = wired["document_id"]
    node_a_id = wired["node_a_id"]
    local_address = NodeAddress(node_id=node_a_id)
    external_address = NodeAddress(
        document_id=wired["external_document_id"], node_id=wired["external_node_id"]
    )
    assert local_address.document_id is None

    local_text = node_address_to_string(local_address, current_document_id=document_id)
    external_text = node_address_to_string(external_address)

    assert local_text == f"{document_id}:{node_a_id}"
    assert external_text == f"{wired['external_document_id']}:{wired['external_node_id']}"
    # the in-memory local form is left untouched by serializing it
    assert local_address.document_id is None


def test_node_address_parsing_roundtrip(wired: Dict[str, Any]) -> None:
    document_id = wired["document_id"]
    node_a_id = wired["node_a_id"]
    local_address = NodeAddress(node_id=node_a_id)
    external_address = NodeAddress(
        document_id=wired["external_document_id"], node_id=wired["external_node_id"]
    )

    local_text = node_address_to_string(local_address, current_document_id=document_id)
    external_text = node_address_to_string(external_address)

    parsed_local = parse_node_address(local_text)
    parsed_external = parse_node_address(external_text)

    assert parsed_local == NodeAddress(document_id=document_id, node_id=node_a_id)
    assert parsed_external == external_address
    assert parsed_local.document_id == document_id
    assert parsed_local.node_id == node_a_id
    assert parsed_external.document_id == wired["external_document_id"]
    assert parsed_external.node_id == wired["external_node_id"]


def test_node_address_parsing_rejects_malformed_uuid() -> None:
    valid_uuid = str(uuid.uuid4())

    with pytest.raises(InvalidNodeAddressError):
        parse_node_address(f"not-a-uuid:{valid_uuid}")
    with pytest.raises(InvalidNodeAddressError):
        parse_node_address(f"{valid_uuid}:not-a-uuid")
    with pytest.raises(InvalidNodeAddressError):
        parse_node_address("not-a-uuid:also-not-a-uuid")


# ---------------------------------------------------------------------------
# Group 2 -- synchronous index-map updates, no stale reads ({p042})
# ---------------------------------------------------------------------------


def test_index_maps_update_after_single_mutation(wired: Dict[str, Any]) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    node_b_id = wired["node_b_id"]
    target_address = NodeAddress(node_id=node_a_id)

    index.update_references(node_b_id, old_targets=[], new_targets=[target_address])

    # outgoing/incoming NodeAddress maps for the affected pair reflect the
    # new state immediately, with no separate refresh/rebuild call.
    assert target_address in index.get_outgoing(node_b_id)
    assert node_b_id in index.get_incoming(node_a_id)
    # id map and parent/child map already reflect the prior registration.
    assert index.get_parent(node_b_id) == node_a_id
    assert node_b_id in index.get_children(node_a_id)
    assert node_a_id in index.nodes_by_id
    assert node_b_id in index.nodes_by_id


def test_index_maps_update_for_each_batch_operation(wired: Dict[str, Any]) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    node_b_id = wired["node_b_id"]
    node_c_id = uuid.uuid4()
    record_c = _Record("c")

    # step 1: register node_c under node_b -- checked right after the call.
    index.register_node(node_c_id, record_c, parent_id=node_b_id)
    assert node_c_id in index.nodes_by_id
    assert node_c_id in index.get_children(node_b_id)

    # step 2: reparent node_c under node_a -- checked right after the call.
    index.reparent(node_c_id, node_a_id)
    assert index.get_parent(node_c_id) == node_a_id
    assert node_c_id in index.get_children(node_a_id)
    assert node_c_id not in index.get_children(node_b_id)

    # step 3: give node_c an outgoing reference to node_b -- checked right
    # after the call.
    address_b = NodeAddress(node_id=node_b_id)
    index.update_references(node_c_id, old_targets=[], new_targets=[address_b])
    assert address_b in index.get_outgoing(node_c_id)
    assert node_c_id in index.get_incoming(node_b_id)


def test_index_map_lookup_after_mutation_uses_direct_index_not_traversal(
    wired: Dict[str, Any]
) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    node_b_id = wired["node_b_id"]
    address_a = NodeAddress(node_id=node_a_id)
    index.update_references(node_b_id, old_targets=[], new_targets=[address_a])

    # get_children is the map a tree-walk would have to call repeatedly;
    # spy on it and prove the direct lookups below never touch it at all.
    with mock.patch.object(
        index, "get_children", wraps=index.get_children
    ) as traversal_spy:
        parent = index.get_parent(node_b_id)
        outgoing = index.get_outgoing(node_b_id)
        entry = index.resolve_node_id(node_b_id)

    assert parent == node_a_id
    assert address_a in outgoing
    assert entry is not None and entry.record is wired["record_b"]
    assert traversal_spy.call_count == 0


def test_batch_partial_failure_leaves_maps_consistent_with_last_applied_step(
    wired: Dict[str, Any]
) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    node_b_id = wired["node_b_id"]
    unregistered_id = uuid.uuid4()

    # step 1 (succeeds).
    address_a = NodeAddress(node_id=node_a_id)
    index.update_references(node_b_id, old_targets=[], new_targets=[address_a])
    generation_after_step_one = index.get_generation(node_b_id)

    # step 2 (fails): the batch goes on to reparent a node_id that was
    # never registered; ReferenceIndex.reparent raises and mutates nothing.
    with pytest.raises(ValueError):
        index.reparent(unregistered_id, node_a_id)

    # the maps reflect exactly the successfully applied step 1: node_b's
    # generation is unchanged by the failed step, and the failed node_id
    # never entered any map.
    assert index.get_generation(node_b_id) == generation_after_step_one
    assert address_a in index.get_outgoing(node_b_id)
    assert unregistered_id not in index.nodes_by_id
    assert unregistered_id not in index.parent_index
    assert unregistered_id not in index.child_index.get(node_a_id, set())


# ---------------------------------------------------------------------------
# Group 3 -- generation-tracked object cache ({p084})
# ---------------------------------------------------------------------------


def test_object_cache_fast_path_hit(wired: Dict[str, Any]) -> None:
    index: ReferenceIndex = wired["index"]
    address = NodeAddress(node_id=wired["node_a_id"])

    ref = _fresh_ref(address)
    first = ref.resolve(index)  # establishes the cache (slow path)

    with mock.patch.object(
        index, "resolve_node_id", wraps=index.resolve_node_id
    ) as resolver_spy:
        second = ref.resolve(index)  # must take the fast path

    assert second is first
    assert second is wired["record_a"]
    assert resolver_spy.call_count == 0


def test_object_cache_generation_mismatch_triggers_reresolution(
    wired: Dict[str, Any]
) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    address = NodeAddress(node_id=node_a_id)

    ref = _fresh_ref(address)
    ref.resolve(index)
    generation_before = ref.cached_generation

    # mutate the target so its generation increments.
    index.update_references(node_a_id, old_targets=[], new_targets=[])
    assert index.get_generation(node_a_id) == generation_before + 1

    with mock.patch.object(
        index, "resolve_node_id", wraps=index.resolve_node_id
    ) as resolver_spy:
        resolved = ref.resolve(index)

    assert resolver_spy.call_count == 1  # re-resolved by UUID4, not cached
    assert resolved is wired["record_a"]
    assert ref.cached_generation == index.get_generation(node_a_id)


def test_object_cache_explicit_integrity_error_on_mismatch(wired: Dict[str, Any]) -> None:
    index: ReferenceIndex = wired["index"]
    node_b_id = wired["node_b_id"]
    address = NodeAddress(node_id=node_b_id)

    ref = _fresh_ref(address)
    ref.resolve(index)

    # corrupt the scenario: the cached target is removed from the index
    # entirely after being cached (e.g. a concurrent deletion elsewhere).
    index.unregister_node(node_b_id)

    with pytest.raises(ReferenceIntegrityError):
        ref.resolve(index)


def test_object_cache_per_target_invalidation_scope(wired: Dict[str, Any]) -> None:
    index: ReferenceIndex = wired["index"]
    node_a_id = wired["node_a_id"]
    node_b_id = wired["node_b_id"]
    address_a = NodeAddress(node_id=node_a_id)
    address_b = NodeAddress(node_id=node_b_id)

    ref_a = _fresh_ref(address_a)
    ref_b = _fresh_ref(address_b)
    ref_a.resolve(index)
    ref_b.resolve(index)
    generation_b_before = ref_b.cached_generation
    object_b_before = ref_b.cached_object

    # mutate only node_a.
    index.update_references(node_a_id, old_targets=[], new_targets=[address_b])

    # the unrelated node_b cache entry is untouched by node_a's mutation.
    assert ref_b.cached_generation == generation_b_before
    assert ref_b.cached_object is object_b_before

    with mock.patch.object(
        index, "resolve_node_id", wraps=index.resolve_node_id
    ) as resolver_spy:
        resolved_b = ref_b.resolve(index)  # still fast path
    assert resolver_spy.call_count == 0
    assert resolved_b is wired["record_b"]

    resolved_a = ref_a.resolve(index)  # re-resolves due to generation bump
    assert resolved_a is wired["record_a"]
    assert ref_a.cached_generation == index.get_generation(node_a_id)
