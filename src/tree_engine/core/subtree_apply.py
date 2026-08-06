"""Explicit ``apply_subtree`` return path for concept C-019 (SubtreeCopyAndApply).

Scope: the counterpart to ``subtree_copy.py``'s read-only ``copy_subtree``,
per A-002. :func:`apply_subtree` returns a (possibly edited)
:class:`~tree_engine.core.subtree_copy.CopiedDocument` back into a target
document, replacing the original subtree it was copied from, per {p076}.
Out of scope: merge semantics (only the explicit replace), and a parallel
error taxonomy -- every rejection carries a stable
:class:`~tree_engine.errors.ErrorCode`, reusing ``NODE_ID_CONFLICT`` for
every identity collision this module rejects.

Locating the replaced subtree: the copy's own ``old_uuid_to_new_uuid`` map
(populated by ``copy_subtree`` in both identity modes, per {p073}/{p074})
carries the *origin* node_id of every copied node under its *new* one, so
the target node being replaced is found by inverting that map at the copy's
root -- uniform for both ``preserve_ids`` modes, no location parameter
needed from the caller.

NODE_ID_CONFLICT, per {p076}: the shared ``validate_mutation`` preflight
({p009}/C-006) rejects an incoming node_id colliding with an existing
``nodes_by_id`` key (its stage 2). Run unmodified, that would misfire on
every ``preserve_ids=True`` replace applied back to its own true origin --
the very identity it preserves always "collides" with the node it replaces.
This module runs ``validate_mutation`` against a *view* of the target with
the origin subtree's node_ids excluded -- but only once that origin is
confirmed the *same logical* subtree the copy came from: cross-referencing
``origin_document_id`` (must equal the target's ``document_id``) and, when
{p074}'s ``origin_parent_id`` was recorded (``preserve_ids=True``), the
origin's current parent in the target. Fresh-UUID4 mode ({p073}) has no
``origin_document_id`` recorded, so identity rests on
``old_uuid_to_new_uuid`` membership alone -- safe, a fresh UUID4 essentially
never collides with an unrelated node. Any collision left unexcluded -- an
unrelated node sharing the UUID4, or any collision against a document that
never held the recorded origin -- is a genuine ``NODE_ID_CONFLICT``, raised
as :class:`NodeIDConflictError` before anything is written.

short_id handling: a node already present in the target under its own
(copy) node_id -- identity-preserved by a legitimate ``preserve_ids=True``
replace -- keeps its existing target short_id untouched, and is not part of
the remap. Every other copied node is genuinely new, so its candidate
short_id (from the copy's own independent ``ShortIdMap``) is merged into
the target's ``short_id_map`` via
:meth:`~tree_engine.core.short_id.ShortIdMap.merge_insert`: free per {p097}
it survives, conflicting it gets a fresh value. :func:`build_short_id_remap`
turns that into the returned ``old -> new`` short_id map; a candidate that
stayed free is left out of it.

Duck-typed target ``document``: mutable ``nodes_by_id``, optional
``document_id``, optional ``document_version``/``version`` (for
``expected_version``), optional ``parent_index``, optional ``root`` (a
whole-document replace, no parent), optional ``short_id_index``, optional
``short_id_map`` (a :class:`~tree_engine.core.short_id.ShortIdMap``). A node
exposes ``node_id``, settable ``short_id``, settable ``children``, and
optionally settable ``parent_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.short_id import ShortIdMap
from tree_engine.core.subtree_copy import CopiedDocument
from tree_engine.core.validation import ValidationError, validate_mutation
from tree_engine.errors import ErrorCode

__all__ = [
    "SubtreeApplyError",
    "NodeIDConflictError",
    "ApplySubtreeResult",
    "build_short_id_remap",
    "apply_subtree",
]


class SubtreeApplyError(Exception):
    """Raised when ``apply_subtree`` cannot be performed as requested.

    Carries the originating :class:`~tree_engine.errors.ErrorCode` as
    ``self.code`` (convention shared with ``subtree_copy.py``'s
    ``SubtreeCopyError``). Raising it guarantees the target document was
    not touched.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code


class NodeIDConflictError(SubtreeApplyError):
    """A node_id from the incoming copy collides with the target and is not
    the same logical node the copy was taken from ({p076}). Always carries
    ``ErrorCode.NODE_ID_CONFLICT`` as ``self.code``. ``self.errors`` holds
    the underlying ``ValidationError`` entries from the shared preflight."""

    def __init__(self, errors: Sequence[ValidationError]) -> None:
        self.errors: List[ValidationError] = list(errors)
        detail = "; ".join(e.message for e in self.errors) or "node_id conflict"
        super().__init__(ErrorCode.NODE_ID_CONFLICT, detail)


@dataclass(frozen=True)
class ApplySubtreeResult:
    """Outcome of ``apply_subtree``: ``node_id`` is the copy's root, now
    live in the target. ``short_id_remap`` maps every reassigned ``old ->
    new`` short_id ({p076}); a short_id that stayed free, or an
    identity-preserved node, is not an entry. ``removed``/``inserted`` are
    the touched :class:`~tree_engine.core.identity.NodeAddress` values."""

    node_id: UUID
    short_id_remap: Mapping[Any, Any]
    removed: NodeAddress
    inserted: NodeAddress


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _get_children(node: Any) -> Tuple[Any, ...]:
    return tuple(getattr(node, "children", None) or ())


