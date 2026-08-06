"""Predicate evaluation for the ported tree-query engine (concept C-009).

Scope (concept C-009, narrowed to predicate evaluation only, per {p005} and
{p019}): this module owns exactly the two functions that decide whether an
already-parsed attribute predicate (or a set of them on one selector step)
holds against a concrete node from the loaded tree -- :func:`evaluate_predicate`
and :func:`evaluate_predicates`. It performs no selector/predicate parsing,
no tree traversal, and no query orchestration.

This is a PORT, not a redesign. The legacy predicate language and its
observable semantics live unchanged in the ``ai_editor`` package's
``cst_query`` modules (``ai_editor.cst_query.ast`` and
``ai_editor.cst_query.executor``). This module is deliberately built
directly on that legacy vocabulary rather than reinventing a parallel one:

* ``Predicate`` and ``PredicateOp`` are imported unchanged from
  ``ai_editor.cst_query.ast`` -- they are exactly what the existing,
  unchanged selector parser (``ai_editor.cst_query.parser.parse_selector``)
  already produces, so no adapter/rewrap step is needed between "parsed
  predicate" and "evaluated predicate".
* Per {p019}, the supported predicate forms are equality (``=``),
  inequality (``!=``), containment (``~=``), prefix match (``^=``) and
  suffix match (``$=``), plus the combination of more than one predicate on
  the same step, all of which must hold together (a logical AND). The
  legacy grammar's numeric comparison operators (``>``, ``<``, ``>=``,
  ``<=``) are not part of this narrowed scope; a predicate carrying one of
  them is treated the same as any other operator this module cannot
  evaluate (see below), consistent with "exactly the predicate forms" the
  atomic step's prompt enumerates.
* Attribute values are read directly off the ``node`` argument -- no tree
  walking, no reparsing, no lookup through any sibling module. ``node`` is
  duck-typed, deliberately compatible with more than one shape so this
  module has no import-time dependency on the sibling traversal adapter
  (written concurrently and not imported here) or on any one node
  representation: a plain ``tree_engine.core.nodes.Node`` (kind/fields),
  a ``tree_engine.core.node_types`` wrapper (``get_attribute``/property
  descriptors, the same convention already used by that module's own
  ``matches(**predicates)`` helper), or any other object exposing the
  attribute directly.

Do not introduce any new predicate-error taxonomy here. Whenever a
predicate cannot be evaluated -- because it names an attribute the node's
shape does not expose, or an operator this module does not support, or an
attribute whose value is itself structural (a child ``Node`` or an ordered
child sequence) rather than a scalar suitable for string comparison -- this
module raises ``ai_editor.core.exceptions.QueryParseError``, imported
unchanged, with no renaming and no subclassing. The stable
``tree_engine.errors.ErrorCode.INVALID_SELECTOR`` catalog code travels
alongside that legacy exception inside its existing ``details`` payload
(key ``"error_code"``), rather than replacing it.

Out of scope, owned by sibling artifacts under G-018/T-001: parsing
selector/predicate syntax from text, tree traversal, semantic-role
resolution, and full query orchestration. This file depends on nothing
from those siblings; it does not import the query-result record type
either, since nothing here needs it for type consistency.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from tree_engine.query.selector import Predicate, PredicateOp, QueryParseError
from tree_engine.errors import ErrorCode

__all__ = [
    "evaluate_predicate",
    "evaluate_predicates",
]

# The narrowed set of operators this atomic step supports, per {p019}. Any
# other member of the legacy ``PredicateOp`` enum (the numeric comparisons)
# is a recognized-but-unsupported operator, not an unknown one.
_SUPPORTED_OPS = (
    PredicateOp.EQ,
    PredicateOp.NE,
    PredicateOp.CONTAINS,
    PredicateOp.PREFIX,
    PredicateOp.SUFFIX,
)

# Scalar value types a string predicate can meaningfully compare against.
# Anything else (a Node, an ordered child sequence, or any other object) is
# a structural value: the node's shape does not support comparing it.
_SCALAR_TYPES = (str, int, float, bool, bytes)


class _Missing:
    """Private sentinel distinguishing "no such attribute" from a real ``None``."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "<missing>"


_MISSING = _Missing()


