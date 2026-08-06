"""Unit tests for tree_engine.core.integrity and tree_engine.core.integrity_full.

Scoped to the properties that matter for concept C-008's two ReferenceIntegrity
validators:

* the local check (:func:`~tree_engine.core.integrity.validate_after_mutation`)
  is SCOPE-BOUNDED -- its cost must not grow with total tree size -- and it
  detects broken parent/child symmetry, a stale direct-object cache entry, and
  a missing backlink, while never mutating the index it inspects, on either
  the success or the failure path;
* the full check (:func:`~tree_engine.core.integrity_full.validate_full_document`)
  additionally catches duplicate identifiers (node_id and short_id), an
  unresolvable local address, and a parent/child cycle, while treating a
  syntactically valid address into a simply-unloaded external document as
  legal, whether or not a resolver is supplied.

Builds minimal :class:`~tree_engine.core.reference_cache.ReferenceIndex`
instances directly (its maps are public per its own docstring) rather than a
full ``Document`` facade, except where the uniqueness check specifically
needs a raw ``root`` node graph. Corruption scenarios are induced by writing
directly to the index's public dict/set attributes -- the same "duck-typed
tree" surface the validators themselves read -- never by calling into
private helpers of the modules under test.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.integrity import IntegrityError, validate_after_mutation
from tree_engine.core.integrity_full import FullIntegrityError, validate_full_document
from tree_engine.core.nodes import make_node
from tree_engine.core.reference_cache import CachedObjectRef, ReferenceIndex

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _Record:
    """Minimal node record: only carries what the validators may read."""

    def __init__(self, label: str, cached_refs: Any = None) -> None:
        self.label = label
        self.cached_refs = cached_refs


class _Document:
    """Minimal document facade: a ReferenceIndex plus an optional root graph."""

    def __init__(self, reference_index: ReferenceIndex, root: Any = None) -> None:
        self.reference_index = reference_index
        if root is not None:
            self.root = root


def _register(
    index: ReferenceIndex,
    parent_id: Optional[uuid.UUID] = None,
    *,
    cached_refs: Any = None,
    short_id: Optional[int] = None,
) -> uuid.UUID:
    node_id = uuid.uuid4()
    index.register_node(
        node_id,
        _Record(label=str(node_id), cached_refs=cached_refs),
        parent_id=parent_id,
        short_id=short_id,
    )
    return node_id


def _build_branching_tree(depth: int, branching: int) -> Tuple[ReferenceIndex, List[uuid.UUID]]:
    """Register a full ``branching``-ary tree of ``depth`` levels below a root.

    Returns the populated index and the list of node ids at the deepest
    level (leaves), so a test can validate one of them regardless of how
    large the rest of the tree is.
    """

    index = ReferenceIndex()
    root_id = _register(index)
    frontier = [root_id]
    for _ in range(depth):
        next_frontier: List[uuid.UUID] = []
        for parent_id in frontier:
            for _ in range(branching):
                next_frontier.append(_register(index, parent_id=parent_id))
        frontier = next_frontier
    return index, frontier


def _generations(index: ReferenceIndex) -> Dict[uuid.UUID, int]:
    return {node_id: entry.generation for node_id, entry in index.nodes_by_id.items()}


def _structure_snapshot(index: ReferenceIndex) -> Tuple[Any, ...]:
    return (
        set(index.nodes_by_id),
        {k: frozenset(v) for k, v in index.child_index.items()},
        dict(index.parent_index),
        {k: frozenset(v) for k, v in index.outgoing_refs.items()},
        {k: frozenset(v) for k, v in index.incoming_refs.items()},
        _generations(index),
    )


# ---------------------------------------------------------------------------
# Local validator: scope boundedness
# ---------------------------------------------------------------------------


def test_validate_after_mutation_scope_size_independent_of_tree_size() -> None:
    """Checked-scope size must stay flat while total tree size grows ~100x.

    Depth grows the tree, not the mutated leaf's own parent fan-out (a wide
    single-parent fan-out is a legitimately in-scope cost, not a scope leak,
    so it is deliberately avoided here -- see module docstring).
    """

    small_index, small_leaves = _build_branching_tree(depth=2, branching=3)
    large_index, large_leaves = _build_branching_tree(depth=5, branching=4)

    assert len(small_index.nodes_by_id) == 1 + 3 + 9
    assert len(large_index.nodes_by_id) == 1 + 4 + 16 + 64 + 256 + 1024
    assert len(large_index.nodes_by_id) > 100 * len(small_index.nodes_by_id)

    small_summary = validate_after_mutation(small_index, [small_leaves[0]])
    large_summary = validate_after_mutation(large_index, [large_leaves[0]])

    # Leaf + its parent, in both cases -- unaffected by the ~100x size gap.
    assert small_summary.checked_nodes == 2
    assert large_summary.checked_nodes == 2
    assert small_summary.checked_references == 0
    assert large_summary.checked_references == 0


# ---------------------------------------------------------------------------
# Local validator: failure semantics, each proven non-mutating on top
# ---------------------------------------------------------------------------


def test_validate_after_mutation_detects_broken_parent_child_symmetry() -> None:
    index = ReferenceIndex()
    root_id = _register(index)
    child_id = _register(index, parent_id=root_id)

    # Corrupt: child_index[root] no longer lists child, parent_index[child]
    # still points at root -- classic broken symmetry.
    index.child_index[root_id].discard(child_id)
    before = _structure_snapshot(index)

    with pytest.raises(IntegrityError) as excinfo:
        validate_after_mutation(index, [child_id])
    assert excinfo.value.check == "symmetry"
    assert _structure_snapshot(index) == before


def test_validate_after_mutation_detects_stale_cache() -> None:
    index = ReferenceIndex()
    target_id = _register(index)
    cache_ref = CachedObjectRef.create(index, NodeAddress(node_id=target_id))
    source_id = _register(index, cached_refs=cache_ref)

    # Bump target's generation without touching the cache -- it goes stale.
    index.update_references(target_id, [], [])
    before = _structure_snapshot(index)

    with pytest.raises(IntegrityError) as excinfo:
        validate_after_mutation(index, [source_id])
    assert excinfo.value.check == "cache-conformance"
    assert _structure_snapshot(index) == before


def test_validate_after_mutation_detects_missing_backlink() -> None:
    index = ReferenceIndex()
    target_id = _register(index)
    source_id = _register(index)

    # Add the outgoing edge directly, bypassing update_references, so
    # incoming_refs at the target is never populated.
    index.outgoing_refs[source_id].add(NodeAddress(node_id=target_id))
    before = _structure_snapshot(index)

    with pytest.raises(IntegrityError) as excinfo:
        validate_after_mutation(index, [source_id])
    assert excinfo.value.check == "backlink"
    assert _structure_snapshot(index) == before


def test_validate_after_mutation_commits_and_never_mutates_on_healthy_change() -> None:
    index = ReferenceIndex()
    root_id = _register(index)
    child_id = _register(index)
    index.reparent(child_id, root_id)
    before = _structure_snapshot(index)

    summary = validate_after_mutation(index, [child_id])

    assert summary.checked_nodes == 2
    assert summary.checked_references == 0
    assert summary.checked_caches == 0
    assert _structure_snapshot(index) == before


# ---------------------------------------------------------------------------
# Full validator: uniqueness (duplicate node_id, duplicate short_id)
# ---------------------------------------------------------------------------


def test_full_validator_detects_duplicate_uuid_and_short_id() -> None:
    dup_id = uuid.uuid4()
    leaf_a = dataclasses.replace(make_node("Leaf", {}, ()), node_id=dup_id)
    leaf_b = dataclasses.replace(make_node("Leaf", {}, ()), node_id=dup_id)
    root = make_node("Root", {}, (leaf_a, leaf_b))
    document = _Document(reference_index=ReferenceIndex(), root=root)

    with pytest.raises(FullIntegrityError) as excinfo:
        validate_full_document(document)
    checks = {check for check, _message in excinfo.value.violations}
    assert checks == {"uniqueness"}

    index = ReferenceIndex()
    _register(index, short_id=1)
    node_b = _register(index, short_id=2)
    index.node_id_to_short_id[node_b] = 1  # corrupt: now shares short_id 1

    with pytest.raises(FullIntegrityError) as excinfo:
        validate_full_document(index)
    checks = {check for check, _message in excinfo.value.violations}
    assert checks == {"uniqueness"}


# ---------------------------------------------------------------------------
# Full validator: local resolvability
# ---------------------------------------------------------------------------


def test_full_validator_detects_unresolvable_local_reference() -> None:
    index = ReferenceIndex()
    source_id = _register(index)
    missing_id = uuid.uuid4()
    index.update_references(source_id, [], [NodeAddress(node_id=missing_id)])

    with pytest.raises(FullIntegrityError) as excinfo:
        validate_full_document(index)
    checks = {check for check, _message in excinfo.value.violations}
    assert checks == {"local-resolvability"}


def test_full_validator_passes_when_local_references_resolve() -> None:
    index = ReferenceIndex()
    source_id = _register(index)
    target_id = _register(index)
    index.update_references(source_id, [], [NodeAddress(node_id=target_id)])

    report = validate_full_document(index)

    assert report.nodes_checked == 2
    assert report.external_references_checked == 0
    assert report.unresolved_external == ()


# ---------------------------------------------------------------------------
# Full validator: external resolvability, with and without a resolver
# ---------------------------------------------------------------------------


def test_full_validator_external_reference_with_resolver() -> None:
    index = ReferenceIndex()
    source_id = _register(index)
    doc_ok, target_ok = uuid.uuid4(), uuid.uuid4()
    doc_missing, target_missing = uuid.uuid4(), uuid.uuid4()
    doc_unloaded, target_unloaded = uuid.uuid4(), uuid.uuid4()
    index.outgoing_refs[source_id].update(
        {
            NodeAddress(document_id=doc_ok, node_id=target_ok),
            NodeAddress(document_id=doc_missing, node_id=target_missing),
            NodeAddress(document_id=doc_unloaded, node_id=target_unloaded),
        }
    )

    def resolver(document_id: uuid.UUID) -> Optional[Dict[uuid.UUID, Any]]:
        if document_id == doc_ok:
            return {target_ok: object()}
        if document_id == doc_missing:
            return {}  # loaded, but does not contain target_missing
        return None  # doc_unloaded: simply not loaded -- legal per {p083}

    with pytest.raises(FullIntegrityError) as excinfo:
        validate_full_document(index, resolver=resolver)

    assert len(excinfo.value.violations) == 1
    check, message = excinfo.value.violations[0]
    assert check == "external-address"
    assert str(target_missing) in message


def test_full_validator_external_reference_unloaded_without_resolver_is_legal() -> None:
    index = ReferenceIndex()
    source_id = _register(index)
    address = NodeAddress(document_id=uuid.uuid4(), node_id=uuid.uuid4())
    index.outgoing_refs[source_id].add(address)

    report = validate_full_document(index)  # no resolver supplied at all

    assert report.external_references_checked == 1
    assert report.unresolved_external == (address,)


# ---------------------------------------------------------------------------
# Full validator: cycle detection
# ---------------------------------------------------------------------------


def test_full_validator_cycle_detection() -> None:
    index = ReferenceIndex()
    node_a = _register(index)
    node_b = _register(index, parent_id=node_a)
    node_c = _register(index, parent_id=node_b)

    # Same shape, acyclic: A -> B -> C. Must pass first.
    report = validate_full_document(index)
    assert report.nodes_checked == 3

    # Corrupt into a cycle: A -> B -> C -> A.
    index.reparent(node_a, node_c)

    with pytest.raises(FullIntegrityError) as excinfo:
        validate_full_document(index)
    checks = {check for check, _message in excinfo.value.violations}
    assert "cycle" in checks
