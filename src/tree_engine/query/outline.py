"""Compact ``model_outline`` response schema for concept C-018 (TreeInspection).

Scope (concept C-018, narrowed to the ``drill_down`` response shape and its
assembly into a serializable form, per HRS fragments {p070} and {p071}): this
module defines the ``model_outline`` response records -- the single meta
header, the flat preorder node record, the collapsed-subtree stub record, the
per-field and whole-response truncation contracts -- plus one assembly
helper, :func:`build_outline_response`, that stitches an already-built header
and an already-built ordered record list into the complete response object.

Non-goals, left entirely to the sibling ``drill_down`` inspection module:
tree traversal, address resolution (``normalize_node_address``), depth
control, auto-expansion decisions driven by ``expand_below_bytes``, and the
truncation *decisions* (what to cut and where). This file only shapes and
assembles values its caller already computed; it never walks a
:class:`tree_engine.core.nodes.Node` graph, never touches
``tree_engine.core.short_id.ShortIdMap``, and never reads
``tree_engine.core.positions.SubtreeBytesAggregate`` itself -- the caller
consumes that cache and simply passes the resulting integer (or ``None`` for
the missing/stale sentinel, per {p067}) into ``subtree_bytes`` below.

Per {p021}/{p070}/{p071}, every shown or collapsed node must carry both its
canonical UUID4 ``node_id`` and its compact ``short_id_hex`` together, the
latter never a substitute for the former. Rather than hand-roll that pair a
second time, every place this module needs it -- the viewed node in the
header, a node record's own address, a node record's parent reference, a
stub record's address, and the whole-response continuation address -- reuses
the existing {p021} pair type, ``tree_engine.core.address.NodeAddressView``,
the same pattern already followed by the sibling
``tree_engine.query.results.QueryMatch.parent_path``. Callers are expected to
have produced each pair via ``tree_engine.core.address
.build_node_address_view``.

This file defines data only. It performs no I/O, no tree walking, no address
resolution, and no truncation decision of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from tree_engine.core.address import NodeAddressView

__all__ = [
    "OutlineMeta",
    "TruncatedField",
    "OutlineNodeRecord",
    "OutlineStubRecord",
    "OutlineTruncation",
    "OutlineResponse",
    "build_outline_response",
]


# --------------------------------------------------------------------------
# Response header
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineMeta:
    """The single response header ``model_outline`` carries, per {p070}.

    ``viewed`` is the {p021} node_id/short_id_hex pair of the node the
    ``drill_down`` call was resolved to (see
    ``tree_engine.core.address.build_node_address_view``). ``depth`` and
    ``expand_below_bytes`` are the effective parameter values the caller
    already applied ({p066}, {p067}) -- this module does not validate or
    default them. ``document_version`` is the document version the response
    was produced against, carried exactly as given so a caller can compare
    it against a later ``expected_version`` ({p065}). ``node_count`` is the
    number of entries (node records plus stub records) in the assembled
    ``nodes`` list, and ``response_bytes`` is the serialized byte size of
    the whole response -- both computed by the caller, not by this module.
    """

    viewed: NodeAddressView
    depth: int
    expand_below_bytes: int
    document_version: Any
    node_count: int
    response_bytes: int


# --------------------------------------------------------------------------
# Per-field truncation contract
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TruncatedField:
    """The per-field truncation contract for one oversized optional value.

    Used when a single record's optional content -- a source preview or a
    large attribute value -- would alone exceed the response budget
    ({p069}). ``value`` is the (possibly already-shortened) content that is
    still returned; ``field_truncated`` marks whether it was cut, and
    ``original_field_bytes`` records the pre-truncation byte size only when
    ``field_truncated`` is true. This contract applies to exactly the one
    field it wraps -- a record's mandatory address and structural fields
    (``node_id``, ``short_id_hex``, ``type``, ``child_count``, ...) are
    never wrapped in this type and are always returned intact, per {p069}.
    """

    value: Any
    field_truncated: bool = False
    original_field_bytes: Optional[int] = None


# --------------------------------------------------------------------------
# Flat preorder node record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineNodeRecord:
    """One entry of the flat, preorder ``nodes`` list, per {p070}.

    ``address`` is this node's own {p021} node_id/short_id_hex pair.
    ``depth`` is its distance (in edges) from the viewed node. ``parent`` is
    the immediate parent's {p021} pair, or ``None`` -- absent only for the
    viewed node itself when it has no shown parent in this response.
    ``child_index`` is this node's position among its siblings, as the
    caller determined it.

    ``type`` and ``name_or_value`` are the node's short-form identity for
    display. ``attributes`` is the selected-attributes payload, gated by
    whether ``include_attributes`` was requested ({p068}): ``None`` means
    attributes were not requested for this response; an (possibly empty)
    mapping means they were. Any individual attribute value may itself be a
    :class:`TruncatedField` when that one value alone was too large.

    ``child_count`` is the node's total direct-child count; ``shown_child_count``
    is how many of those children actually appear (as records or stubs)
    in this response. ``subtree_bytes`` is the locally maintained aggregate
    figure for this node (see ``tree_engine.core.positions
    .SubtreeBytesAggregate``), or ``None`` when that cache is missing or
    stale for this node ({p067}) -- this module never re-derives it.

    ``source_preview`` is gated by whether ``include_source`` was requested
    ({p068}): ``None`` means source was not requested; otherwise it is a
    :class:`TruncatedField` wrapping the preview string (``field_truncated``
    false when the preview fit whole).

    ``expanded`` is true when this node's children were shown rather than
    collapsed into a stub. ``auto_expanded`` is true when that expansion was
    triggered by the ``expand_below_bytes`` threshold rather than the
    requested ``depth`` ({p067}). ``truncated`` is true when this specific
    record's own content was cut for the whole-response budget ({p069}).
    """

    node_id: Any
    short_id_hex: str
    depth: int
    parent_id: Optional[Any]
    parent_short_id_hex: Optional[str]
    child_index: int
    type: str
    name_or_value: str
    attributes: Optional[Mapping[str, Any]]
    child_count: int
    shown_child_count: int
    subtree_bytes: Optional[int]
    source_preview: Optional[TruncatedField]
    expanded: bool
    auto_expanded: bool
    truncated: bool

    @property
    def address(self) -> NodeAddressView:
        """This record's own {p021} node_id/short_id_hex pair."""

        return NodeAddressView(short_id_hex=self.short_id_hex, node_id=str(self.node_id))

    @property
    def parent(self) -> Optional[NodeAddressView]:
        """The immediate parent's {p021} pair, or ``None`` if unshown."""

        if self.parent_id is None and self.parent_short_id_hex is None:
            return None
        return NodeAddressView(
            short_id_hex=str(self.parent_short_id_hex), node_id=str(self.parent_id)
        )