def _read_attribute(node: Any, attr: str) -> Any:
    """Read ``attr`` off ``node`` without tree walking or reparsing.

    Resolution order, matching the convention already established by
    ``tree_engine.core.node_types``'s own ``matches(**predicates)`` helper:

    1. A ``property`` descriptor on ``type(node)`` (e.g. a node-type
       wrapper's ``.name``) -- read through the descriptor.
    2. A callable ``node.get_attribute(name, default)`` (the node-type
       wrapper contract) -- consulted with the private missing sentinel as
       default so an absent key is distinguishable from a stored ``None``.
    3. A ``node.fields`` mapping (the base ``tree_engine.core.nodes.Node``
       contract) -- looked up directly.
    4. A plain instance attribute (covers first-class ``Node`` slots such
       as ``kind``, and any other duck-typed fixture).

    Returns the private missing sentinel when none of the above resolves
    ``attr``.
    """

    descriptor = getattr(type(node), attr, None)
    if isinstance(descriptor, property):
        return getattr(node, attr)

    get_attribute = getattr(node, "get_attribute", None)
    if callable(get_attribute):
        value = get_attribute(attr, _MISSING)
        if value is not _MISSING:
            return value

    fields = getattr(node, "fields", None)
    if isinstance(fields, Mapping) and attr in fields:
        return fields[attr]

    if hasattr(node, attr):
        return getattr(node, attr)

    return _MISSING


def _invalid_selector(message: str, *, predicate: Predicate) -> QueryParseError:
    """Build the shared legacy exception, with the catalog code attached.

    Always the same, unchanged ``QueryParseError`` class -- never a
    subclass, never a differently named exception -- carrying
    ``ErrorCode.INVALID_SELECTOR`` inside its existing ``details`` dict so
    the stable catalog code travels alongside it.
    """

    return QueryParseError(
        message,
        details={
            "error_code": ErrorCode.INVALID_SELECTOR,
            "attr": predicate.attr,
            "op": predicate.op.value,
        },
    )


def _compare(left: str, op: PredicateOp, right: str) -> bool:
    """Apply one of the five supported string operators; ``op`` is pre-validated."""

    if op == PredicateOp.EQ:
        return left == right
    if op == PredicateOp.NE:
        return left != right
    if op == PredicateOp.CONTAINS:
        return right in left
    if op == PredicateOp.PREFIX:
        return left.startswith(right)
    return left.endswith(right)  # PredicateOp.SUFFIX: the only case left


def evaluate_predicate(predicate: Predicate, node: Any) -> bool:
    """Evaluate one already-parsed ``Predicate`` against a concrete ``node``.

    Reads ``predicate.attr``'s current value directly off ``node`` (see
    :func:`_read_attribute`) and compares it against ``predicate.value``
    using ``predicate.op``. Supports exactly equality, inequality,
    containment, prefix match and suffix match, per {p019}.

    A recognized attribute whose current value is ``None`` simply does not
    match (returns ``False``), the same as the legacy executor: an empty
    value is not a shape problem.

    Raises:
        QueryParseError: (imported unchanged from ``ai_editor.core
            .exceptions``, ``details["error_code"] is
            ErrorCode.INVALID_SELECTOR``) when ``predicate.op`` is outside
            the five supported operators, when ``node`` does not expose
            ``predicate.attr`` at all, or when the attribute resolves to a
            structural value (a child ``Node`` or an ordered child
            sequence) that no string predicate can meaningfully compare.
    """

    if predicate.op not in _SUPPORTED_OPS:
        raise _invalid_selector(
            f"predicate operator {predicate.op.value!r} is not supported by "
            "tree-query predicate evaluation",
            predicate=predicate,
        )

    value = _read_attribute(node, predicate.attr)
    if value is _MISSING:
        raise _invalid_selector(
            f"node has no attribute {predicate.attr!r} to evaluate a "
            "predicate against",
            predicate=predicate,
        )
    if value is None:
        return False
    if not isinstance(value, _SCALAR_TYPES):
        raise _invalid_selector(
            f"attribute {predicate.attr!r} holds a {type(value).__name__} "
            "value that tree-query string predicates cannot compare",
            predicate=predicate,
        )

    left = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    return _compare(left, predicate.op, predicate.value)


def evaluate_predicates(predicates: Sequence[Predicate], node: Any) -> bool:
    """Evaluate every predicate in ``predicates`` against ``node`` (logical AND).

    Mirrors the legacy executor's step-matching loop exactly: predicates
    are checked in order and evaluation stops at the first one that does
    not hold, so a later, possibly-unsupported predicate is never reached
    once an earlier one has already failed. An empty ``predicates``
    sequence holds vacuously (``True``), matching a selector step with no
    predicates at all.
    """

    for predicate in predicates:
        if not evaluate_predicate(predicate, node):
            return False
    return True
