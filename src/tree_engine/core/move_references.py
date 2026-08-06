"""Cross-document move reference reconciliation (concept C-020, {p039}/{p080}/{p081}).

Scope, narrowed exactly to what this atomic step owns: given the subtree(s)
already structurally relocated by the sibling ``move.py`` orchestrator, this
module computes -- and, once computed, mechanically applies -- the reference
rewrites a cross-document move requires:

* every reference between two moved nodes ("subtree-internal") is rewritten
  to carry the target document's ``document_id`` explicitly;
* every outgoing reference from a moved node to a node left behind in the
  source document is rewritten to an explicit external ``NodeAddress``
  naming the source document;
* every incoming reference that names a moved node -- found on a node still
  resident in the source document, or on a node in any other *loaded*
  document -- is rewritten to an explicit external ``NodeAddress`` naming
  the target document.

This satisfies {p080}/{p081} in the context of the move defined by {p039}.
``NodeAddress`` (imported unchanged from ``core.identity``) stays the sole
canonical representation; this module never introduces a second one and
never touches any object-reference cache -- there is none here to touch,
since ``core.nodes.Node.references`` already stores canonical ``NodeAddress``
values directly, per {p080}.

This file computes a :class:`ReferenceDelta` and applies it -- nothing else.
It never decides transaction boundaries, never acquires a lock, and never
commits or rolls back a transaction: the sibling ``move.py`` orchestrator
calls ``reconcile_references(...)`` once, inside its own rollback scope,
immediately after the structural relocation, and then calls the returned
delta's ``.apply(source_document, target_document, loaded_documents)``,
still inside that same scope. Likewise, refreshing either document's index
maps (``nodes_by_id``, ``short_id``, ``parent``/``child``, the
incoming/outgoing reference indices such as ``core.reference_cache
.ReferenceIndex``) is *not* done by this file -- per this step's own
contract, that synchronous refresh happens elsewhere, as part of the same
application ``move.py`` performs, not here directly.

Duck-typed contracts reused unchanged from the already-merged sibling
modules (never redefined here):

* ``NodeAddress(document_id, node_id)`` -- ``core.identity``. ``document_id
  is None`` is the implicit-current-document (local) form; an explicit
  value names a document unambiguously, per {p080}.
* ``is_local(address)`` -- ``core.references``, the exact local/external
  classification helper this module reuses instead of re-implementing the
  ``document_id is None`` check inline.
* ``document`` -- duck-typed exactly as ``move.py``'s own contract:
  ``document.nodes_by_id`` (node_id -> node) and an optional
  ``document.document_id``.
* ``node`` -- duck-typed with an optional ``node_id``, an optional
  ``children`` sequence (for subtree traversal), and an optional
  ``references`` sequence of ``NodeAddress`` values -- mirroring the
  reserved extension-point attribute on ``core.nodes.Node`` -- that this
  module reads and, in ``ReferenceDelta.apply``, rewrites in place via
  ``setattr``, exactly the convention ``move.py`` itself already uses for
  ``parent`` and ``children``.

``short_id_remap`` is accepted only because ``move.py`` always supplies it
as part of its fixed call shape; references are addressed by ``node_id``,
never by ``short_id``, so this module never reads it.

An intra-document move (``source_document`` and ``target_document`` sharing
the same ``document_id``, including both being ``None``) has nothing to
reconcile -- no document boundary is actually crossed -- so
:func:`reconcile_references` returns an empty, no-op delta for it rather
than rewriting addresses that were already correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tree_engine.core.identity import NodeAddress
from tree_engine.core.references import is_local

__all__ = ["ReferenceChange", "ReferenceDelta", "reconcile_references"]


@dataclass(frozen=True)
class ReferenceChange:
    """One node's outgoing ``references`` tuple, before and after rewrite."""

    node: Any
    old_references: Tuple[Any, ...]
    new_references: Tuple[Any, ...]


