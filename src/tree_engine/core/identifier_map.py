"""The three-way identifier map: short_id <-> node_id <-> native reference.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: one uniform correspondence per node across EVERY format -- the compact
integer ``short_id``, the canonical UUID4 ``node_id``, and, for a format whose
plugin declares a reference notation of its own, that native reference (a JSON
Pointer for the data formats). All three name the same node, so a caller may
hand the engine whichever one it happens to be holding.

Two of the three already existed: ``core.short_id.ShortIdMap`` is the
persisted int<->UUID4 bidirectional map, and ``core.address
.normalize_node_address`` is the single entry point that canonicalizes an int,
a ``0x`` hex short_id, a decimal string, a UUID4, or a ``"document:node"``
string to a UUID4. This module adds the third correspondence and nothing else:
it never allocates a short_id, never mutates the document, and never
re-implements address normalization -- it delegates to it.

Where the native reference comes from is the design constraint that shaped
this file. A format is a pluggable module, so the notation is a PLUGIN
DECLARATION, read here duck-typed off the resolved plugin exactly as
``facade._fragment`` already reads ``fragment_container_kinds``::

    plugin.native_reference.notation      -> the notation's name
    plugin.native_reference.index(root)   -> both directions of the index

A plugin that declares nothing simply has no third slot, and the ``ref`` of
every one of its nodes is ``None``. Nothing here tests the format id, and
nothing here knows what a JSON Pointer looks like: resolving a reference is a
dictionary lookup in the index the PLUGIN built, so a format that some day
speaks XPath needs no change on this side.

Position independence is inherited, not re-established. The integer is issued
by ``ShortIdMap`` against a node's UUID4 and ``TreeDocument.reindex`` keeps
whatever a node already holds, so inserting a line above a node moves its line
number and leaves its short_id alone. The native reference is the one
identifier of the three that is a PATH and therefore genuinely positional: a
JSON Pointer of ``/items/1`` names whatever now sits at index 1. That is what
the notation means, and this module reports it as the format defines it rather
than pretending a path is stable.

The ``style`` flag selects which identifier the engine REPORTS. It never
narrows what the engine ACCEPTS: :meth:`IdentifierMap.resolve` takes all three
forms under either style, because the map is precisely what makes them
equivalent. It is a constructor argument on an ordinary object -- there is no
module-level switch, and no caller can change another caller's reporting.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Optional, Tuple, Union
from uuid import UUID

from tree_engine.core.address import NodeAddressError, UnknownAddressError, normalize_node_address

__all__ = [
    "IdentifierStyle",
    "NodeIdentifiers",
    "native_reference_of",
    "IdentifierMap",
]


class IdentifierStyle(str, enum.Enum):
    """Which of the two document-wide identifiers the engine reports.

    ``SHORT_ID`` is the default because brevity is the reason the integer
    exists at all; ``NODE_ID`` reports the canonical UUID4 for a caller that
    would rather work in it directly. Being a ``str`` enum, either member can
    be passed as its own plain string over a protocol boundary.
    """

    SHORT_ID = "short_id"
    NODE_ID = "node_id"


@dataclass(frozen=True)
class NodeIdentifiers:
    """Every identifier one node answers to, and the one currently reported.

    ``short_id`` and ``node_id`` are always present -- every indexed node has
    both. ``ref`` is the format's own reference for this node, or ``None``
    when the format declares no notation (plain text, Python, BSL) or when
    this particular node has none the notation can express (a YAML comment, a
    TOML blank line, a JSON object member as distinct from its value).
    ``notation`` names the language ``ref`` is written in, and is ``None``
    exactly when the format declares none.

    ``reported`` is what ``style`` selects. It is the ONLY thing ``style``
    changes: the other fields are identical under both settings.
    """

    node_id: UUID
    short_id: int
    ref: Optional[str] = None
    notation: Optional[str] = None
    style: IdentifierStyle = IdentifierStyle.SHORT_ID

    @property
    def reported(self) -> Union[int, str]:
        """The identifier to show: the integer, or the UUID4 as a string."""

        return self.short_id if self.style is IdentifierStyle.SHORT_ID else str(self.node_id)

    def with_style(self, style: IdentifierStyle) -> "NodeIdentifiers":
        """The same three identifiers, reported under ``style`` instead."""

        return NodeIdentifiers(node_id=self.node_id, short_id=self.short_id, ref=self.ref,
                               notation=self.notation, style=IdentifierStyle(style))


def native_reference_of(plugin: Any) -> Optional[Any]:
    """The reference notation ``plugin`` declares, or ``None``.

    Duck-typed on purpose, following ``fragment_container_kinds``: a plugin
    opts in by publishing a ``native_reference`` object exposing ``notation``
    and ``index(root)``. An object that does not expose both is not a
    declaration and is ignored rather than half-used, so a partially written
    plugin degrades to "this format has no reference notation" instead of
    failing every address resolution in the document.
    """

    declared = getattr(plugin, "native_reference", None)
    if declared is None:
        return None
    if not isinstance(getattr(declared, "notation", None), str):
        return None
    return declared if callable(getattr(declared, "index", None)) else None


class IdentifierMap:
    """A document's three-way correspondence, under one reporting style.

    Built over a live document rather than a copy of it, so the integers and
    UUID4s it reports are the document's own. The native-reference index is
    the one part that has to be derived, and it is derived LAZILY and cached
    against ``document_version``: a caller that never asks for a reference
    never pays for the walk, and an edit that bumps the version invalidates
    the cache instead of serving a stale path.
    """

    __slots__ = ("_document", "_plugin", "_style", "_notation", "_index", "_indexed_version")

    def __init__(self, document: Any, plugin: Any = None, *,
                 style: Union[IdentifierStyle, str] = IdentifierStyle.SHORT_ID) -> None:
        self._document = document
        self._plugin = plugin
        self._style = IdentifierStyle(style)
        self._notation = native_reference_of(plugin)
        self._index: Any = None
        self._indexed_version: Any = None

    @property
    def style(self) -> IdentifierStyle:
        """The style this map reports under; fixed for this object's lifetime."""

        return self._style

    @property
    def notation(self) -> Optional[str]:
        """The name of this format's reference notation, or ``None``."""

        return None if self._notation is None else self._notation.notation

    def with_style(self, style: Union[IdentifierStyle, str]) -> "IdentifierMap":
        """A second view of the same document reporting under ``style``.

        A new object rather than a mutation: two callers may hold two styles
        over one document at the same time without either changing the other.
        """

        return IdentifierMap(self._document, self._plugin, style=style)

    # -- the native-reference index -----------------------------------------

    def _pointer_index(self) -> Any:
        """The plugin-built reference index, rebuilt when the document moved."""

        if self._notation is None:
            return None
        version = getattr(self._document, "document_version", None)
        if self._index is None or self._indexed_version != version:
            self._index = self._notation.index(getattr(self._document, "root", None))
            self._indexed_version = version
        return self._index

    def ref_for(self, node_id: UUID) -> Optional[str]:
        """This node's native reference, or ``None`` when it has none."""

        index = self._pointer_index()
        return None if index is None else index.ref_for(node_id)

    def node_for_ref(self, ref: Any) -> Optional[UUID]:
        """The node ``ref`` names, or ``None`` -- unknown ref, or no notation.

        A pure lookup in the index the plugin built. This module never parses
        the reference itself, which is what keeps the notation entirely inside
        the plugin that speaks it.
        """

        index = self._pointer_index()
        if index is None or not isinstance(ref, str):
            return None
        return index.node_for(ref)

    # -- resolution and reporting -------------------------------------------

    def resolve(self, address: Any) -> UUID:
        """Canonicalize any of the three forms to the node's UUID4.

        The int/hex/decimal/UUID4/``"document:node"`` forms go through
        ``normalize_node_address`` ({j9rh}) untouched, so this adds no second
        address parser. Only when that rejects a STRING is the native-reference
        index consulted, which keeps every existing address form on exactly the
        path it already took and never builds the index for a caller that is
        not using references. An address no form resolves raises the original
        ``NodeAddressError``, not a substituted one.
        """

        try:
            return normalize_node_address(
                self._document, address,
                current_document_id=getattr(self._document, "document_id", None),
                resolve_short_id=getattr(self._document, "resolve_short_id", None))
        except NodeAddressError:
            resolved = self.node_for_ref(address)
            if resolved is None:
                raise
            return resolved

    def identifiers(self, address: Any) -> NodeIdentifiers:
        """Every identifier of the addressed node, reported under this style."""

        node_id = self.resolve(address)
        node = getattr(self._document, "nodes_by_id", {}).get(node_id)
        short_id = getattr(node, "short_id", None)
        if not isinstance(short_id, int) or isinstance(short_id, bool):
            # reindex() gives every live node a short_id, so this is a document
            # whose indexes were never built -- report it rather than invent one.
            raise UnknownAddressError(address, f"node {node_id} carries no short_id")
        return NodeIdentifiers(node_id=node_id, short_id=short_id, ref=self.ref_for(node_id),
                               notation=self.notation, style=self._style)

    def report(self, address: Any) -> Union[int, str]:
        """The single identifier this style reports for the addressed node."""

        return self.identifiers(address).reported

    def entries(self) -> Tuple[NodeIdentifiers, ...]:
        """Every node's identifiers, ordered by short_id -- the whole table."""

        nodes = getattr(self._document, "nodes_by_id", {})
        return tuple(
            self.identifiers(node_id)
            for node_id in sorted(nodes, key=lambda key: getattr(nodes[key], "short_id", 0)))
