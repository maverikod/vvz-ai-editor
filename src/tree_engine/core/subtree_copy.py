"""Read-only independent subtree copying for concept C-019 (SubtreeCopyAndApply).

Scope (concept C-019, narrowed to the copy half only, per A-001): one
read-only entry point, :func:`copy_subtree`, plus its result type
:class:`CopiedDocument`. Never mutates the source document, its nodes, or
its index maps. The explicit ``replace_subtree``/``apply_subtree`` return
path ({p076}) is a sibling artifact's job -- out of scope here.

Per {p072}-{p074}, two identity modes:

* ``preserve_ids=False`` (default): every copied node gets a fresh UUID4
  node_id; ``CopiedDocument.old_uuid_to_new_uuid`` records the resulting
  old->new map for the whole copied subtree.
* ``preserve_ids=True``: every copied node keeps its original UUID4 under a
  brand-new ``document_id``. ``old_uuid_to_new_uuid`` is still populated, as
  the identity map (``old == new``); ``origin_document_id``/
  ``origin_parent_id`` record where the copy came from, per {p074}.

In both modes, per {p073}/{p074}: references whose source and target both
lie inside the copied subtree become new intra-document references of the
copy (implicit-local form, ``document_id=None``); references that leave the
subtree are preserved unchanged as explicit external ``NodeAddress`` values
naming the *source* document and the *original* target node_id. References
incoming from outside the subtree are never copied -- traversal never
visits any node outside the chosen subtree ({p077}, bounded cost).

Per {p075}, the returned :class:`CopiedDocument` is fully independent of the
source: its own ``document_id``, its own fresh :class:`ShortIdMap`, its own
``nodes_by_id`` of freshly built node objects (immutable dataclass nodes
rebuilt bottom-up via ``dataclasses.replace``; any other duck-typed mutable
node is shallow-copied via ``copy.copy`` then has its identity-bearing
attributes overwritten). Mutating either side afterwards updates only that
side's own state. ``document_version`` on the copy always starts at ``1``:
{p075} requires an independent version counter, not inheritance of the
source's current value.

Duck-typed contracts, matching the convention already established by
``identity.py``, ``validation.py`` and ``operations.py`` -- no concrete
``Document``/``Node`` type is imported or required:

* ``document``: ``nodes_by_id`` (``node_id -> node``, read-only, consulted
  only to look up the requested subtree root), optionally ``root`` (used
  when ``node_id`` is ``None``, i.e. "copy the whole tree"), optionally
  ``document_id``, optionally ``document_version``/``version`` for the
  ``expected_version`` check, and optionally ``parent_index`` (a
  ``node_id -> parent_id`` mapping, consulted only for ``origin_parent_id``
  under ``preserve_ids=True``).
* a node: ``node_id`` (required), an ordered ``children`` sequence
  (optional, absent/``None`` means a leaf), and optionally ``short_id``,
  ``references`` (an iterable of :class:`~tree_engine.core.identity.NodeAddress`),
  and ``parent_id``. A node built through ``nodes.py``'s immutable
  ``Node``/``make_node`` is rebuilt via ``dataclasses.replace``, including
  ``fields`` (any value that *is* one of ``node.children``, by object
  identity, tracks that child's copy, so ``fields``/``children`` never
  drift apart); a fields-embedded ``Node`` not also reachable through
  ``children`` is not deep-copied, matching ``nodes.py``'s own "not
  required to be kept in lockstep" note.

Non-goals: no ``replace_subtree``/``apply_subtree``, no shared insertion
validation, no ``NODE_ID_CONFLICT`` detection on return -- a sibling step.
"""

from __future__ import annotations

import copy as _copy
import dataclasses
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
from uuid import UUID

from tree_engine.core.identity import NodeAddress, generate_node_id
from tree_engine.core.references import is_local
from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode

__all__ = ["SubtreeCopyError", "CopiedDocument", "copy_subtree"]