@dataclass(frozen=True)
class ReferenceDelta:
    """The complete, immutable plan produced by :func:`reconcile_references`.

    ``changes`` is fully computed before this object is constructed, so
    there is no lazy or partial state to observe between construction and
    :meth:`apply` -- either every planned rewrite is here already, or (for
    a node untouched by the move) it is simply absent from ``changes``.
    Applying is a purely mechanical replay of that already-decided plan:
    for each recorded :class:`ReferenceChange`, ``change.node.references``
    is set to ``change.new_references``. Nothing else is touched -- no
    lock, no transaction, no index map, no document attribute other than
    the node's own ``references``.
    """

    changes: Tuple[ReferenceChange, ...] = ()

    def apply(
        self,
        source_document: Any = None,
        target_document: Any = None,
        loaded_documents: Optional[Dict[Any, Any]] = None,
    ) -> "ReferenceDelta":
        """Write every planned rewrite back onto its owning node.

        Accepts the same three arguments ``move.py`` passes positionally
        (``source_document``, ``target_document``, ``loaded_documents``)
        purely to satisfy the injected ``.apply(...)`` contract it already
        calls; none of them is otherwise required here, since every node
        this delta touches is already reachable directly through
        ``self.changes``.
        """

        for change in self.changes:
            setattr(change.node, "references", change.new_references)
        return self


def _document_id(document: Any) -> Any:
    return getattr(document, "document_id", None)


def _fragment_nodes(root: Any) -> List[Any]:
    """Every node in ``root``'s subtree, ``root`` included (order-agnostic).

    Mirrors ``move.py``'s own ``_fragment_nodes`` helper in shape (this
    file never imports it, per the sibling-duplication precedent already
    established between ``operations.py`` and ``updates.py``)."""

    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        stack = list(getattr(node, "children", None) or ()) + stack
    return ordered


def _collect_moved(moved_roots: Sequence[Any]) -> Tuple[List[Any], set]:
    """Flatten every moved root's subtree into a node list and an id set."""

    nodes: List[Any] = []
    ids: set = set()
    for root in moved_roots:
        for node in _fragment_nodes(root):
            nodes.append(node)
            node_id = getattr(node, "node_id", None)
            if node_id is not None:
                ids.add(node_id)
    return nodes, ids


def _references_of(node: Any) -> Tuple[Any, ...]:
    return tuple(getattr(node, "references", None) or ())


def _address_parts(address: Any) -> Tuple[Any, Any]:
    """Duck-typed ``(node_id, document_id)`` read off ``address``.

    Mirrors ``validate_mutation``'s own ``getattr(reference, "node_id",
    reference)`` convention: a bare id is accepted as-is, alongside a full
    ``NodeAddress``-shaped value."""

    node_id = getattr(address, "node_id", address)
    document_id = getattr(address, "document_id", None)
    return node_id, document_id


def _rewrite_outgoing(
    moved_nodes: Sequence[Any],
    moved_ids: set,
    src_id: Any,
    tgt_id: Any,
) -> List[ReferenceChange]:
    """Rewrite each moved node's own outgoing references -- {p039}'s first
    two clauses: a subtree-internal reference adopts the target
    document_id; a reference to a node left behind in the source document
    becomes external and explicitly names the source document. A
    reference that, even before the move, already named some third
    document is left exactly as it was -- this move never touches it."""

    changes: List[ReferenceChange] = []
    for node in moved_nodes:
        old_refs = _references_of(node)
        if not old_refs:
            continue
        new_refs: List[Any] = []
        changed = False
        for address in old_refs:
            node_id, document_id = _address_parts(address)
            effective_doc = src_id if is_local(address) else document_id
            if effective_doc == src_id and node_id in moved_ids:
                new_address: Any = NodeAddress(node_id=node_id, document_id=tgt_id)
                changed = True
            elif effective_doc == src_id and node_id not in moved_ids:
                new_address = NodeAddress(node_id=node_id, document_id=src_id)
                changed = True
            else:
                new_address = address
            new_refs.append(new_address)
        if changed:
            changes.append(
                ReferenceChange(node=node, old_references=old_refs, new_references=tuple(new_refs))
            )
    return changes