def _walk(node: Any):
    yield node
    for child in _get_children(node):
        yield from _walk(child)


def _check_version(document: Any, expected_version: Optional[Any]) -> None:
    if expected_version is None:
        return
    _absent = object()
    current = getattr(document, "document_version", _absent)
    current = getattr(document, "version", None) if current is _absent else current
    if current != expected_version:
        raise SubtreeApplyError(
            ErrorCode.DOCUMENT_VERSION_CONFLICT,
            f"expected_version {expected_version!r} does not match target "
            f"document_version {current!r}",
        )


def _origin_root_id(copy: CopiedDocument) -> UUID:
    root_id = getattr(copy.root, "node_id")
    for old_id, new_id in copy.old_uuid_to_new_uuid.items():
        if new_id == root_id:
            return old_id
    raise SubtreeApplyError(
        ErrorCode.NODE_NOT_FOUND,
        "copy.root.node_id is not recorded in old_uuid_to_new_uuid; cannot "
        "establish which target node this copy replaces",
    )


def _resolved_parent_id(document: Any, node_id: UUID, node: Any) -> Optional[UUID]:
    parent_index = getattr(document, "parent_index", None)
    if isinstance(parent_index, dict):
        return parent_index.get(node_id)
    return getattr(node, "parent_id", None)


def _legitimate_old_ids(
    document: Any,
    copy: CopiedDocument,
    target_parent_id: Optional[UUID],
) -> FrozenSet[UUID]:
    """Origin subtree node_ids {p076} treats as the *same logical* node in
    the target's ``nodes_by_id``, not a conflict (module docstring has the
    cross-reference rules)."""

    if copy.origin_document_id is not None:
        if copy.origin_document_id != getattr(document, "document_id", None):
            return frozenset()
        if copy.origin_parent_id is not None and target_parent_id != copy.origin_parent_id:
            return frozenset()
    return frozenset(copy.old_uuid_to_new_uuid.keys())


class _FilteredView:
    """Minimal read-only ``validate_mutation`` target: real ``nodes_by_id``
    minus the confirmed-legitimate origin subtree's node_ids, so stage 2
    does not misfire on the identity {p076} means to preserve."""

    __slots__ = ("nodes_by_id", "document_id")

    def __init__(self, nodes_by_id: Dict[UUID, Any], document_id: Optional[UUID]) -> None:
        self.nodes_by_id = nodes_by_id
        self.document_id = document_id


def _children_list(node: Any) -> List[Any]:
    return list(getattr(node, "children", None) or ())


def _set_children(node: Any, children: Sequence[Any]) -> None:
    if isinstance(getattr(node, "children", None), tuple):
        node.children = tuple(children)
    else:
        node.children = list(children)


def _partition_fragment(
    copy_root: Any, nodes_by_id: Mapping[UUID, Any]
) -> Tuple[List[Any], List[Any]]:
    """Split the copy's fragment into ``kept`` (node_id already live in the
    target -- identity-preserved) and ``new``, against the target's
    *unmodified* ``nodes_by_id``."""

    kept: List[Any] = []
    new: List[Any] = []
    for node in _walk(copy_root):
        (kept if node.node_id in nodes_by_id else new).append(node)
    return kept, new


def build_short_id_remap(
    candidates: Mapping[UUID, Any], assigned: Mapping[UUID, Any]
) -> Dict[Any, Any]:
    """Build the ``old -> new`` short_id remap ({p076}) from each *new*
    node's candidate (its value in the copy's own ``ShortIdMap``) and the
    final value ``merge_insert``/``allocate`` assigned in the target. A
    candidate that stayed free is left out, per {p097}."""

    remap: Dict[Any, Any] = {}
    for node_id, candidate in candidates.items():
        final = assigned.get(node_id)
        if candidate is not None and final is not None and final != candidate:
            remap[candidate] = final
    return remap


def _apply_short_ids(
    document: Any, kept: Sequence[Any], new: Sequence[Any], nodes_by_id: Mapping[UUID, Any]
) -> Dict[Any, Any]:
    """Assign every copied node its final target short_id in place and
    return the remap. ``kept`` nodes reuse the target's existing short_id;
    ``new`` nodes go through the target's ``short_id_map``."""

    for node in kept:
        node.short_id = getattr(nodes_by_id[node.node_id], "short_id", None)
    short_id_map: Optional[ShortIdMap] = getattr(document, "short_id_map", None)
    if short_id_map is None or not new:
        return {}
    candidates = {node.node_id: node.short_id for node in new}
    with_value = {nid: sid for nid, sid in candidates.items() if sid is not None}
    without_value = [nid for nid, sid in candidates.items() if sid is None]
    assigned: Dict[UUID, int] = dict(short_id_map.merge_insert(with_value)) if with_value else {}
    for node_id in without_value:
        assigned[node_id] = short_id_map.allocate(node_id)
    by_id = {node.node_id: node for node in new}
    for node_id, final_short_id in assigned.items():
        by_id[node_id].short_id = final_short_id
    return build_short_id_remap(candidates, assigned)


