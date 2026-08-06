"""Shared preflight mutation-validation pipeline (concept C-006, {p009}).

This module implements the single entry point every mutation operation in
this task family (``insert``, ``replace_range``, ``replace_node_id``, an
incoming cross-document ``move``, a subtree ``apply``, or a
``parse_fragment`` result) must call before any tree or index-map change is
applied. Per {p009}, :func:`validate_mutation` checks, in order:

  1. UUID4 format validity of every node_id carried by the incoming node
     or fragment.
  2. node_id conflicts against the target document's existing identity
     map.
  3. parent/position type compatibility.
  4. cycle formation.
  5. resolvability of references touched by the change.
  6. the remaining structural invariants of the tree (here: the
     positional-addressing literal used by ``insert``, per {p107}).

Every failure is reported as a distinct :class:`ValidationError` carrying
the matching :class:`~tree_engine.errors.ErrorCode`, never a generic
exception. All six stages run to completion and accumulate failures; the
pipeline never stops at the first one, so independent and combined failure
scenarios are both fully reported by a single call.

For any node arriving without a ``short_id``, and for a fragment carried
over from another document, this module computes a *plan* describing which
short_id values must be reassigned -- it never allocates an identifier
itself. A free short_id (present, and not conflicting with the target
document) is left completely untouched: it never appears in the plan. A
missing or conflicting short_id becomes a plan entry; the fresh value is
obtained by invoking the caller-supplied ``next_short_id`` allocator (the
existing allocator contract owned by ``short_id.py``), never by any ad hoc
scheme invented here.

Sibling contracts that are not yet available as importable modules in this
worktree -- the parent/position compatibility rules of ``node_types.py``
and the ``next_short_id`` allocator of ``short_id.py`` -- are consumed
here only as caller-injected, duck-typed callables, and the incoming
node/fragment and the target document are consumed only through the
minimal structural (duck-typed) attributes documented on
:func:`validate_mutation`. This file imports neither sibling module, so it
can be exercised today and wired to the real modules later without any
change to its own code.

This module performs no mutation of any tree or index map, and allocates
no identifier of its own, in any code path: the atomic application of a
validated change belongs to the sibling atomic-tree-operations file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

from tree_engine.errors import ErrorCode

__all__ = [
    "ValidationError",
    "ValidationResult",
    "ShortIdReassignment",
    "validate_mutation",
]


_VALID_POSITIONS = frozenset(
    {"first_child", "last_child", "child_index", "before", "after"}
)


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationError:
    """One distinct preflight validation failure.

    ``code`` is the exact :class:`~tree_engine.errors.ErrorCode` naming the
    failure category; a generic exception is never used in its place.
    ``message`` is a human-readable detail for logs and diagnostics.
    ``node_id`` optionally pins the failure to the offending node: a
    ``uuid.UUID`` when the identifier parsed, or the raw offending value
    when it did not (e.g. a malformed UUID4 string).
    """

    code: ErrorCode
    message: str
    node_id: Optional[Any] = None


@dataclass(frozen=True)
class ShortIdReassignment:
    """One entry of the short_id reassignment plan.

    ``node_id`` identifies the node this entry belongs to; it disambiguates
    entries when several incoming nodes share ``old_short_id is None``, so
    the plan cannot be a bare ``{old_short_id: new_short_id}`` dict.
    ``old_short_id`` is the short_id the node arrived with, or ``None``
    when it had none. ``new_short_id`` is the fresh value obtained from the
    caller-supplied ``next_short_id`` allocator, or ``None`` when no
    allocator was supplied to this call (the entry still records that a
    reassignment is required; no value is invented locally).
    """

    node_id: Any
    old_short_id: Optional[Any]
    new_short_id: Optional[Any]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of one :func:`validate_mutation` call.

    ``success`` is ``True`` exactly when ``errors`` is empty. ``errors`` is
    the ordered list of distinct failures found, in the order the checks
    that produced them ran ({p009}'s six-stage order). ``short_id_plan`` is
    the ordered short_id reassignment plan, populated only when ``success``
    is ``True``: a free short_id is left out entirely, and only a true
    conflict (or a node missing a short_id) appears as an entry.
    """

    success: bool
    errors: List[ValidationError] = field(default_factory=list)
    short_id_plan: List[ShortIdReassignment] = field(default_factory=list)


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _parse_uuid4(value: Any) -> Optional[UUID]:
    """Return ``value`` as a UUID4 ``UUID``, or ``None`` if it is not one."""

    candidate: Optional[UUID]
    if isinstance(value, UUID):
        candidate = value
    else:
        try:
            candidate = UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            candidate = None
    if candidate is None or candidate.version != 4:
        return None
    return candidate