class SubtreeCopyError(Exception):
    """Raised when ``copy_subtree`` cannot be performed as requested.

    Carries the originating :class:`~tree_engine.errors.ErrorCode` as
    ``self.code`` (convention shared with ``nodes.py``'s
    ``NodeSchemaError``): an ``expected_version`` mismatch
    (``DOCUMENT_VERSION_CONFLICT``) or an unresolvable ``node_id``/missing
    document root (``NODE_NOT_FOUND``). Raising it guarantees the source
    document was not touched.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code


@dataclass
class CopiedDocument:
    """The independent tree copy returned by :func:`copy_subtree` ({p072}).

    ``root`` is the copied subtree's root, always with ``parent_id`` (when
    the node type carries one) set to ``None``. ``nodes_by_id`` and
    ``short_id_map`` are freshly built, touching nothing of the source's own
    maps. ``old_uuid_to_new_uuid`` maps every copied node's original
    node_id to its node_id here (identity mapping under
    ``preserve_ids=True``). ``origin_document_id``/``origin_parent_id`` are
    populated only under ``preserve_ids=True`` ({p074}), else ``None``.
    """

    document_id: UUID
    document_version: int
    root: Any
    nodes_by_id: Dict[UUID, Any]
    short_id_map: ShortIdMap
    old_uuid_to_new_uuid: Dict[UUID, UUID]
    origin_document_id: Optional[UUID] = None
    origin_parent_id: Optional[UUID] = None


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
        raise SubtreeCopyError(
            ErrorCode.DOCUMENT_VERSION_CONFLICT,
            f"expected_version {expected_version!r} does not match source "
            f"document_version {current!r}",
        )


def _find_root(document: Any, node_id: Optional[UUID]) -> Any:
    if node_id is None:
        root = getattr(document, "root", None)
        if root is None:
            raise SubtreeCopyError(
                ErrorCode.NODE_NOT_FOUND,
                "document exposes no 'root' node and no node_id was given",
            )
        return root
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    node = nodes_by_id.get(node_id)
    if node is None:
        raise SubtreeCopyError(
            ErrorCode.NODE_NOT_FOUND,
            f"node_id not found in source document: {node_id!r}",
        )
    return node


def _collect_ids(
    node: Any,
    preserve_ids: bool,
    id_map: Dict[UUID, UUID],
    old_id_set: Set[UUID],
    ordered_new_ids: List[UUID],
) -> None:
    """Pre-order, subtree-only walk ({p077}): assigns each node's new
    node_id (fresh UUID4, or same UUID4 under ``preserve_ids``) without
    building any node object yet."""

    old_id = node.node_id
    old_id_set.add(old_id)
    new_id = old_id if preserve_ids else generate_node_id()
    id_map[old_id] = new_id
    ordered_new_ids.append(new_id)
    for child in _get_children(node):
        _collect_ids(child, preserve_ids, id_map, old_id_set, ordered_new_ids)


def _rewrite_references(
    node: Any,
    old_id_set: Set[UUID],
    id_map: Dict[UUID, UUID],
    source_document_id: Optional[UUID],
) -> Tuple[NodeAddress, ...]:
    """Rewrite outgoing references per {p073}/{p074}: internal (target
    inside the subtree) -> new implicit-local reference of the copy;
    external (target outside) -> preserved, unchanged, as an explicit
    ``NodeAddress`` of the source document."""

    raw_refs = getattr(node, "references", None) or ()
    new_refs = []
    for ref in raw_refs:
        target_id = ref.node_id
        if target_id in old_id_set:
            new_refs.append(NodeAddress(document_id=None, node_id=id_map[target_id]))
        else:
            doc_id = source_document_id if is_local(ref) else ref.document_id
            new_refs.append(NodeAddress(document_id=doc_id, node_id=target_id))
    return tuple(new_refs)


def _rewrite_fields(
    fields: Any, original_children: Tuple[Any, ...], new_children: List[Any]
) -> Any:
    """Sync a dataclass node's ``fields`` with its rebuilt ``children``: a
    field value that *is* one of ``original_children`` (by identity) is
    replaced by that child's already-built copy; anything else is left
    untouched (``nodes.py``'s "not required to be kept in lockstep")."""

    if not isinstance(fields, Mapping):
        return fields
    child_copy_of = {id(oc): nc for oc, nc in zip(original_children, new_children)}

    def _map_value(value: Any) -> Any:
        if isinstance(value, tuple):
            return tuple(child_copy_of.get(id(v), v) for v in value)
        return child_copy_of.get(id(value), value)

    return MappingProxyType({key: _map_value(value) for key, value in fields.items()})


def _clone_leaf(
    node: Any,
    *,
    new_node_id: UUID,
    new_short_id: Any,
    new_children: List[Any],
    new_references: Tuple[NodeAddress, ...],
    new_parent_id: Optional[UUID],
) -> Any:
    """Build one copied node, independent of ``node``: an immutable
    dataclass node (e.g. ``nodes.py``'s ``Node``) is rebuilt via
    ``dataclasses.replace``; any other duck-typed node is shallow-copied via
    ``copy.copy`` then has every identity-bearing attribute overwritten."""

    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        changes: Dict[str, Any] = {}
        if hasattr(node, "node_id"):
            changes["node_id"] = new_node_id
        if hasattr(node, "short_id"):
            changes["short_id"] = new_short_id
        if hasattr(node, "children"):
            original = getattr(node, "children")
            changes["children"] = (
                tuple(new_children) if isinstance(original, tuple) else list(new_children)
            )
        if hasattr(node, "references"):
            changes["references"] = new_references
        if hasattr(node, "fields"):
            changes["fields"] = _rewrite_fields(node.fields, _get_children(node), new_children)
        if hasattr(node, "parent_id"):
            changes["parent_id"] = new_parent_id
        return dataclasses.replace(node, **changes)

    cloned = _copy.copy(node)
    if hasattr(cloned, "node_id"):
        cloned.node_id = new_node_id
    if hasattr(cloned, "short_id"):
        cloned.short_id = new_short_id
    if hasattr(cloned, "children"):
        original = getattr(node, "children")
        cloned.children = (
            type(original)(new_children) if isinstance(original, (tuple, list)) else list(new_children)
        )
    if hasattr(cloned, "references"):
        original_refs = getattr(node, "references", None)
        cloned.references = (
            tuple(new_references) if not isinstance(original_refs, list) else list(new_references)
        )
    if hasattr(cloned, "parent_id"):
        cloned.parent_id = new_parent_id
    return cloned


def _build_copy(
    node: Any,
    *,
    is_root: bool,
    old_id_set: Set[UUID],
    id_map: Dict[UUID, UUID],
    short_ids: Dict[UUID, Any],
    source_document_id: Optional[UUID],
) -> Any:
    """Bottom-up rebuild ({p077}, subtree-only): children first (an
    immutable node is built from already-existing children), then this
    node is cloned with its new identity, ``children``, ``references``,
    and a ``parent_id`` remapped through ``id_map`` (a no-op under
    ``preserve_ids=True``, where ``id_map`` is the identity map)."""

    new_children = [
        _build_copy(
            child,
            is_root=False,
            old_id_set=old_id_set,
            id_map=id_map,
            short_ids=short_ids,
            source_document_id=source_document_id,
        )
        for child in _get_children(node)
    ]
    new_node_id = id_map[node.node_id]
    new_short_id = short_ids[new_node_id]
    new_references = _rewrite_references(node, old_id_set, id_map, source_document_id)
    old_parent_id = getattr(node, "parent_id", None)
    new_parent_id = None if is_root else id_map.get(old_parent_id, old_parent_id)
    return _clone_leaf(
        node,
        new_node_id=new_node_id,
        new_short_id=new_short_id,
        new_children=new_children,
        new_references=new_references,
        new_parent_id=new_parent_id,
    )


def _find_origin_parent_id(document: Any, node_id: Optional[UUID], root: Any) -> Optional[UUID]:
    if node_id is None:
        return None
    parent_index = getattr(document, "parent_index", None)
    return parent_index.get(node_id) if isinstance(parent_index, dict) else getattr(root, "parent_id", None)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def copy_subtree(
    document: Any,
    node_id: Optional[UUID] = None,
    expected_version: Optional[Any] = None,
    preserve_ids: bool = False,
) -> CopiedDocument:
    """Return an independent copy of ``document``'s subtree rooted at
    ``node_id`` (whole document when ``None``), per {p072}. Read-only: the
    source document, its nodes, and its index maps are never mutated.

    ``expected_version`` -- checked first -- must equal
    ``document.document_version``/``version`` when given, or
    :class:`SubtreeCopyError` (``DOCUMENT_VERSION_CONFLICT``) is raised. An
    unresolvable ``node_id`` (or missing ``document.root`` when ``node_id``
    is ``None``) raises :class:`SubtreeCopyError` (``NODE_NOT_FOUND``).

    ``preserve_ids`` selects the identity mode: ``False`` (default) mints a
    fresh UUID4 per copied node ({p073}); ``True`` keeps every UUID4
    unchanged under the copy's new ``document_id``, recording
    ``origin_document_id``/``origin_parent_id`` ({p074}). Either way the
    copy gets its own fresh :class:`~tree_engine.core.short_id.ShortIdMap`,
    ``nodes_by_id``, and ``document_version`` starting at ``1``; references
    are rewritten/preserved as documented at module level. Traversal and
    copying touch only the chosen subtree's nodes ({p077}).
    """

    _check_version(document, expected_version)
    root = _find_root(document, node_id)
    source_document_id = getattr(document, "document_id", None)

    id_map: Dict[UUID, UUID] = {}
    old_id_set: Set[UUID] = set()
    ordered_new_ids: List[UUID] = []
    _collect_ids(root, preserve_ids, id_map, old_id_set, ordered_new_ids)

    short_id_map = ShortIdMap()
    short_ids = short_id_map.assign_bulk(ordered_new_ids)

    new_root = _build_copy(
        root,
        is_root=True,
        old_id_set=old_id_set,
        id_map=id_map,
        short_ids=short_ids,
        source_document_id=source_document_id,
    )

    nodes_by_id = {n.node_id: n for n in _walk(new_root)}

    origin_document_id: Optional[UUID] = None
    origin_parent_id: Optional[UUID] = None
    if preserve_ids:
        origin_document_id = source_document_id
        origin_parent_id = _find_origin_parent_id(document, node_id, root)

    return CopiedDocument(
        document_id=generate_node_id(),
        document_version=1,
        root=new_root,
        nodes_by_id=nodes_by_id,
        short_id_map=short_id_map,
        old_uuid_to_new_uuid=id_map,
        origin_document_id=origin_document_id,
        origin_parent_id=origin_parent_id,
    )