# --------------------------------------------------------------------------
# Collapsed-subtree stub record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineStubRecord:
    """A stand-in record for a subtree ``drill_down`` did not expand, per {p071}.

    Carries only enough to address and describe the collapsed subtree:
    ``node_id``/``short_id_hex`` (the {p021} pair, always both present),
    ``type``, ``child_count``, ``subtree_node_count`` (the collapsed
    subtree's total node count), and ``subtree_bytes`` (the locally
    maintained aggregate, or ``None`` when missing/stale, mirroring
    :attr:`OutlineNodeRecord.subtree_bytes`). ``expandable`` is a literal
    flag, always ``True`` -- it is not a constructor parameter, so a stub
    can never be built claiming otherwise. This is sufficient, on its own,
    for a follow-up command to address the node by ``short_id_hex`` without
    a further search, per {p071}.
    """

    node_id: Any
    short_id_hex: str
    type: str
    child_count: int
    subtree_node_count: int
    subtree_bytes: Optional[int]
    expandable: bool = field(default=True, init=False)

    @property
    def address(self) -> NodeAddressView:
        """This stub's own {p021} node_id/short_id_hex pair."""

        return NodeAddressView(short_id_hex=self.short_id_hex, node_id=str(self.node_id))


# --------------------------------------------------------------------------
# Whole-response truncation and continuation contract
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineTruncation:
    """The whole-response truncation and continuation contract, per {p069}.

    ``truncated`` is true when the serialized response was cut short (only
    ever between node-record boundaries, never mid-record). ``omitted_nodes``
    and ``omitted_bytes`` count what was left out. ``continuation`` is the
    {p021} pair (``short_id_hex`` plus ``node_id``) identifying where a
    follow-up call should resume -- ``None`` when there is nothing to
    resume (the ordinary, untruncated case).
    """

    truncated: bool
    omitted_nodes: int
    omitted_bytes: int
    continuation: Optional[NodeAddressView] = None


# --------------------------------------------------------------------------
# Assembled response and its assembly helper
# --------------------------------------------------------------------------


OutlineEntry = Union[OutlineNodeRecord, OutlineStubRecord]


@dataclass(frozen=True)
class OutlineResponse:
    """The complete, serializable ``model_outline`` response ({p070}).

    ``meta`` is the response header, ``nodes`` is the flat preorder list
    (mixing :class:`OutlineNodeRecord` and :class:`OutlineStubRecord`
    entries, in the exact order given), and ``truncation`` is the
    whole-response truncation/continuation contract. This type never
    reorders, filters, or otherwise recomputes what it was given.
    """

    meta: OutlineMeta
    nodes: Tuple[OutlineEntry, ...]
    truncation: OutlineTruncation


def build_outline_response(
    meta: OutlineMeta,
    nodes: Sequence[OutlineEntry],
    truncation: OutlineTruncation,
) -> OutlineResponse:
    """Assemble an already-built header, node list, and truncation contract.

    This is the module's one assembly helper: it performs no computation of
    its own beyond wrapping ``nodes`` in an immutable, ordered tuple and
    threading ``meta``/``truncation`` through unchanged. It does not compute
    ``node_count``/``response_bytes`` (those belong on ``meta``, already
    resolved by the caller), does not decide expansion or truncation, and
    does not resolve addresses -- all of that is the sibling ``drill_down``
    module's responsibility. The returned :class:`OutlineResponse` exposes
    every value from ``meta``, ``nodes``, and ``truncation`` unchanged and in
    the given order.
    """

    return OutlineResponse(meta=meta, nodes=tuple(nodes), truncation=truncation)