def _iter_fragment_nodes(root: Any) -> List[Any]:
    """Return ``root`` and every descendant, pre-order.

    ``children`` is read as a duck-typed, optional attribute: absent or
    ``None`` means a leaf. This is the only shape assumed of the incoming
    node/fragment object's internal structure.
    """

    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        children = list(getattr(node, "children", None) or ())
        stack = children + stack
    return ordered


def _node_id_of(node: Any) -> Any:
    return getattr(node, "node_id", None)


def _short_id_of(node: Any) -> Any:
    return getattr(node, "short_id", None)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def validate_mutation(
    document: Any,
    incoming: Any,
    *,
    parent: Any = None,
    position: Optional[str] = None,
    index: Optional[int] = None,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None,
    next_short_id: Optional[Callable[[], Any]] = None,
) -> ValidationResult:
    """Run the shared {p009} preflight pipeline once and return its result.

    Args:
        document: the target document. Duck-typed: read via
            ``document.nodes_by_id`` (a mapping of node_id -> node, the
            same attribute name ``identity.replace_node_id`` already
            relies on) and, optionally, ``document.document_id``. Never
            mutated.
        incoming: the node or fragment root being introduced. Duck-typed:
            ``node_id`` (required), optional ``short_id``, optional
            ``children`` (an iterable of same-shaped nodes, for a
            fragment). Never mutated.
        parent: the prospective parent node, when the change attaches
            ``incoming`` under a parent (``insert``, a subtree apply, an
            incoming move). Duck-typed: optional ``node_id`` and ``parent``
            (its own parent, walked upward for cycle detection). ``None``
            when the change has no parent/position dimension (e.g.
            ``replace_node_id``).
        position: one of ``"first_child"``, ``"last_child"``,
            ``"child_index"``, ``"before"``, ``"after"``, or ``None`` when
            not applicable, per the {p107} addressing modes.
        index: the sibling index; required only when ``position ==
            "child_index"``.
        is_type_compatible: the node-type compatibility rules already
            provided by ``node_types.py``, injected as a callable
            ``(parent, position, incoming) -> bool`` because that module is
            not yet importable from this file. When omitted, the
            compatibility check is skipped (treated as compatible) rather
            than guessed at.
        references: the references touched by the change, each duck-typed
            with a required ``node_id`` (or given directly as a bare
            id/UUID) and an optional ``document_id`` (``None`` meaning the
            target document). Resolved against ``document.nodes_by_id``
            for a local reference, or against
            ``loaded_documents[document_id].nodes_by_id`` for a
            cross-document one.
        loaded_documents: mapping of ``document_id -> document-like``
            object (each exposing ``nodes_by_id``) for resolving a
            cross-document reference. A cross-document reference whose
            document is absent here is reported unresolved.
        used_short_ids: the short_id values already allocated in the
            target document, as known by the caller (typically read from
            the document's short_id index maintained by ``short_id.py``).
        next_short_id: the existing ``next_short_id`` allocator from
            ``short_id.py``, injected as a zero-argument callable because
            that module is not yet importable from this file. Called only
            for a node that needs a fresh short_id (missing or
            conflicting); never called for a free short_id, and never
            called at all when validation fails.

    Returns:
        A :class:`ValidationResult` whose ``success`` is ``True`` iff
        ``errors`` is empty, in which case ``short_id_plan`` carries the
        reassignment plan. No tree, index map, or identifier is ever
        allocated or mutated by this function, in any code path.
    """

    errors: List[ValidationError] = []
    fragment_nodes = _iter_fragment_nodes(incoming)
    nodes_by_id = getattr(document, "nodes_by_id", None)
    if nodes_by_id is None:
        nodes_by_id = {}

    # 1. UUID4 format validity, for every node in the incoming node/fragment.
    parsed_ids: List[Optional[UUID]] = []
    for node in fragment_nodes:
        raw_id = _node_id_of(node)
        parsed = _parse_uuid4(raw_id) if raw_id is not None else None
        parsed_ids.append(parsed)
        if parsed is None:
            errors.append(
                ValidationError(
                    code=ErrorCode.INVALID_SELECTOR,
                    message=f"node_id is not a syntactically valid UUID4: {raw_id!r}",
                    node_id=raw_id,
                )
            )

    # 2. node_id conflicts against the document's existing identity map.
    for parsed in parsed_ids:
        if parsed is not None and parsed in nodes_by_id:
            errors.append(
                ValidationError(
                    code=ErrorCode.NODE_ID_CONFLICT,
                    message=f"node_id already present in the document: {parsed}",
                    node_id=parsed,
                )
            )

    # 3. parent/position type compatibility, using the node-type
    #    compatibility rules injected from node_types.py.
    if is_type_compatible is not None and not is_type_compatible(parent, position, incoming):
        errors.append(
            ValidationError(
                code=ErrorCode.INVALID_PARENT_TYPE,
                message="incoming node type is not admissible under the chosen parent and position",
                node_id=_node_id_of(incoming),
            )
        )

    # 4. cycle formation: none of the incoming fragment's own node_ids may
    #    already sit among the ancestors of the target parent.
    if parent is not None:
        incoming_parsed_ids = {p for p in parsed_ids if p is not None}
        incoming_raw_ids = {_node_id_of(node) for node in fragment_nodes}
        ancestor = parent
        visited_ancestor_object_ids: set = set()
        while ancestor is not None and id(ancestor) not in visited_ancestor_object_ids:
            visited_ancestor_object_ids.add(id(ancestor))
            ancestor_raw_id = getattr(ancestor, "node_id", None)
            ancestor_parsed_id = _parse_uuid4(ancestor_raw_id) if ancestor_raw_id is not None else None
            if ancestor_raw_id in incoming_raw_ids or (
                ancestor_parsed_id is not None and ancestor_parsed_id in incoming_parsed_ids
            ):
                errors.append(
                    ValidationError(
                        code=ErrorCode.CYCLE_DETECTED,
                        message="attaching the incoming node/fragment under this parent would introduce a cycle",
                        node_id=_node_id_of(incoming),
                    )
                )
                break
            ancestor = getattr(ancestor, "parent", None)

    # 5. resolvability of references touched by the change.
    own_document_id = getattr(document, "document_id", None)
    for reference in references or ():
        ref_node_id = getattr(reference, "node_id", reference)
        ref_document_id = getattr(reference, "document_id", None)
        if ref_document_id is None or ref_document_id == own_document_id:
            target_map = nodes_by_id
        else:
            target_document = (loaded_documents or {}).get(ref_document_id)
            target_map = getattr(target_document, "nodes_by_id", None) if target_document is not None else None
        if target_map is None or ref_node_id not in target_map:
            errors.append(
                ValidationError(
                    code=ErrorCode.UNRESOLVED_REFERENCE,
                    message=f"reference cannot be resolved: {ref_node_id!r}",
                    node_id=ref_node_id,
                )
            )

    # 6. remaining structural invariants: the {p107} positional-addressing
    #    literal, when a parent/position dimension applies to this change.
    if position is not None and position not in _VALID_POSITIONS:
        errors.append(
            ValidationError(
                code=ErrorCode.INVALID_POSITION,
                message=f"position is not one of {sorted(_VALID_POSITIONS)}: {position!r}",
            )
        )
    elif position == "child_index" and (
        index is None or isinstance(index, bool) or not isinstance(index, int) or index < 0
    ):
        errors.append(
            ValidationError(
                code=ErrorCode.INVALID_POSITION,
                message=f"child_index position requires a non-negative integer index, got {index!r}",
            )
        )

    if errors:
        return ValidationResult(success=False, errors=errors, short_id_plan=[])

    # Compute the short_id reassignment plan. Only reachable on success, and
    # no identifier is generated here: a fresh value is only ever obtained
    # by invoking the caller-supplied next_short_id allocator.
    used = set(used_short_ids or ())
    plan: List[ShortIdReassignment] = []
    for node in fragment_nodes:
        old_short_id = _short_id_of(node)
        if old_short_id is not None and old_short_id not in used:
            continue  # free short_id: left completely untouched.
        new_short_id = next_short_id() if next_short_id is not None else None
        plan.append(
            ShortIdReassignment(
                node_id=_node_id_of(node),
                old_short_id=old_short_id,
                new_short_id=new_short_id,
            )
        )

    return ValidationResult(success=True, errors=[], short_id_plan=plan)