def _rewrite_incoming(
    scanned_docs: Dict[Any, Any],
    moved_object_ids: set,
    moved_ids: set,
    src_id: Any,
    tgt_id: Any,
) -> List[ReferenceChange]:
    """Rewrite every reference, in every *loaded* document, that names a
    moved node -- {p039}'s third clause, generalized from "the source
    document's remaining nodes" to any loaded document, since a third
    document can hold an external reference into the source document just
    as validly as the source document's own remaining nodes can. A
    document the caller never loaded is, correctly, never visited here:
    nothing in it is touched, since this module has no way to reach it."""

    changes: List[ReferenceChange] = []
    for doc_id, document in scanned_docs.items():
        nodes_by_id = getattr(document, "nodes_by_id", None) or {}
        for node in nodes_by_id.values():
            if id(node) in moved_object_ids:
                continue  # the moved side is already handled by _rewrite_outgoing
            old_refs = _references_of(node)
            if not old_refs:
                continue
            new_refs: List[Any] = []
            changed = False
            for address in old_refs:
                node_id, document_id = _address_parts(address)
                effective_doc = doc_id if is_local(address) else document_id
                if effective_doc == src_id and node_id in moved_ids:
                    new_refs.append(NodeAddress(node_id=node_id, document_id=tgt_id))
                    changed = True
                else:
                    new_refs.append(address)
            if changed:
                changes.append(
                    ReferenceChange(node=node, old_references=old_refs, new_references=tuple(new_refs))
                )
    return changes


def reconcile_references(
    *,
    source_document: Any,
    target_document: Any,
    moved_roots: Sequence[Any],
    short_id_remap: Sequence[Any] = (),
    loaded_documents: Optional[Dict[Any, Any]] = None,
) -> ReferenceDelta:
    """Compute the reference-conversion plan for one cross-document move.

    Called once by ``move.py``, after the structural relocation but before
    either document is considered final, with ``moved_roots`` already
    attached under ``target_document`` (so ``target_document.nodes_by_id``
    already contains them and ``source_document.nodes_by_id`` no longer
    does). Returns a fully-computed, immutable :class:`ReferenceDelta`;
    nothing is mutated by this function itself -- only :meth:`ReferenceDelta
    .apply` writes anything.

    Three conversions are computed, per {p039}/{p080}/{p081}:

    1. A reference between two moved nodes stays addressable, now inside
       the target document: its ``NodeAddress`` is rewritten with an
       explicit ``document_id`` equal to ``target_document``'s.
    2. An outgoing reference from a moved node to a node left behind in
       ``source_document`` becomes external: its ``NodeAddress`` is
       rewritten with an explicit ``document_id`` equal to
       ``source_document``'s.
    3. An incoming reference that names a moved node, found on any node
       still resident in ``source_document`` or in any document supplied
       through ``loaded_documents``, is rewritten with an explicit
       ``document_id`` equal to ``target_document``'s. A document not
       present in ``loaded_documents`` is never inspected, so a reference
       living there is left exactly as it was.

    A reference that, before this move, already named some other document
    entirely (neither ``source_document`` nor ``target_document``) is left
    untouched in every case above -- this move never rewrites a reference
    it did not make stale.

    ``short_id_remap`` is accepted only to match the fixed call shape
    ``move.py`` always uses; references are addressed by ``node_id``, so
    it is never read here.
    """

    src_id = _document_id(source_document)
    tgt_id = _document_id(target_document)

    if src_id == tgt_id:
        # No document boundary is actually crossed (including the
        # both-None implicit-document case): nothing needs reconciling.
        return ReferenceDelta(changes=())

    moved_nodes, moved_ids = _collect_moved(moved_roots)
    moved_object_ids = {id(n) for n in moved_nodes}

    scanned_docs: Dict[Any, Any] = {}
    if src_id is not None:
        scanned_docs[src_id] = source_document
    if tgt_id is not None:
        scanned_docs.setdefault(tgt_id, target_document)
    for doc_id, document in (loaded_documents or {}).items():
        scanned_docs.setdefault(doc_id, document)

    outgoing = _rewrite_outgoing(moved_nodes, moved_ids, src_id, tgt_id)
    incoming = _rewrite_incoming(scanned_docs, moved_object_ids, moved_ids, src_id, tgt_id)

    return ReferenceDelta(changes=tuple(outgoing) + tuple(incoming))
