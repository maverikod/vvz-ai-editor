"""Mutable working mirror of the common tree model, for the mutating core operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the integration layer between the *immutable* common model of
``tree_engine.core.nodes`` and the *mutating* operations of
``tree_engine.core.operations``/``move``/``updates``/``subtree_apply``. Those
operations are deliberately duck-typed ({p010}, {p107}, {p108}): they resolve a
node's ``parent`` back-link, splice its ``children`` in place, and write
``node_id``/``short_id`` on it. ``core.nodes.Node`` is a frozen dataclass with
no ``parent`` field at all, so it cannot be that node. Until this module, no
merged file closed that gap and every caller had to invent its own mirror.

:class:`LiveNode` is that node: the exact ``Node`` schema -- ``kind``,
``fields``, ``children``, plus the five reserved slots ``node_id``,
``short_id``, ``extended_type``, ``buffer_range``, ``references`` -- with a
settable ``parent`` and a list ``children``. :func:`to_live` and
:func:`to_frozen` are its lossless conversion pair with ``Node``, so a document
is parsed by a format plugin into ``Node``, mirrored here for editing, and
converted back for every render.

Two rendering realities every editor of this model has to honor, both owned
here rather than by each caller:

* **fields vs children** ({p045}, {p008}). ``nodes.py`` states plainly that
  ``children`` and ``fields`` are not required to be kept in lockstep, and the
  shipped plugins split on exactly that: the Python and BSL generators rebuild
  from node-valued ``fields`` entries, while the JSON and TOML generators walk
  ``children``. A core splice touches ``children`` only, so
  :func:`sync_fields` mirrors the new ``children`` back into the parent's
  node-holding sequence field. Where that mapping is ambiguous the edit is
  refused with a catalog code rather than silently not rendered.
* **cached source slices**. A plugin may cache a node's original source text on
  the node itself so an untouched document round-trips byte-identically -- JSON
  stores the whole document under ``fields["raw"]``, BSL under
  ``fields["content"]`` -- and replays that cache instead of re-composing from
  children. After a splice, every ancestor of the edit holds a stale cache that
  would replay pre-edit text. :data:`CACHED_SOURCE_FIELDS` names the convention
  and :func:`invalidate_cached_source` drops it along the ancestor chain, so
  the rule is one documented core-side invariant instead of plugin knowledge
  spread through callers.

This module performs no validation, no addressing, no locking and no I/O: it
owns the working representation and nothing else. It raises only
``nodes.NodeSchemaError`` carrying an ``ErrorCode`` from the shared catalog,
the same convention ``core/nodes.py`` established, so a public facade can map
it to the typed hierarchy without inventing a code of its own.

Source-of-truth requirement labels honored here: {p008}, {p010}, {p045},
{p107}, {p108}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID, uuid4

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Node, NodeKind, NodeSchemaError
from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode

__all__ = [
    "CACHED_SOURCE_FIELDS",
    "LiveNode",
    "TreeDocument",
    "to_live",
    "to_frozen",
    "walk",
    "relink",
    "sync_fields",
    "invalidate_cached_source",
]

#: Field names under which a format plugin may cache a node's own original
#: source slice: JSON's ``raw`` (the document root's covers the entire text)
#: and BSL's ``content``. A plugin that finds one replays it verbatim instead
#: of re-composing the node from its children, which is exactly what keeps an
#: untouched document byte-identical -- and exactly what makes the cache stale
#: on every ancestor of an edit. See :func:`invalidate_cached_source`.
CACHED_SOURCE_FIELDS: Tuple[str, ...] = ("raw", "content")


@dataclass(eq=False)
class LiveNode:
    """A mutable node carrying the exact ``core.nodes.Node`` schema.

    ``kind``, ``fields`` and ``children`` mirror ``Node``'s three structural
    attributes, and ``node_id``/``short_id``/``extended_type``/``buffer_range``/
    ``references`` mirror its five reserved identity and extension slots.
    ``parent`` is the settable back-link ``Node`` deliberately does not carry
    (immutable bottom-up construction keeps no back-references) and which every
    mutating core operation resolves; ``children`` is a ``list`` so those
    operations can splice it in place.

    ``eq=False`` keeps identity comparison: ``parent`` makes the graph cyclic,
    so a generated structural ``__eq__`` would recurse forever, and the core's
    splice helpers compare nodes by identity anyway (``siblings.index(node)``).
    """

    kind: str
    fields: Dict[str, Any]
    children: List["LiveNode"]
    node_id: UUID
    short_id: Optional[int] = None
    extended_type: Optional[str] = None
    buffer_range: Optional[Tuple[int, int]] = None
    references: Tuple[Any, ...] = ()
    parent: Optional["LiveNode"] = field(default=None, repr=False)

    def get_attribute(self, name: str, default: Any = None) -> Any:
        """Read field ``name``, the accessor ``core.updates`` and the query
        predicate evaluator both look for on a node."""

        return self.fields.get(name, default)

    def set_attribute(self, name: str, value: Any) -> None:
        """Set field ``name`` to a primitive value, validating before writing.

        Rejects anything the ``Node`` field contract does not admit as a plain
        value with ``NodeSchemaError`` (``INVALID_PARENT_TYPE``), the same error
        ``core/nodes.py`` raises for a field-shape mismatch and the one
        ``core.updates.set_attribute`` already catches and re-raises as its own
        typed rejection, having written nothing.
        """

        if not (value is None or isinstance(value, (str, int, float, bool, bytes))):
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"attribute {name!r} must be a primitive value, got {type(value).__name__}",
            )
        self.fields = {**self.fields, name: value}


def _remap(fields: Mapping[str, Any], old: Sequence[Any], new: Sequence[Any]) -> Dict[str, Any]:
    """Rebuild ``fields`` with every node value swapped for its counterpart.

    A field value that *is* one of ``old`` (by object identity) becomes the
    matching entry of ``new`` -- the same fields/children reconciliation
    ``core.subtree_copy`` already performs when it clones a node. A live node
    that is no longer among ``old`` is one a splice detached from ``children``
    while a field still holds it (an ``IndentedBlock``'s ``header``, say); it is
    converted on the spot instead of being left behind as a live node inside an
    otherwise immutable tree.
    """

    swap = {id(item): replacement for item, replacement in zip(old, new)}

    def one(value: Any) -> Any:
        if isinstance(value, tuple):
            return tuple(one(item) for item in value)
        if id(value) in swap:
            return swap[id(value)]
        return to_frozen(value) if isinstance(value, LiveNode) else value

    return {key: one(value) for key, value in fields.items()}


def to_live(node: Node, parent: Optional[LiveNode] = None) -> LiveNode:
    """Mirror an immutable ``Node`` subtree into linked :class:`LiveNode` objects.

    Every attribute is carried across unchanged; a node that arrives without a
    ``node_id`` (a plugin fragment that assigns identity later) is given a fresh
    UUID4 here so the mirror is always addressable.
    """

    live = LiveNode(
        kind=str(node.kind),
        fields=dict(node.fields),
        children=[],
        parent=parent,
        node_id=node.node_id if node.node_id is not None else generate_node_id(),
        short_id=node.short_id,
        extended_type=node.extended_type,
        buffer_range=node.buffer_range,
        references=tuple(node.references or ()),
    )
    live.children = [to_live(child, live) for child in node.children]
    live.fields = _remap(node.fields, node.children, live.children)
    return live


def to_frozen(live: LiveNode) -> Node:
    """Rebuild the immutable ``Node`` subtree a format plugin renders from.

    The exact inverse of :func:`to_live`: identity, extension slots, byte range
    and references are preserved, and node-valued ``fields`` entries are
    re-pointed at the rebuilt children so ``fields`` and ``children`` describe
    the same tree on both sides of the conversion.
    """

    children = [to_frozen(child) for child in live.children]
    return Node(
        kind=NodeKind(live.kind),
        fields=_remap(live.fields, live.children, children),
        children=tuple(children),
        node_id=live.node_id,
        short_id=live.short_id,
        extended_type=live.extended_type,
        buffer_range=live.buffer_range,
        references=live.references,
    )


def walk(node: LiveNode) -> Iterator[LiveNode]:
    """Depth-first, pre-order traversal of a live subtree, ``node`` first."""

    yield node
    for child in node.children:
        yield from walk(child)


def relink(node: LiveNode, parent: Optional[LiveNode] = None) -> None:
    """Restore the ``parent`` back-links over a subtree rebuilt elsewhere.

    ``core.subtree_copy``/``core.subtree_apply`` rebuild nodes through
    ``dataclasses.replace`` and splice them by ``children``/``parent_id``, never
    touching the ``parent`` object link; running this over the affected root
    afterwards puts the back-links back in agreement with ``children``.
    """

    node.parent = parent
    for child in node.children:
        relink(child, node)


def sync_fields(parent: Optional[LiveNode]) -> None:
    """Mirror ``parent.children`` back into its node-holding ``fields``.

    The Python and BSL generators rebuild a node from its node-valued ``fields``
    entries; the JSON and TOML generators walk ``children``. A core splice
    rewrites ``children`` only, so a fields-driven parent would otherwise render
    its pre-edit content. When exactly one field holds a non-empty sequence of
    nodes, that field is unambiguously the parent's child sequence and is
    rewritten from ``children`` in order.

    When several fields hold node sequences, or the parent's node children sit
    only in single-valued fields, no single field can express the new child
    order; the edit is refused with ``NodeSchemaError``
    (``INVALID_PARENT_TYPE``) rather than accepted and silently not rendered.
    Splice into the descendant that does hold one sequence instead -- for
    Python that is the ``Module`` or the ``IndentedBlock``, not the ``ClassDef``
    whose body is a single node. A parent with no node-valued field at all is a
    children-driven format and needs nothing done.

    ``parent`` may be ``None`` (an operation whose affected parent was the
    document root's own absent parent), in which case this is a no-op.
    """

    if parent is None:
        return
    sequences = [
        name
        for name, value in parent.fields.items()
        if isinstance(value, tuple) and value and all(isinstance(item, LiveNode) for item in value)
    ]
    if len(sequences) == 1:
        parent.fields = {**parent.fields, sequences[0]: tuple(parent.children)}
        return
    if sequences or any(isinstance(value, LiveNode) for value in parent.fields.values()):
        raise NodeSchemaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"node kind {parent.kind!r} does not hold its children in exactly one sequence "
            "field, so a sequence edit cannot be expressed on it; splice into the "
            "sequence-holding descendant instead",
        )


def invalidate_cached_source(node: Optional[LiveNode]) -> None:
    """Drop the stale cached source slice on ``node`` and each of its ancestors.

    A plugin that cached its own original text under one of
    :data:`CACHED_SOURCE_FIELDS` replays that cache verbatim rather than
    re-composing from children, which is what makes an untouched document
    byte-identical. After a splice the cache is correct on every node outside
    the edit and stale on every node containing it, so exactly the ancestor
    chain from the edited parent to the root is cleared -- never a sibling,
    never a descendant, and never on an untouched document.
    """

    current = node
    while current is not None:
        if any(name in current.fields for name in CACHED_SOURCE_FIELDS):
            current.fields = {
                key: value
                for key, value in current.fields.items()
                if key not in CACHED_SOURCE_FIELDS
            }
        current = current.parent


class TreeDocument:
    """One loaded document: its tree, identity, indexes, and version.

    ``document_id`` is a fresh UUID4 per load and ``document_version`` the monotonic counter every
    mutating command checks and bumps ({p024}). ``source_format_id`` is the originally selected format
    and ``format_id`` the current working one; they differ only under the authorized plain-text
    fallback, which also fills ``fallback_diagnostic`` ({p050}, {7a9b}). ``nodes_by_id``,
    ``short_id_index``, ``short_id_map`` and ``parent_index`` are the document-local addressing state
    ({p097}); ``path`` is the file it was loaded from, or ``None`` for a :func:`loads` document.

    ``short_id_map`` is the one piece of state a caller may SEED. A document rebuilt from a stored
    tree file already knows which integer every node_id was issued, and letting :meth:`reindex` mint
    a fresh map instead would silently reissue new short_ids for nodes whose identity survived --
    which is exactly the identity loss the persisted map exists to prevent. Passing the stored map
    here makes :meth:`reindex` keep every recorded value and carry the monotonic ``next_short_id``
    across the reload, so a short_id released by an earlier delete is still never reused ({p097})."""

    def __init__(self, root: LiveNode, source_format_id: str, format_id: str, source_bytes: bytes, *,
                 path: Optional[Path] = None,
                 fallback_diagnostic: Optional[Mapping[str, Any]] = None,
                 short_id_map: Optional[ShortIdMap] = None) -> None:
        self.document_id, self.document_version = uuid4(), 1
        self.root, self.source_bytes, self.path = root, source_bytes, path
        self.source_format_id, self.format_id = source_format_id, format_id
        self.fallback_diagnostic = dict(fallback_diagnostic) if fallback_diagnostic else None
        self.short_id_map = ShortIdMap() if short_id_map is None else short_id_map
        self.nodes_by_id: Dict[UUID, LiveNode] = {}
        self.short_id_index: Dict[int, UUID] = {}
        self.parent_index: Dict[UUID, Optional[UUID]] = {}
        self.reindex()

    def reindex(self) -> None:
        """Rebuild the node, short_id and parent indexes from the live tree: a node keeps the short_id
        it already holds, one without gets the next monotonic value, and a short_id whose node is gone
        is released and never reused ({p097})."""
        live: Dict[UUID, LiveNode] = {node.node_id: node for node in walk(self.root)}
        for node_id in self.short_id_index.values():
            if node_id not in live:
                self.short_id_map.release(node_id)
        self.nodes_by_id, self.short_id_index = live, {}
        self.parent_index = {i: (n.parent.node_id if n.parent is not None else None)
                             for i, n in live.items()}
        for node_id, node in live.items():
            existing = self.short_id_map.get_short_id(node_id)
            node.short_id = existing if existing is not None else self.short_id_map.allocate(node_id)
            self.short_id_index[node.short_id] = node_id

    def resolve_short_id(self, short_id: int) -> Sequence[UUID]:
        """The ``normalize_node_address`` accessor: short_id -> node_id, empty when unknown."""
        node_id = self.short_id_map.get_node_id(short_id)
        return () if node_id is None else (node_id,)

    def source_for(self, node: LiveNode) -> Optional[str]:
        """The node's own text from the loaded source, for ``drill_down``'s source previews."""
        span = node.buffer_range
        return None if span is None else self.source_bytes[span[0]:span[1]].decode("utf-8", "replace")
