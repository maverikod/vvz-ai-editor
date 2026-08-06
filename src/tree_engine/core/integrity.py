"""Local post-mutation reference-integrity validator (concept C-008).

Scope (concept C-008, narrowed to *local* post-mutation validation only):
this module owns exactly one entry point, :func:`validate_after_mutation`,
that the core mutation and batch-operation surface must call after each
individual operation is applied -- including every operation inside a
batch -- to confirm the reference subsystem is still internally consistent
around the just-changed part of the tree, per {p081}/{p082}.

Per {p082}, this validator's scope is strictly bounded: the changed nodes,
their immediate structural neighbours (parent + direct children), the
``NodeAddress`` references touched by the mutation, and the index-map
entries just updated for those nodes. It never walks the whole tree, and
its cost never grows with total tree size -- only with the size of the
touched neighbourhood. On any mismatch the caller's operation is
considered unsuccessful and must be fully rolled back by the caller; this
module performs no mutation and no recovery of its own, in any code path.

This module owns none of the heavier machinery it checks: the index maps
and the generation-tracked direct-object cache are owned by the sibling
``core/reference_cache.py`` (:class:`~tree_engine.core.reference_cache.ReferenceIndex`,
:class:`~tree_engine.core.reference_cache.CachedObjectRef`), and the
canonical ``NodeAddress``/locality helpers are owned by
``core/identity.py`` and ``core/references.py``. This file imports and
reuses their public API and reimplements none of it. Full-document
validation (global id/short_id uniqueness, external resolver checks,
cycle detection, version consistency), performed before export/generate/
storage handoff per {p083}, is out of scope here and belongs to the
separate integrity-full step.

Duck-typed ``tree`` contract, mirroring the rest of this package: ``tree``
is either a :class:`~tree_engine.core.reference_cache.ReferenceIndex`
instance itself, or any object exposing one through a ``reference_index``
attribute -- the shape a later tree/document facade is expected to use.
A node record registered in the index may optionally expose a
``cached_refs`` attribute -- a single
:class:`~tree_engine.core.reference_cache.CachedObjectRef` or an iterable
of them -- naming the direct-object cache entries that node currently
holds; nodes without such an attribute simply contribute no cache checks.

Source-of-truth requirement labels honored here: {p080}, {p081}, {p082},
{p084}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Set, Tuple, Union
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.reference_cache import CachedObjectRef, ReferenceIndex
from tree_engine.core.references import is_local

__all__ = ["IntegrityError", "ValidationSummary", "validate_after_mutation"]

#: One touched outgoing reference, either as a bare target address (source
#: unknown to the caller) or as an explicit ``(source_node_id, address)``
#: pair -- the shape :meth:`ReferenceIndex.update_references` diffs into.
TouchedReference = Union[NodeAddress, Tuple[UUID, NodeAddress]]


class IntegrityError(Exception):
    """Raised by :func:`validate_after_mutation` on the first failing check.

    ``check`` names which local check failed -- one of ``"symmetry"``,
    ``"cache-conformance"``, ``"backlink"``, or ``"local-resolvability"`` --
    and ``message`` names the specific offending node(s)/reference(s), so a
    caller can log/diagnose without re-deriving the failure from scratch.
    Raising this error means the module found the inconsistency; rolling
    the just-applied operation back is entirely the caller's
    responsibility.
    """

    def __init__(self, check: str, message: str) -> None:
        self.check = check
        super().__init__(f"[{check}] {message}")


@dataclass(frozen=True)
class ValidationSummary:
    """Small, informational success result of :func:`validate_after_mutation`.

    Counts describe how much the call actually touched, so a caller (or a
    test) can confirm the scope stayed bounded: ``checked_nodes`` is the
    size of the structural scope, ``checked_references`` is the number of
    distinct touched-reference edges examined, and ``checked_caches`` is
    the number of direct-object cache entries examined.
    """

    checked_nodes: int
    checked_references: int
    checked_caches: int


@dataclass
class _Scope:
    """The bounded set of nodes/edges a single call must examine ({p082})."""

    node_ids: Set[UUID] = field(default_factory=set)
    # Edges with a known source: (source_node_id, target_address).
    outgoing_edges: Set[Tuple[UUID, NodeAddress]] = field(default_factory=set)
    # Edges recorded the other way: (target_node_id, source_node_id).
    incoming_edges: Set[Tuple[UUID, UUID]] = field(default_factory=set)
    # Touched addresses whose source the caller did not name.
    loose_addresses: Set[NodeAddress] = field(default_factory=set)


def _index_of(tree: Any) -> ReferenceIndex:
    """Resolve ``tree`` to the :class:`ReferenceIndex` it exposes.

    Duck-typed: only presence of ``nodes_by_id`` is checked directly;
    every other attribute access below fails naturally with
    ``AttributeError`` if ``tree`` does not actually implement the
    ReferenceIndex API.
    """

    candidate = getattr(tree, "reference_index", tree)
    if not hasattr(candidate, "nodes_by_id"):
        raise TypeError(
            "tree must be a ReferenceIndex, or expose one via a "
            "'reference_index' attribute"
        )
    return candidate


def _normalize_touched(
    touched_references: Optional[Iterable[TouchedReference]],
) -> Iterable[Tuple[Optional[UUID], NodeAddress]]:
    for item in touched_references or ():
        if isinstance(item, NodeAddress):
            yield None, item
        else:
            source_id, address = item
            yield source_id, address


def _scope_from_changed_nodes(
    index: ReferenceIndex,
    changed_node_ids: Iterable[UUID],
    touched_references: Optional[Iterable[TouchedReference]] = None,
) -> _Scope:
    """Build the {p082}-bounded scope for one ``validate_after_mutation`` call."""

    changed_ids = list(dict.fromkeys(changed_node_ids))
    scope = _Scope(node_ids=set(changed_ids))

    # Immediate structural neighbours: parent + direct children only.
    for node_id in changed_ids:
        parent_id = index.get_parent(node_id)
        if parent_id is not None:
            scope.node_ids.add(parent_id)
        scope.node_ids.update(index.get_children(node_id))

    # References touched by the mutation: outgoing/incoming edges of the
    # changed nodes themselves, as already recorded in the updated index.
    for node_id in changed_ids:
        for address in index.get_outgoing(node_id):
            scope.outgoing_edges.add((node_id, address))
        for source_id in index.get_incoming(node_id):
            scope.incoming_edges.add((node_id, source_id))

    # Caller-supplied touched references, additive and equally bounded
    # (their count is fixed by the mutation, never by tree size).
    for source_id, address in _normalize_touched(touched_references):
        if source_id is not None:
            scope.node_ids.add(source_id)
            scope.outgoing_edges.add((source_id, address))
        else:
            scope.loose_addresses.add(address)
        if is_local(address):
            scope.node_ids.add(address.node_id)

    return scope


def _check_parent_child_symmetry(index: ReferenceIndex, scope: _Scope) -> None:
    for node_id in scope.node_ids:
        parent_id = index.get_parent(node_id)
        if parent_id is not None and node_id not in index.get_children(parent_id):
            raise IntegrityError(
                "symmetry",
                f"node {node_id} records parent {parent_id}, but "
                f"{parent_id}'s child_index does not list {node_id} back",
            )
        for child_id in index.get_children(node_id):
            recorded_parent = index.get_parent(child_id)
            if recorded_parent != node_id:
                raise IntegrityError(
                    "symmetry",
                    f"node {node_id} lists child {child_id}, but "
                    f"{child_id}'s parent_index points to "
                    f"{recorded_parent!r} instead of {node_id}",
                )


def _iter_cached_refs(record: Any) -> Tuple[CachedObjectRef, ...]:
    refs = getattr(record, "cached_refs", None)
    if refs is None:
        return ()
    if isinstance(refs, CachedObjectRef):
        return (refs,)
    return tuple(refs)


def _check_cache_conformance(index: ReferenceIndex, scope: _Scope) -> int:
    """Fast-path-check every cache entry attached to a node in scope.

    Reuses :class:`CachedObjectRef`'s own fast-path condition ({p084}) by
    reading its two public fields directly, and reuses
    :meth:`ReferenceIndex.resolve_node_id` for the read-only UUID4
    re-resolution -- never :meth:`CachedObjectRef.resolve`, which would
    mutate the entry and violate this module's read-only contract. A
    fast-path mismatch is never silently accepted: it always raises,
    whether or not the target still resolves elsewhere.
    """

    checked = 0
    for node_id in scope.node_ids:
        entry = index.nodes_by_id.get(node_id)
        if entry is None:
            continue
        for cache_ref in _iter_cached_refs(entry.record):
            checked += 1
            target_id = cache_ref.node_address.node_id
            live_entry = index.nodes_by_id.get(target_id)
            fast_path_ok = (
                live_entry is not None
                and live_entry.generation == cache_ref.cached_generation
                and live_entry.record is cache_ref.cached_object
            )
            if fast_path_ok:
                continue

            resolved_entry = index.resolve_node_id(target_id)
            if resolved_entry is None:
                raise IntegrityError(
                    "cache-conformance",
                    f"node {node_id}'s cached_object for "
                    f"{cache_ref.node_address!r} cannot be re-resolved: "
                    f"{target_id} is not present in the reference index",
                )
            raise IntegrityError(
                "cache-conformance",
                f"node {node_id}'s cached_object for "
                f"{cache_ref.node_address!r} is stale "
                f"(cached_generation={cache_ref.cached_generation}, "
                f"live generation={resolved_entry.generation}); a stale "
                "cache is never silently accepted",
            )
    return checked


def _check_backlinks(index: ReferenceIndex, scope: _Scope) -> None:
    """Check backlink symmetry for edges whose endpoints both resolve.

    An edge naming a target/source not present in ``nodes_by_id`` at all
    is not a backlink-symmetry question -- it is caught, with its own
    dedicated diagnosis, by :func:`_check_local_resolvability` instead.
    """

    for source_id, address in scope.outgoing_edges:
        if not is_local(address) or address.node_id not in index.nodes_by_id:
            continue
        if source_id not in index.get_incoming(address.node_id):
            raise IntegrityError(
                "backlink",
                f"outgoing reference {source_id} -> {address.node_id} has "
                f"no matching incoming_refs entry at {address.node_id}",
            )
    for target_id, source_id in scope.incoming_edges:
        if source_id not in index.nodes_by_id:
            continue
        outgoing_targets = {
            addr.node_id for addr in index.get_outgoing(source_id) if is_local(addr)
        }
        if target_id not in outgoing_targets:
            raise IntegrityError(
                "backlink",
                f"incoming reference at {target_id} claims source "
                f"{source_id}, but {source_id}'s outgoing_refs has no "
                f"matching NodeAddress back to {target_id}",
            )


def _check_local_resolvability(index: ReferenceIndex, scope: _Scope) -> None:
    addresses = {addr for _source_id, addr in scope.outgoing_edges}
    addresses.update(scope.loose_addresses)
    for address in addresses:
        if not is_local(address):
            continue  # external addresses are out of scope here ({p081}/{p083}).
        if address.node_id not in index.nodes_by_id:
            raise IntegrityError(
                "local-resolvability",
                f"local reference to {address.node_id} does not resolve: "
                f"{address.node_id} is not present in nodes_by_id",
            )


def validate_after_mutation(
    tree: Any,
    changed_node_ids: Iterable[UUID],
    touched_references: Optional[Iterable[TouchedReference]] = None,
) -> ValidationSummary:
    """Validate the tree's reference subsystem around one applied mutation.

    The single entry point the core mutation and batch-operation surface
    must call after each individual operation is applied, including every
    operation inside a batch ({p081}, {p082}). Runs, in order, on the
    {p082}-bounded scope derived from ``changed_node_ids`` (see module
    docstring): parent/child symmetry, direct-object cache conformance,
    backlink correctness, and local resolvability. Raises
    :class:`IntegrityError` on the first failing check; performs no
    mutation, in any code path, whether it succeeds or fails.

    ``touched_references`` optionally supplements the scope with
    references the caller knows were touched but that ``changed_node_ids``
    alone would not surface (e.g. edges recorded by a call to
    :meth:`ReferenceIndex.update_references`); it accepts either a bare
    :class:`NodeAddress` or an explicit ``(source_node_id, NodeAddress)``
    pair.

    Returns a :class:`ValidationSummary` on success.
    """

    index = _index_of(tree)
    scope = _scope_from_changed_nodes(index, changed_node_ids, touched_references)

    _check_parent_child_symmetry(index, scope)
    checked_caches = _check_cache_conformance(index, scope)
    _check_backlinks(index, scope)
    _check_local_resolvability(index, scope)

    checked_references = len(scope.outgoing_edges) + len(scope.incoming_edges) + len(
        scope.loose_addresses
    )
    return ValidationSummary(
        checked_nodes=len(scope.node_ids),
        checked_references=checked_references,
        checked_caches=checked_caches,
    )
