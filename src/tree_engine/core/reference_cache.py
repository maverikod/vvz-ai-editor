"""In-memory reference index and generation-tracked object cache (C-008).

Scope (concept C-008, narrowed to the index/object-cache primitives only):
this module owns two things and nothing else.

1. :class:`ReferenceIndex` — the in-memory bidirectional index maps
   (identity, short_id, parent/child structure, outgoing/incoming
   ``NodeAddress`` references) and their synchronous, per-operation update
   API. Per {p042} and {p081}, every applied mutation — including each
   individual operation inside a batch — must update the maps for the
   affected nodes/edges immediately, before any following lookup or
   mutation runs; resolution is always direct ``dict`` access, never tree
   traversal. Every mutation that touches a node's identity, structure, or
   references bumps that node's own integer generation counter.
2. :class:`CachedObjectRef` — a derived direct-object reference cache
   entry. Per {p080}/{p084}, ``NodeAddress`` is the sole canonical source
   of truth; a cached object is only an accelerating derivative that is
   valid exactly while its recorded generation matches the target's
   current generation in the index AND the cached object is (identity)
   the live record held there. Otherwise it is re-resolved by UUID4, or
   :class:`ReferenceIntegrityError` is raised when the target cannot be
   found. Invalidation is strictly per-target: mutating one node's record
   must never force re-resolution of caches pointing at unrelated nodes.

Out of scope here, delivered by sibling atomic steps under G-013/T-001:
node identity/addressing itself (``core/identity.py``), the reference
string-form helpers (``core/references.py``), local post-mutation
validation, and full-document validation. This module performs no I/O and
defines no export/generate hooks or validators of its own; it is pure
in-memory bookkeeping plus the resolve API described above.

Source-of-truth requirement labels honored here: {p042}, {p080}, {p081},
{p084}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Optional, Set
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.references import is_local

__all__ = [
    "ReferenceIntegrityError",
    "NodeEntry",
    "ReferenceIndex",
    "CachedObjectRef",
]


class ReferenceIntegrityError(Exception):
    """Raised by :meth:`CachedObjectRef.resolve` on an explicit integrity failure.

    Covers exactly the case where a ``NodeAddress`` cannot be re-resolved
    to a live record through the :class:`ReferenceIndex` — its
    ``node_id`` is simply absent from ``nodes_by_id``. Never raised for a
    successful fast-path or slow-path resolution, and never raised by
    :class:`ReferenceIndex`'s own update API, which only maintains maps
    and never judges resolvability.
    """


@dataclass
class NodeEntry:
    """One ``nodes_by_id`` record: the live node object plus its generation.

    Deliberately mutable and exposed as a plain attribute-bearing object
    (not frozen) so that direct dict access — ``index.nodes_by_id[id]`` —
    is the only operation either side of the cache contract ever needs,
    per {p042}'s "no tree traversal" rule. ``record`` is whatever node
    object the caller registered; this module does not constrain its
    type. ``generation`` starts at ``0`` and is incremented by
    :class:`ReferenceIndex` on every mutation that touches this node's
    identity, structure, or references, per {p084}.
    """

    node_id: UUID
    record: Any
    generation: int = 0


class ReferenceIndex:
    """Synchronously maintained in-memory reference/structure index.

    All maps below are public attributes, not accessors, precisely so
    that resolution and (in tests) inspection is always a direct O(1)
    dict/set operation:

    * ``nodes_by_id``: ``node_id -> NodeEntry`` (record + generation).
    * ``short_id_to_node_id`` / ``node_id_to_short_id``: bidirectional
      document-local short_id map.
    * ``parent_index``: ``child_id -> parent_id``.
    * ``child_index``: ``parent_id -> set of child_id``.
    * ``outgoing_refs``: ``node_id -> set of NodeAddress`` it references.
    * ``incoming_refs``: ``target node_id -> set of referencing node_id``,
      populated only for local targets (``is_local``): an external
      ``NodeAddress`` names a node_id that belongs to another document's
      own index, so this index never records it as an incoming edge.

    Every method below mutates only the entries for the nodes/edges it is
    actually told about, and returns only after those maps are fully
    consistent — there is no deferred rebuild step, per {p042}/{p081}.
    """

    def __init__(self) -> None:
        self.nodes_by_id: Dict[UUID, NodeEntry] = {}
        self.short_id_to_node_id: Dict[int, UUID] = {}
        self.node_id_to_short_id: Dict[UUID, int] = {}
        self.parent_index: Dict[UUID, UUID] = {}
        self.child_index: Dict[UUID, Set[UUID]] = {}
        self.outgoing_refs: Dict[UUID, Set[NodeAddress]] = {}
        self.incoming_refs: Dict[UUID, Set[UUID]] = {}

    # -- registration ---------------------------------------------------

    def register_node(
        self,
        node_id: UUID,
        record: Any,
        *,
        parent_id: Optional[UUID] = None,
        short_id: Optional[int] = None,
    ) -> None:
        """Register a new node at generation 0 and index its edges.

        Raises ``ValueError`` if ``node_id`` is already registered, or if
        ``short_id`` collides with one already in use. On any failure
        nothing is mutated.
        """

        if node_id in self.nodes_by_id:
            raise ValueError(f"node_id already registered: {node_id!r}")
        if short_id is not None and short_id in self.short_id_to_node_id:
            raise ValueError(f"short_id already in use: {short_id!r}")

        self.nodes_by_id[node_id] = NodeEntry(node_id=node_id, record=record)
        self.outgoing_refs[node_id] = set()

        if short_id is not None:
            self.short_id_to_node_id[short_id] = node_id
            self.node_id_to_short_id[node_id] = short_id

        if parent_id is not None:
            self.parent_index[node_id] = parent_id
            self.child_index.setdefault(parent_id, set()).add(node_id)

    def unregister_node(self, node_id: UUID) -> None:
        """Remove a node and every index entry that names it.

        Detaches it from its parent's child set, drops its short_id
        mapping, discards its outgoing references (mirroring each removal
        into the target's ``incoming_refs``), and drops any
        ``incoming_refs`` entry recorded under this node_id as a target.
        Raises ``ValueError`` if ``node_id`` is not registered.
        """

        if node_id not in self.nodes_by_id:
            raise ValueError(f"node_id not registered: {node_id!r}")

        parent_id = self.parent_index.pop(node_id, None)
        if parent_id is not None:
            self._discard_child(parent_id, node_id)
        self.child_index.pop(node_id, None)

        short_id = self.node_id_to_short_id.pop(node_id, None)
        if short_id is not None:
            self.short_id_to_node_id.pop(short_id, None)

        targets = self.outgoing_refs.pop(node_id, set())
        for target in targets:
            if is_local(target):
                self._discard_incoming(target.node_id, node_id)

        self.incoming_refs.pop(node_id, None)
        del self.nodes_by_id[node_id]

    # -- structural mutation ---------------------------------------------

    def reparent(self, node_id: UUID, new_parent_id: UUID) -> None:
        """Move ``node_id`` to ``new_parent_id`` and bump its generation.

        Updates ``parent_index`` and both the old and new ``child_index``
        entries synchronously, in this call, before returning. Raises
        ``ValueError`` if ``node_id`` is not registered.
        """

        if node_id not in self.nodes_by_id:
            raise ValueError(f"node_id not registered: {node_id!r}")

        old_parent_id = self.parent_index.get(node_id)
        if old_parent_id is not None:
            self._discard_child(old_parent_id, node_id)

        self.parent_index[node_id] = new_parent_id
        self.child_index.setdefault(new_parent_id, set()).add(node_id)
        self._bump_generation(node_id)

    def update_references(
        self,
        node_id: UUID,
        old_targets: Iterable[NodeAddress],
        new_targets: Iterable[NodeAddress],
    ) -> None:
        """Replace ``node_id``'s outgoing references and bump its generation.

        ``old_targets`` is the previously registered set (as returned by
        :attr:`outgoing_refs` before the call); ``new_targets`` is the
        full replacement set. Only the symmetric difference is touched:
        removed local targets lose ``node_id`` from their
        ``incoming_refs`` entry, added local targets gain it, both within
        this same call, per {p081}. Raises ``ValueError`` if ``node_id``
        is not registered.
        """

        if node_id not in self.nodes_by_id:
            raise ValueError(f"node_id not registered: {node_id!r}")

        old_set = set(old_targets)
        new_set = set(new_targets)

        for target in old_set - new_set:
            if is_local(target):
                self._discard_incoming(target.node_id, node_id)
        for target in new_set - old_set:
            if is_local(target):
                self.incoming_refs.setdefault(target.node_id, set()).add(node_id)

        self.outgoing_refs[node_id] = new_set
        self._bump_generation(node_id)

    # -- lookups (direct dict access only, per {p042}) --------------------

    def get_generation(self, node_id: UUID) -> Optional[int]:
        """Return ``node_id``'s current generation, or ``None`` if absent."""

        entry = self.nodes_by_id.get(node_id)
        return entry.generation if entry is not None else None

    def resolve_node_id(self, node_id: UUID) -> Optional[NodeEntry]:
        """Direct O(1) re-resolution of ``node_id`` to its current entry.

        This is the slow-path lookup :class:`CachedObjectRef` calls when
        its fast path is not valid; it is never consulted on the fast
        path, which checks generation and object identity directly
        against ``nodes_by_id`` instead. Returns ``None`` when ``node_id``
        is not registered — callers that need an integrity error (such as
        :meth:`CachedObjectRef.resolve`) raise it themselves.
        """

        return self.nodes_by_id.get(node_id)

    def get_parent(self, node_id: UUID) -> Optional[UUID]:
        """Return ``node_id``'s current parent_id, or ``None`` if root/absent."""

        return self.parent_index.get(node_id)

    def get_children(self, node_id: UUID) -> FrozenSet[UUID]:
        """Return a snapshot of ``node_id``'s current child ids."""

        return frozenset(self.child_index.get(node_id, ()))

    def get_outgoing(self, node_id: UUID) -> FrozenSet[NodeAddress]:
        """Return a snapshot of ``node_id``'s current outgoing references."""

        return frozenset(self.outgoing_refs.get(node_id, ()))

    def get_incoming(self, node_id: UUID) -> FrozenSet[UUID]:
        """Return a snapshot of the node ids that reference ``node_id`` locally."""

        return frozenset(self.incoming_refs.get(node_id, ()))

    # -- internal helpers --------------------------------------------------

    def _discard_child(self, parent_id: UUID, child_id: UUID) -> None:
        siblings = self.child_index.get(parent_id)
        if siblings is None:
            return
        siblings.discard(child_id)
        if not siblings:
            del self.child_index[parent_id]

    def _discard_incoming(self, target_node_id: UUID, referencing_node_id: UUID) -> None:
        refs = self.incoming_refs.get(target_node_id)
        if refs is None:
            return
        refs.discard(referencing_node_id)
        if not refs:
            del self.incoming_refs[target_node_id]

    def _bump_generation(self, node_id: UUID) -> None:
        entry = self.nodes_by_id.get(node_id)
        if entry is not None:
            entry.generation += 1


@dataclass
class CachedObjectRef:
    """A derived, generation-scoped direct-object reference cache entry.

    Per {p080}, ``node_address`` is the canonical source of truth and
    this cache carries no independent authority; per {p084}, its fast
    path is valid only while ``cached_generation`` still matches the
    target's live generation in the index AND ``cached_object`` is
    (identity) the live record. Both conditions are checked, because
    generation alone does not prove the same object is still installed
    (an index entry could in principle be repointed without a generation
    bump, or vice versa) — either mismatch alone forces re-resolution.
    """

    node_address: NodeAddress
    cached_generation: int
    cached_object: Any

    @classmethod
    def create(cls, index: "ReferenceIndex", node_address: NodeAddress) -> "CachedObjectRef":
        """Build a freshly resolved cache entry for ``node_address``.

        Raises :class:`ReferenceIntegrityError` if ``node_address`` does
        not resolve in ``index`` right now.
        """

        ref = cls(node_address=node_address, cached_generation=-1, cached_object=None)
        ref.resolve(index)
        return ref

    def resolve(self, index: "ReferenceIndex") -> Any:
        """Return the live object ``node_address`` currently addresses.

        Fast path (no call into :meth:`ReferenceIndex.resolve_node_id`):
        valid only when ``index.nodes_by_id`` still holds an entry for
        this node_id whose generation equals ``cached_generation`` and
        whose record *is* ``cached_object``. Otherwise, re-resolves by
        UUID4 through :meth:`ReferenceIndex.resolve_node_id`, refreshes
        both ``cached_generation`` and ``cached_object`` on success, and
        raises :class:`ReferenceIntegrityError` when the target cannot be
        found. A mutation elsewhere in the index never affects this
        method's outcome for an untouched target, per {p084}.
        """

        node_id = self.node_address.node_id
        live_entry = index.nodes_by_id.get(node_id)
        if (
            live_entry is not None
            and live_entry.generation == self.cached_generation
            and live_entry.record is self.cached_object
        ):
            return self.cached_object

        resolved_entry = index.resolve_node_id(node_id)
        if resolved_entry is None:
            raise ReferenceIntegrityError(
                f"cannot resolve NodeAddress(document_id={self.node_address.document_id!r}, "
                f"node_id={node_id!r}): node_id is not present in the reference index"
            )

        self.cached_generation = resolved_entry.generation
        self.cached_object = resolved_entry.record
        return self.cached_object
