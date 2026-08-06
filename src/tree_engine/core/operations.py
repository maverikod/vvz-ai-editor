"""Atomic core node operations: insert, delete, replace_range (concept C-006).

Runs on top of the shared preflight validator in the sibling
``validation.py`` ({p009}): every operation that introduces new content
calls :func:`~tree_engine.core.validation.validate_mutation` first and only
touches the tree and its index maps -- ``document.nodes_by_id`` and, when
present, a ``document.short_id_index`` map of ``short_id -> node_id`` --
after validation succeeds, raising :class:`MutationError` on any failure
before writing anything, so no partial mutation is ever observable.

Duck-typed contract (mirrors ``validation.py``; no concrete tree/document
type is imported): ``document.nodes_by_id`` is a mutable ``node_id ->
node`` map; ``document.short_id_index`` is an optional mutable ``short_id
-> node_id`` map; ``document.document_id`` is read only to build a
:class:`~tree_engine.core.identity.NodeAddress`. A node exposes
``node_id``, ``short_id``, a settable ``parent`` back-link, and a settable
``children`` sequence (list or tuple, preserved either way).
``buffer_range`` -- an optional ``(start, end)`` byte span -- is read and,
for ``delete``, updated when present; its absence is never a hard failure.
Every operation returns the single shared :class:`MutationResult`.

API choices made where {p010}/{p107}/{p108} under-specify the exact shape:
``insert`` takes one ``incoming`` root and a ``parent`` and/or ``sibling``
reference -- each a short_id, a UUID4, or an already-resolved node --
normalized before use ({p107}). ``delete``/``replace_range`` take
``targets``: a reference or a non-empty sequence naming an existing,
contiguous run of one parent's children, in order; one reference
removes/replaces that node with its whole subtree (inherent, since
descendants are only reachable through it), a multi-element sequence acts
on a contiguous sibling range ({p010}). ``replace_range``'s incoming side
is a non-empty sequence of new sibling roots, each preflighted with its
own ``validate_mutation`` call ({p108}'s "runs the same insertion
preflight"), plus a same-batch node_id-collision guard since
``validate_mutation`` never sees two calls' roots together. The old range
is removed and the new one inserted through one combined ``children``
assignment -- no reader ever observes the range missing with nothing yet
in its place ({p108}'s "does not publish an intermediate deletion").

Out of scope, owned by sibling files: automatic reparse of edited text
(``reparse.py``); attribute/body/source-fragment/identifier updates
(``updates.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.validation import (
    ShortIdReassignment,
    ValidationError,
    validate_mutation,
)
from tree_engine.errors import ErrorCode

__all__ = ["MutationError", "MutationResult", "insert", "delete", "replace_range"]

_BEFORE_AFTER = frozenset({"before", "after"})
_PARENT_POSITIONS = frozenset({"first_child", "last_child", "child_index"})


class MutationError(Exception):
    """Raised before any write, carrying the never-empty ``errors`` list
    from the shared preflight validator or this file's own reference-
    resolution / contiguity pre-checks."""

    def __init__(self, errors: Sequence[ValidationError]) -> None:
        self.errors: List[ValidationError] = list(errors)
        summary = "; ".join(f"{e.code.value}: {e.message}" for e in self.errors)
        super().__init__(summary or "mutation rejected")


@dataclass(frozen=True)
class MutationResult:
    """Shared result: affected root ``node_id``/``short_id`` (the inserted
    node for ``insert``, the shared parent for ``delete``/``replace_range``),
    final ``position``, the applied short_id ``remap``, and the touched
    ``removed``/``inserted`` :class:`~tree_engine.core.identity.NodeAddress`
    values."""

    node_id: Optional[UUID]
    short_id: Optional[Any]
    position: Optional[int]
    remap: Tuple[ShortIdReassignment, ...] = ()
    removed: Tuple[NodeAddress, ...] = ()
    inserted: Tuple[NodeAddress, ...] = ()

# -- internal helpers -------------------------------------------------------


def _parse_uuid(value: Any) -> Optional[UUID]:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _resolve(document: Any, ref: Any) -> Optional[Any]:
    """Normalize ``ref`` (a node, a short_id, or a UUID4) to a node object.
    An already-resolved node is accepted only if it is literally the object
    stored under its own ``node_id`` in ``document.nodes_by_id`` (rejecting
    look-alikes, e.g. a bare ``NodeAddress``). Otherwise ``ref`` is tried as
    a UUID4, then as a short_id against ``short_id_index`` when present,
    then via a linear short_id scan -- so a short_id resolves exactly as
    reliably as a UUID4, per {p107}."""
    if ref is None:
        return None
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    candidate_id = getattr(ref, "node_id", None)
    if candidate_id is not None and nodes_by_id.get(candidate_id) is ref:
        return ref
    parsed = _parse_uuid(ref)
    if parsed is not None and parsed in nodes_by_id:
        return nodes_by_id[parsed]
    short_index = getattr(document, "short_id_index", None)
    if isinstance(short_index, dict) and ref in short_index:
        return nodes_by_id.get(short_index[ref])
    for node in nodes_by_id.values():
        if getattr(node, "short_id", None) == ref:
            return node
    return None


def _children_list(node: Any) -> List[Any]:
    return list(getattr(node, "children", None) or ())


def _set_children(node: Any, children: Sequence[Any]) -> None:
    if isinstance(getattr(node, "children", None), tuple):
        node.children = tuple(children)
    else:
        node.children = list(children)


def _address(document: Any, node: Any) -> NodeAddress:
    return NodeAddress(document_id=getattr(document, "document_id", None), node_id=getattr(node, "node_id", None))


def _fragment_nodes(root: Any) -> List[Any]:
    """Pre-order ``root`` and every descendant (mirrors validation.py)."""
    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        stack = list(getattr(node, "children", None) or ()) + stack
    return ordered


def _apply_short_id_plan(fragment_nodes: Sequence[Any], plan: Sequence[ShortIdReassignment]) -> None:
    by_id = {getattr(n, "node_id", None): n for n in fragment_nodes}
    for entry in plan:
        node = by_id.get(entry.node_id)
        if node is not None and hasattr(node, "short_id"):
            node.short_id = entry.new_short_id


def _register_fragment(document: Any, fragment_nodes: Sequence[Any]) -> None:
    nodes_by_id = getattr(document, "nodes_by_id", None)
    if nodes_by_id is None:
        nodes_by_id = {}
        document.nodes_by_id = nodes_by_id
    short_index = getattr(document, "short_id_index", None)
    for node in fragment_nodes:
        node_id = getattr(node, "node_id", None)
        if node_id is not None:
            nodes_by_id[node_id] = node
        if isinstance(short_index, dict):
            short_id = getattr(node, "short_id", None)
            if short_id is not None:
                short_index[short_id] = node_id


def _unregister_subtree(document: Any, root: Any) -> None:
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    short_index = getattr(document, "short_id_index", None)
    for node in _fragment_nodes(root):
        nodes_by_id.pop(getattr(node, "node_id", None), None)
        if isinstance(short_index, dict):
            short_index.pop(getattr(node, "short_id", None), None)
    if hasattr(root, "parent"):
        root.parent = None


def _range_byte_length(nodes: Sequence[Any]) -> int:
    ranges = [getattr(n, "buffer_range", None) for n in nodes]
    if not ranges or any(r is None for r in ranges):
        return 0
    return ranges[-1][1] - ranges[0][0]


def _shrink_range(node: Any, removed_length: int) -> None:
    rng = getattr(node, "buffer_range", None)
    if rng is not None and hasattr(node, "buffer_range"):
        node.buffer_range = (rng[0], rng[1] - removed_length)


def _shift_subtree(node: Any, delta: int) -> None:
    rng = getattr(node, "buffer_range", None)
    if rng is not None and hasattr(node, "buffer_range"):
        node.buffer_range = (rng[0] + delta, rng[1] + delta)
    for child in _children_list(node):
        _shift_subtree(child, delta)


def _resolve_contiguous_range(document: Any, targets: Any) -> Tuple[List[Any], Any, int, int]:
    """Resolve ``targets`` to an ordered, contiguous sibling run, shared by
    ``delete``/``replace_range``. Returns ``(resolved_nodes, parent_node,
    start_index, end_index)``; raises :class:`MutationError` -- no mutation
    performed -- when a reference does not resolve, the nodes do not share
    one parent, or they are not contiguous, in order, among its children."""
    refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]
    if not refs:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="at least one target is required")])
    resolved: List[Any] = []
    for ref in refs:
        node = _resolve(document, ref)
        if node is None:
            raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"target could not be resolved: {ref!r}")])
        resolved.append(node)
    parent_node = getattr(resolved[0], "parent", None)
    if parent_node is None:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="target has no resolvable parent")])
    for node in resolved[1:]:
        if getattr(node, "parent", None) is not parent_node:
            raise MutationError([ValidationError(code=ErrorCode.INVALID_POSITION, message="targets do not share the same parent")])
    siblings = _children_list(parent_node)
    try:
        start = siblings.index(resolved[0])
    except ValueError:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="target is not among its parent's children")])
    end = start + len(resolved)
    if siblings[start:end] != resolved:
        raise MutationError(
            [ValidationError(code=ErrorCode.INVALID_POSITION, message="targets are not a contiguous sibling range in the given order")]
        )
    return resolved, parent_node, start, end

# -- public operations --------------------------------------------------


def insert(
    document: Any, incoming: Any, *, position: str, parent: Any = None, sibling: Any = None,
    index: Optional[int] = None,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None, loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None, next_short_id: Optional[Callable[[], Any]] = None,
) -> MutationResult:
    """Insert ``incoming`` at one {p107} positional address: ``first_child``,
    ``last_child``, ``child_index`` (with ``index``), ``before``, or
    ``after``. ``parent``/``sibling`` are each a short_id, a UUID4, or an
    already-resolved node, normalized before use; ``before``/``after``
    resolve their parent from the sibling when ``parent`` is not given."""
    parent_node = _resolve(document, parent) if parent is not None else None
    sibling_node = _resolve(document, sibling) if sibling is not None else None
    if position in _BEFORE_AFTER:
        if sibling_node is None:
            raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"sibling could not be resolved: {sibling!r}")])
        if parent_node is None:
            parent_node = getattr(sibling_node, "parent", None)
        if parent_node is None:
            raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="sibling has no resolvable parent")])
        siblings = _children_list(parent_node)
        try:
            anchor = siblings.index(sibling_node)
        except ValueError:
            raise MutationError([ValidationError(code=ErrorCode.INVALID_POSITION, message="sibling is not a child of its parent")])
        splice_index = anchor if position == "before" else anchor + 1
    elif position in _PARENT_POSITIONS:
        if parent_node is None:
            raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"parent could not be resolved: {parent!r}")])
        siblings = _children_list(parent_node)
        if position == "first_child":
            splice_index = 0
        elif position == "last_child":
            splice_index = len(siblings)
        else:
            splice_index = 0 if index is None else max(0, min(index, len(siblings)))
    else:
        raise MutationError([ValidationError(code=ErrorCode.INVALID_POSITION, message=f"unrecognized position: {position!r}")])

    result = validate_mutation(
        document, incoming, parent=parent_node, position=position, index=index,
        is_type_compatible=is_type_compatible, references=references,
        loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=next_short_id,
    )
    if not result.success:
        raise MutationError(result.errors)
    fragment_nodes = _fragment_nodes(incoming)
    _apply_short_id_plan(fragment_nodes, result.short_id_plan)
    siblings = _children_list(parent_node)
    siblings.insert(splice_index, incoming)
    _set_children(parent_node, siblings)
    if hasattr(incoming, "parent"):
        incoming.parent = parent_node
    _register_fragment(document, fragment_nodes)
    return MutationResult(
        node_id=getattr(incoming, "node_id", None),
        short_id=getattr(incoming, "short_id", None),
        position=splice_index,
        remap=tuple(result.short_id_plan),
        inserted=(_address(document, incoming),),
    )


def delete(document: Any, targets: Any) -> MutationResult:
    """Delete a node, a contiguous sibling range, or a subtree ({p010}).
    ``targets`` is a reference (short_id, UUID4, or node) or a non-empty
    sequence naming an existing contiguous run of one parent's children, in
    order; each removed node's whole subtree is purged from
    ``nodes_by_id``/``short_id_index`` with it. Parent links, sibling
    order, and -- when every touched node exposes ``buffer_range`` -- text
    ranges (parent shrinks, later siblings shift left) are updated only
    after every target resolves and the range is confirmed contiguous."""
    resolved, parent_node, start, end = _resolve_contiguous_range(document, targets)
    removed_length = _range_byte_length(resolved)
    removed_addresses = tuple(_address(document, node) for node in resolved)
    siblings = _children_list(parent_node)
    remaining = siblings[:start] + siblings[end:]
    _set_children(parent_node, remaining)
    if removed_length:
        _shrink_range(parent_node, removed_length)
        for later in remaining[start:]:
            _shift_subtree(later, -removed_length)
    for node in resolved:
        _unregister_subtree(document, node)
    return MutationResult(
        node_id=getattr(parent_node, "node_id", None),
        short_id=getattr(parent_node, "short_id", None),
        position=start,
        removed=removed_addresses,
    )


def replace_range(
    document: Any, targets: Any, incoming: Sequence[Any], *,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None, loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None, next_short_id: Optional[Callable[[], Any]] = None,
) -> MutationResult:
    """Atomically replace a contiguous sibling range ({p108}). ``targets``
    names the existing contiguous range to remove (see :func:`delete`).
    ``incoming`` is a non-empty sequence of new sibling roots; each is
    preflighted with its own ``validate_mutation`` call against the
    range's parent, all running to completion before anything is written.
    The old range is removed and the new one inserted through one combined
    ``children`` assignment, so no intermediate, range-missing state is
    ever observable."""
    resolved, parent_node, start, end = _resolve_contiguous_range(document, targets)
    incoming_roots = list(incoming)
    if not incoming_roots:
        raise MutationError([ValidationError(code=ErrorCode.INVALID_SELECTOR, message="at least one incoming node is required")])
    all_fragment_nodes: List[Any] = []
    for root in incoming_roots:
        all_fragment_nodes.extend(_fragment_nodes(root))
    seen_ids: set = set()
    for node in all_fragment_nodes:
        raw_id = getattr(node, "node_id", None)
        if raw_id is not None and raw_id in seen_ids:
            raise MutationError([ValidationError(code=ErrorCode.NODE_ID_CONFLICT, message=f"node_id repeated in incoming batch: {raw_id!r}")])
        seen_ids.add(raw_id)
    all_errors: List[ValidationError] = []
    combined_plan: List[ShortIdReassignment] = []
    for root in incoming_roots:
        result = validate_mutation(
            document, root, parent=parent_node, position="child_index", index=start,
            is_type_compatible=is_type_compatible, references=references,
            loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=next_short_id,
        )
        if not result.success:
            all_errors.extend(result.errors)
        else:
            combined_plan.extend(result.short_id_plan)
    if all_errors:
        raise MutationError(all_errors)
    removed_addresses = tuple(_address(document, node) for node in resolved)
    _apply_short_id_plan(all_fragment_nodes, combined_plan)
    for root in incoming_roots:
        if hasattr(root, "parent"):
            root.parent = parent_node
    siblings = _children_list(parent_node)
    new_siblings = siblings[:start] + incoming_roots + siblings[end:]
    _set_children(parent_node, new_siblings)
    for node in resolved:
        _unregister_subtree(document, node)
    _register_fragment(document, all_fragment_nodes)
    inserted_addresses = tuple(_address(document, root) for root in incoming_roots)
    return MutationResult(
        node_id=getattr(parent_node, "node_id", None),
        short_id=getattr(parent_node, "short_id", None),
        position=start,
        remap=tuple(combined_plan),
        removed=removed_addresses,
        inserted=inserted_addresses,
    )