def _splice(document: Any, parent_node: Optional[Any], target_root: Any, new_root: Any) -> None:
    nodes_by_id = document.nodes_by_id
    short_index = getattr(document, "short_id_index", None)
    for old_node in _walk(target_root):
        nodes_by_id.pop(getattr(old_node, "node_id", None), None)
        if isinstance(short_index, dict):
            short_index.pop(getattr(old_node, "short_id", None), None)
    if parent_node is not None:
        siblings = _children_list(parent_node)
        index = next(
            (i for i, c in enumerate(siblings) if getattr(c, "node_id", None) == target_root.node_id),
            None,
        )
        if index is None:
            raise SubtreeApplyError(
                ErrorCode.NODE_NOT_FOUND, "target root is not among its parent's children"
            )
        siblings[index] = new_root
        _set_children(parent_node, siblings)
        if hasattr(new_root, "parent_id"):
            new_root.parent_id = getattr(parent_node, "node_id", None)
    elif hasattr(document, "root"):
        document.root = new_root
    for new_node in _walk(new_root):
        node_id = getattr(new_node, "node_id", None)
        if node_id is not None:
            nodes_by_id[node_id] = new_node
        if isinstance(short_index, dict):
            sid = getattr(new_node, "short_id", None)
            if sid is not None:
                short_index[sid] = node_id


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def apply_subtree(
    document: Any,
    copy: CopiedDocument,
    *,
    expected_version: Optional[Any] = None,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
) -> ApplySubtreeResult:
    """Return ``copy`` into ``document``, replacing the original subtree it
    was copied from, per {p076}. ``expected_version`` is checked first
    (:class:`SubtreeApplyError`, ``DOCUMENT_VERSION_CONFLICT`` on
    mismatch). The origin node is located via ``copy.old_uuid_to_new_uuid``
    (uniform for both ``preserve_ids`` modes); its absence raises
    ``NODE_NOT_FOUND``. The shared {p009}/C-006 ``validate_mutation``
    preflight runs before any write; a ``NODE_ID_CONFLICT`` not recognized
    as the same logical node raises :class:`NodeIDConflictError`, any other
    failure raises :class:`SubtreeApplyError` -- the target is left
    untouched either way. On success the fragment is spliced in, short_ids
    are merged per {p097}, and the ``old -> new`` short_id remap is
    returned."""

    _check_version(document, expected_version)
    nodes_by_id = getattr(document, "nodes_by_id", None)
    if nodes_by_id is None:
        raise SubtreeApplyError(
            ErrorCode.NODE_NOT_FOUND, "target document exposes no 'nodes_by_id' map"
        )

    origin_root_id = _origin_root_id(copy)
    target_root = nodes_by_id.get(origin_root_id)
    if target_root is None:
        raise SubtreeApplyError(
            ErrorCode.NODE_NOT_FOUND,
            f"original subtree root not found in target document: {origin_root_id!r}",
        )

    target_parent_id = _resolved_parent_id(document, origin_root_id, target_root)
    parent_node = nodes_by_id.get(target_parent_id) if target_parent_id is not None else None

    legitimate = _legitimate_old_ids(document, copy, target_parent_id)
    filtered_nodes_by_id = {nid: n for nid, n in nodes_by_id.items() if nid not in legitimate}
    view = _FilteredView(filtered_nodes_by_id, getattr(document, "document_id", None))

    position: Optional[str] = None
    index: Optional[int] = None
    if parent_node is not None:
        siblings = _children_list(parent_node)
        found = next(
            (i for i, c in enumerate(siblings) if getattr(c, "node_id", None) == origin_root_id),
            None,
        )
        if found is not None:
            position, index = "child_index", found

    result = validate_mutation(
        view,
        copy.root,
        parent=parent_node,
        position=position,
        index=index,
        is_type_compatible=is_type_compatible,
        references=references,
        loaded_documents=loaded_documents,
    )
    if not result.success:
        conflicts = [e for e in result.errors if e.code == ErrorCode.NODE_ID_CONFLICT]
        if conflicts:
            raise NodeIDConflictError(conflicts)
        first = result.errors[0]
        raise SubtreeApplyError(first.code, first.message)

    kept, new = _partition_fragment(copy.root, nodes_by_id)
    remap = _apply_short_ids(document, kept, new, nodes_by_id)

    removed_address = NodeAddress(
        document_id=getattr(document, "document_id", None), node_id=origin_root_id
    )
    _splice(document, parent_node, target_root, copy.root)
    inserted_address = NodeAddress(
        document_id=getattr(document, "document_id", None), node_id=getattr(copy.root, "node_id")
    )

    return ApplySubtreeResult(
        node_id=getattr(copy.root, "node_id"),
        short_id_remap=remap,
        removed=removed_address,
        inserted=inserted_address,
    )
