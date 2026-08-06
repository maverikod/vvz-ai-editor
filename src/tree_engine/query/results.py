"""Query-result record model for the ported tree-query engine (concept C-009).

Scope (concept C-009, narrowed to the compact-result shape only, per {p005}
and {p021}): this module owns exactly one thing -- the immutable
``QueryMatch`` record every match returned by the ported ``cst_query``
engine must carry, plus the single small helper, :func:`build_query_match`,
that assembles one from values already known by its caller.

Per {p021}, every node view in this package -- a query result included --
must carry both the compact hex-form ``short_id`` and the canonical UUID4
``node_id`` together, since the compact form is only a later-addressing
shortcut and never a substitute for the canonical id. This module reuses
the existing {p021} pair type, :class:`tree_engine.core.address
.NodeAddressView` (``short_id_hex`` + ``node_id``), for each
``parent_path`` entry instead of hand-rolling a second pair type or
formatting hex itself -- see ``tree_engine.core.address
.build_node_address_view``, which is how a caller is expected to have
produced that pair in the first place.

This file defines data only. It does not parse selectors, walk trees,
resolve semantic roles, evaluate predicates, or orchestrate a query --
all of that is out of scope here and belongs entirely to sibling files
under this same tactical step (G-018/T-001). This module has no dependency
on any of those siblings, and none of them may depend on anything from
this module beyond the ``QueryMatch`` shape and the ``build_query_match``
constructor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from tree_engine.core.address import NodeAddressView

__all__ = [
    "Position",
    "Range",
    "QueryMatch",
    "build_query_match",
]


@dataclass(frozen=True)
class Position:
    """A single source location: a 1- or 0-based line/column pair.

    This module does not fix the numbering convention -- that is a
    format-plugin concern -- it only guarantees ``line`` and ``column`` are
    carried together as given.
    """

    line: int
    column: int


@dataclass(frozen=True)
class Range:
    """A node's source span, as a simple ``start``/``end`` position pair."""

    start: Position
    end: Position


@dataclass(frozen=True)
class QueryMatch:
    """One immutable query result, per the {p021} compact-result contract.

    Fields:

    * ``node_id`` -- the matched node's canonical UUID4 node_id.
    * ``short_id_hex`` -- the matched node's compact hex-form short_id
      (from the sibling ``tree_engine.core.short_id`` module). Exists only
      for later re-addressing without a further search; never a substitute
      for ``node_id``.
    * ``type`` -- the concrete node kind as produced by the loaded format,
      e.g. the underlying construct name or a format extension type such
      as ``preprocessor_directive`` or ``variable_declaration``.
    * ``kind`` -- the standard semantic role (``function``, ``method``,
      ``class``, ``module``) the traversal adapter mapped the node to, or
      ``""`` when no role applies.
    * ``name`` -- the node's short display name, or ``""`` when it has
      none.
    * ``range`` -- the node's start/end position as a :class:`Range`.
    * ``parent_path`` -- an ordered tuple of ancestor
      :class:`~tree_engine.core.address.NodeAddressView` entries, from the
      document root down to but excluding the matched node itself. Each
      entry carries both the ancestor's ``node_id`` and its
      ``short_id_hex``, so any ancestor can be addressed later without a
      further search.
    * ``source`` -- the node's source text, present only when the caller
      asked for source to be included; ``None`` (absent) otherwise.

    Every field is stored exactly as given -- this type performs no
    coercion, normalization, or validation of any kind. It is a shape, not
    a validator; overwriting a field after construction is rejected by the
    ``frozen`` dataclass machinery rather than silently succeeding.
    """

    node_id: Any
    short_id_hex: str
    type: str
    kind: str
    name: str
    range: Range
    parent_path: Tuple[NodeAddressView, ...]
    source: Optional[str] = None


def build_query_match(
    node: Any,
    kind: str,
    short_id_hex: str,
    parent_path: Sequence[NodeAddressView],
    source: Optional[str] = None,
) -> QueryMatch:
    """Assemble a :class:`QueryMatch` from values already known to the caller.

    Performs no tree walking, parsing, predicate evaluation, or lookup of
    any kind -- it only reads already-attached data off ``node`` and
    threads the remaining, already-resolved arguments straight into the
    record. Every value this function needs must already be known by the
    caller (the traversal adapter) before calling it.

    ``node`` is duck-typed, the same convention already used by
    ``tree_engine.core.address`` for its ``document`` parameter: this
    helper reads ``node.node_id``, ``node.name`` and ``node.range``
    directly, and ``node.type`` -- falling back to ``node.kind`` when
    ``type`` is absent, for direct compatibility with
    ``tree_engine.core.nodes.Node``, whose own attribute for "the node's
    format-defined type" is named ``kind``. It never falls back to a
    lookup, a default document, or any sibling module.

    ``kind`` is the already-resolved standard semantic role (or ``""``
    when inapplicable), ``short_id_hex`` is the already-rendered compact
    hex short_id (see ``tree_engine.core.short_id.to_hex`` and
    ``tree_engine.core.address.build_node_address_view``, both
    sibling-owned renderers this function never calls itself), and
    ``parent_path`` is the already-built ordered ancestor sequence. All
    three are threaded through unchanged.
    """

    node_type = getattr(node, "type", None)
    if node_type is None:
        node_type = getattr(node, "kind", "")

    name = getattr(node, "name", None)
    if name is None:
        name = ""

    return QueryMatch(
        node_id=node.node_id,
        short_id_hex=short_id_hex,
        type=node_type,
        kind=kind,
        name=name,
        range=getattr(node, "range", None),
        parent_path=tuple(parent_path),
        source=source,
    )
