"""Atomic subtree move: intra-document and cross-document (concept C-020).

Scope, narrowed exactly to what this atomic step owns per {p009}/{p039}:
this file is the transaction orchestrator for :func:`move`. It owns locking
order, running the shared C-006 preflight validator against the target
document before any mutation, structural relocation (detach from the
source, reattach in the target) with full rollback on any failure, UUID4
identity preservation, and target-document short_id reassignment (free
short_ids kept, conflicting ones reassigned from the target's own
allocator, with the old->new remap returned to the caller). It never
implements reference conversion and never implements the move contract
tests -- both are sibling artifacts.

Two sibling facilities are not yet importable modules in this worktree, so,
following the precedent set by ``validation.py``'s ``next_short_id`` and
``address.py``'s ``resolve_short_id``, both are consumed here only as
caller-injected, duck-typed callables -- this file never imports either
sibling module and never stubs a fake replacement for it:

* ``lock_coordinator`` -- the sibling ``locking.py`` facility. Called as
  ``lock_coordinator(document_ids)`` with the participating ``document_id``
  values already sorted here in deterministic UUID4 order (per {p035}), and
  used as a context manager: ``with lock_coordinator(document_ids): ...``.
  ``None`` means no locking is attempted, mirroring ``validate_mutation``'s
  own ``is_type_compatible=None`` "skip rather than guess" convention.
* ``reconcile_references`` -- the sibling move-references file's reference
  reconciliation, called once as ``reconcile_references(source_document=...,
  target_document=..., moved_roots=..., short_id_remap=...,
  loaded_documents=...)`` after the structural relocation. It must return an
  object exposing ``.apply(source_document, target_document,
  loaded_documents)`` -- the duck-typed "ReferenceDelta" contract -- called
  inside the same rollback scope as the structural change. ``None`` means no
  reconciliation is attempted.

Duck-typed ``document``/``node`` contract, identical to ``operations.py``'s:
``document.nodes_by_id`` (mutable node_id -> node), an optional
``document.short_id_index`` (short_id -> node_id), an optional
``document.document_id``; a node exposes ``node_id``, an optional
``short_id``, a settable ``parent`` back-link, a settable ``children``
sequence, and an optional ``buffer_range`` ``(start, end)`` pair.

Rollback: every mutation this file performs directly (children splices,
index-map registration/unregistration, short_id/parent/buffer_range writes)
is recorded on a changelog before it happens. Validation failure mutates
nothing, so both documents are left byte-for-byte as given. A failure after
that -- including the injected ``reconcile_references``/``.apply`` call --
undoes every recorded change, in reverse order, before re-raising, so a
mid-move failure still leaves both documents exactly as they were.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.validation import (
    ShortIdReassignment,
    ValidationError,
    validate_mutation,
)
from tree_engine.errors import ErrorCode

__all__ = ["MoveError", "MoveResult", "move"]

_BEFORE_AFTER = frozenset({"before", "after"})
_PARENT_POSITIONS = frozenset({"first_child", "last_child", "child_index"})


class MoveError(Exception):
    """Raised before any mutation, or after a full rollback of one. Carries
    the never-empty ``errors`` list from the shared preflight validator
    (e.g. ``NODE_ID_CONFLICT``) or this file's own resolution/contiguity
    pre-checks."""

    def __init__(self, errors: Sequence[ValidationError]) -> None:
        self.errors: List[ValidationError] = list(errors)
        summary = "; ".join(f"{e.code.value}: {e.message}" for e in self.errors)
        super().__init__(summary or "move rejected")


@dataclass(frozen=True)
class MoveResult:
    """Outcome of one successful :func:`move` call. ``node_id``/``short_id``
    name the first moved root; ``position`` is its final index among the
    target parent's children. ``remap`` is the old_short_id ->
    new_short_id reassignment plan applied in the target document (free
    short_ids never appear in it). ``removed``/``inserted`` are the moved
    nodes' addresses in the source/target document -- same UUID4 ``node_id``,
    per {p039} only ``document_id`` changes for a cross-document move.
    ``reference_delta`` is whatever the injected ``reconcile_references``
    callable returned (``None`` when it was not supplied)."""

    node_id: Optional[UUID]
    short_id: Optional[Any]
    position: Optional[int]
    remap: Tuple[ShortIdReassignment, ...] = ()
    removed: Tuple[NodeAddress, ...] = ()
    inserted: Tuple[NodeAddress, ...] = ()
    reference_delta: Any = None


# -- internal helpers (duplicated in miniature from the sibling operations.py,
# which is the established precedent for this -- see updates.py) -----------


def _resolve(document: Any, ref: Any) -> Optional[Any]:
    if ref is None:
        return None
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    candidate_id = getattr(ref, "node_id", None)
    if candidate_id is not None and nodes_by_id.get(candidate_id) is ref:
        return ref
    if isinstance(ref, UUID) and ref in nodes_by_id:
        return nodes_by_id[ref]
    short_index = getattr(document, "short_id_index", None)
    if isinstance(short_index, dict) and ref in short_index:
        return nodes_by_id.get(short_index[ref])
    for node in nodes_by_id.values():
        if getattr(node, "short_id", None) == ref:
            return node
    return None


def _children_list(node: Any) -> List[Any]:
    return list(getattr(node, "children", None) or ())


def _address(document: Any, node: Any) -> NodeAddress:
    return NodeAddress(document_id=getattr(document, "document_id", None), node_id=getattr(node, "node_id", None))


def _fragment_nodes(root: Any) -> List[Any]:
    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        stack = list(getattr(node, "children", None) or ()) + stack
    return ordered


def _range_byte_length(nodes: Sequence[Any]) -> int:
    ranges = [getattr(n, "buffer_range", None) for n in nodes]
    if not ranges or any(r is None for r in ranges):
        return 0
    return ranges[-1][1] - ranges[0][0]


def _resolve_source_range(document: Any, targets: Any) -> Tuple[List[Any], Any, int, int]:
    """Resolve ``targets`` (mirrors ``operations._resolve_contiguous_range``)."""
    refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]
    if not refs:
        raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="at least one target is required")])
    resolved: List[Any] = []
    for ref in refs:
        node = _resolve(document, ref)
        if node is None:
            raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"target could not be resolved: {ref!r}")])
        resolved.append(node)
    parent_node = getattr(resolved[0], "parent", None)
    if parent_node is None:
        raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="target has no resolvable parent")])
    for node in resolved[1:]:
        if getattr(node, "parent", None) is not parent_node:
            raise MoveError([ValidationError(code=ErrorCode.INVALID_POSITION, message="targets do not share the same parent")])
    siblings = _children_list(parent_node)
    try:
        start = siblings.index(resolved[0])
    except ValueError:
        raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="target is not among its parent's children")])
    end = start + len(resolved)
    if siblings[start:end] != resolved:
        raise MoveError([ValidationError(code=ErrorCode.INVALID_POSITION, message="targets are not a contiguous sibling range in the given order")])
    return resolved, parent_node, start, end


def _resolve_target_position(target_document: Any, position: str, parent: Any, sibling: Any, index: Optional[int]) -> Tuple[Any, int]:
    """Resolve the target attach point (mirrors ``operations.insert``). Read-only."""
    parent_node = _resolve(target_document, parent) if parent is not None else None
    sibling_node = _resolve(target_document, sibling) if sibling is not None else None
    if position in _BEFORE_AFTER:
        if sibling_node is None:
            raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"sibling could not be resolved: {sibling!r}")])
        if parent_node is None:
            parent_node = getattr(sibling_node, "parent", None)
        if parent_node is None:
            raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message="sibling has no resolvable parent")])
        siblings = _children_list(parent_node)
        try:
            anchor = siblings.index(sibling_node)
        except ValueError:
            raise MoveError([ValidationError(code=ErrorCode.INVALID_POSITION, message="sibling is not a child of its parent")])
        return parent_node, (anchor if position == "before" else anchor + 1)
    if position in _PARENT_POSITIONS:
        if parent_node is None:
            raise MoveError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"parent could not be resolved: {parent!r}")])
        siblings = _children_list(parent_node)
        if position == "first_child":
            return parent_node, 0
        if position == "last_child":
            return parent_node, len(siblings)
        return parent_node, (0 if index is None else max(0, min(index, len(siblings))))
    raise MoveError([ValidationError(code=ErrorCode.INVALID_POSITION, message=f"unrecognized position: {position!r}")])


# -- rollback changelog: zero-arg undo callables, run in reverse order ------


def _log_setattr(log: List[Callable[[], None]], obj: Any, name: str, value: Any) -> None:
    old = getattr(obj, name, None)
    setattr(obj, name, value)
    log.append(lambda: setattr(obj, name, old))


def _log_dict_set(log: List[Callable[[], None]], mapping: Dict[Any, Any], key: Any, value: Any) -> None:
    existed = key in mapping
    old = mapping.get(key)
    mapping[key] = value
    log.append((lambda: mapping.__setitem__(key, old)) if existed else (lambda: mapping.pop(key, None)))


def _log_dict_pop(log: List[Callable[[], None]], mapping: Dict[Any, Any], key: Any) -> None:
    if key in mapping:
        old = mapping[key]
        del mapping[key]
        log.append(lambda: mapping.__setitem__(key, old))


def _detach(document: Any, resolved: Sequence[Any], parent_node: Any, start: int, end: int, log: List[Callable[[], None]]) -> None:
    siblings = _children_list(parent_node)
    _log_setattr(log, parent_node, "children", tuple(siblings[:start] + siblings[end:]) if isinstance(getattr(parent_node, "children", None), tuple) else siblings[:start] + siblings[end:])
    removed_length = _range_byte_length(resolved)
    if removed_length:
        rng = getattr(parent_node, "buffer_range", None)
        if rng is not None:
            _log_setattr(log, parent_node, "buffer_range", (rng[0], rng[1] - removed_length))
        for later in siblings[end:]:
            _shift(later, -removed_length, log)
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    short_index = getattr(document, "short_id_index", None)
    for root in resolved:
        for node in _fragment_nodes(root):
            _log_dict_pop(log, nodes_by_id, getattr(node, "node_id", None))
            if isinstance(short_index, dict):
                _log_dict_pop(log, short_index, getattr(node, "short_id", None))
        _log_setattr(log, root, "parent", None)


def _shift(node: Any, delta: int, log: List[Callable[[], None]]) -> None:
    rng = getattr(node, "buffer_range", None)
    if rng is not None:
        _log_setattr(log, node, "buffer_range", (rng[0] + delta, rng[1] + delta))
    for child in _children_list(node):
        _shift(child, delta, log)


def _attach(target_document: Any, parent_node: Any, splice_index: int, roots: Sequence[Any], log: List[Callable[[], None]]) -> None:
    siblings = _children_list(parent_node)
    new_children = siblings[:splice_index] + list(roots) + siblings[splice_index:]
    _log_setattr(log, parent_node, "children", tuple(new_children) if isinstance(getattr(parent_node, "children", None), tuple) else new_children)
    nodes_by_id = getattr(target_document, "nodes_by_id", None)
    if nodes_by_id is None:
        nodes_by_id = {}
        target_document.nodes_by_id = nodes_by_id
    short_index = getattr(target_document, "short_id_index", None)
    for root in roots:
        _log_setattr(log, root, "parent", parent_node)
        for node in _fragment_nodes(root):
            node_id = getattr(node, "node_id", None)
            if node_id is not None:
                _log_dict_set(log, nodes_by_id, node_id, node)
            if isinstance(short_index, dict):
                short_id = getattr(node, "short_id", None)
                if short_id is not None:
                    _log_dict_set(log, short_index, short_id, node_id)


def _apply_short_id_plan(fragment_nodes: Sequence[Any], plan: Sequence[ShortIdReassignment], log: List[Callable[[], None]]) -> None:
    by_id = {getattr(n, "node_id", None): n for n in fragment_nodes}
    for entry in plan:
        node = by_id.get(entry.node_id)
        if node is not None and hasattr(node, "short_id"):
            _log_setattr(log, node, "short_id", entry.new_short_id)


# -- public entry point ------------------------------------------------


def move(
    source_document: Any,
    targets: Any,
    *,
    position: str,
    target_document: Any = None,
    parent: Any = None,
    sibling: Any = None,
    index: Optional[int] = None,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None,
    next_short_id: Optional[Callable[[], Any]] = None,
    lock_coordinator: Optional[Callable[[Sequence[UUID]], Any]] = None,
    reconcile_references: Optional[Callable[..., Any]] = None,
) -> MoveResult:
    """Move a subtree (or a contiguous sibling range) within one document or
    across two documents, as a single atomic transaction (see module
    docstring). ``targets`` names the existing range to relocate, exactly as
    ``operations.delete`` accepts it. ``position``/``parent``/``sibling``/
    ``index`` address the attach point in ``target_document`` (defaults to
    ``source_document``), exactly as ``operations.insert`` accepts them.

    Both ``document_id`` values are sorted (UUID4 order, per {p035}) before
    ``lock_coordinator`` -- if supplied -- is entered as a context manager
    around the whole operation. The shared preflight validator then runs
    against ``target_document`` with the moved subtree's own node_ids
    excluded from the conflict check (they name themselves, not a new
    collision): a genuine UUID4 collision raises :class:`MoveError` wrapping
    ``NODE_ID_CONFLICT`` before anything is mutated. Only then does the
    structural relocation happen, followed by ``reconcile_references`` and
    its returned delta's ``.apply`` -- both inside the same rollback scope.
    """
    target_document = source_document if target_document is None else target_document
    resolved, src_parent, start, end = _resolve_source_range(source_document, targets)

    src_doc_id = getattr(source_document, "document_id", None)
    tgt_doc_id = getattr(target_document, "document_id", None)
    doc_ids = sorted({d for d in (src_doc_id, tgt_doc_id) if d is not None})
    scope = lock_coordinator(doc_ids) if lock_coordinator is not None else nullcontext()

    with scope:
        parent_node, splice_index = _resolve_target_position(target_document, position, parent, sibling, index)

        # Read-only preflight shim: target_document's nodes_by_id with only
        # the moved nodes' own entries excluded, by object identity (not id
        # value), so an intra-document move is never mistaken for a
        # conflict against itself while a genuine conflict -- a *different*
        # object already holding that UUID4 in the target -- is still caught.
        moved_objects = {id(n) for root in resolved for n in _fragment_nodes(root)}
        real_map = getattr(target_document, "nodes_by_id", None) or {}
        shim = SimpleNamespace(
            nodes_by_id={k: v for k, v in real_map.items() if id(v) not in moved_objects},
            document_id=tgt_doc_id,
        )

        errors: List[ValidationError] = []
        combined_plan: List[ShortIdReassignment] = []
        for root in resolved:
            result = validate_mutation(
                shim, root, parent=parent_node, position=position, index=splice_index,
                is_type_compatible=is_type_compatible, references=references,
                loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=next_short_id,
            )
            if not result.success:
                errors.extend(result.errors)
            else:
                combined_plan.extend(result.short_id_plan)
        if errors:
            raise MoveError(errors)

        # Validation succeeded against the (self-excluded) target view: no
        # mutation has happened yet. Everything from here is logged for
        # rollback on any later failure.
        log: List[Callable[[], None]] = []
        try:
            fragment_nodes = [n for root in resolved for n in _fragment_nodes(root)]
            _detach(source_document, resolved, src_parent, start, end, log)
            _apply_short_id_plan(fragment_nodes, combined_plan, log)
            _attach(target_document, parent_node, splice_index, resolved, log)
            reference_delta = None
            if reconcile_references is not None:
                reference_delta = reconcile_references(
                    source_document=source_document, target_document=target_document,
                    moved_roots=tuple(resolved), short_id_remap=tuple(combined_plan),
                    loaded_documents=loaded_documents,
                )
                apply = getattr(reference_delta, "apply", None)
                if callable(apply):
                    apply(source_document, target_document, loaded_documents)
        except Exception:
            for undo in reversed(log):
                undo()
            raise

        removed_addresses = tuple(_address(source_document, n) for n in resolved)
        inserted_addresses = tuple(_address(target_document, n) for n in resolved)
        first = resolved[0]
        return MoveResult(
            node_id=getattr(first, "node_id", None),
            short_id=getattr(first, "short_id", None),
            position=splice_index,
            remap=tuple(combined_plan),
            removed=removed_addresses,
            inserted=inserted_addresses,
            reference_delta=reference_delta,
        )
