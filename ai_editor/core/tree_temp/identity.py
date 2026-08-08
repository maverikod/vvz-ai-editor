"""Tree-temp node identity: the engine's three-way map over a TreeNode forest.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

A tree-temp session (json / yaml / ini / toml) keeps its document as a forest
of :class:`ai_editor.core.tree_temp.tree_node.TreeNode`, each carrying a
mutation-surviving ``stable_id`` UUID4. What it did NOT have is the compact
integer the frozen MCP surface hands callers in ``node_ref``: preview numbered
nodes 1..N by re-walking the current bytes, so the integer was a POSITION -- it
moved when anything above the node was inserted or deleted -- and
``universal_file_edit`` refused it outright.

This module binds that forest to ``tree_engine``'s identity machinery instead
of inventing a second one:

* ``tree_engine.core.short_id.ShortIdMap`` issues the integer against the
  node's UUID4 and never reuses it, so the integer follows the NODE, not its
  place in the document;
* ``tree_engine.plugins.json_pointer.JsonPointerNotation`` builds both
  directions of the RFC 6901 index, driven by the ``step`` callable below --
  the tree-temp forest's own structural knowledge, supplied exactly the way a
  format plugin supplies it;
* ``tree_engine.core.identifier_map.IdentifierMap`` is then used verbatim as
  the resolver, so an integer, a UUID4 and a JSON Pointer all name one node
  through one map.

Two notations, one canonical. RFC 6901 (``/items/0``) is the engine's and
therefore this module's canonical reference notation. The editor's marked-tree
handler has always emitted, and the frozen ``json_pointer`` parameter has
always accepted, the BRACKET form ``/items[0]``.
:func:`bracket_pointer_to_rfc6901` is the one named translation between them;
nothing else in the editor may re-derive it inline.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from tree_engine.core.address import NodeAddressError
from tree_engine.core.identifier_map import IdentifierMap, NodeIdentifiers
from tree_engine.core.short_id import ShortIdMap
from tree_engine.plugins.json_pointer import (
    NOTATION,
    JsonPointerNotation,
    parse_pointer,
)

from ai_editor.core.tree_temp.tree_node import TreeNode

__all__ = [
    "REFERENCE_NOTATION",
    "TreeTempAddressError",
    "bracket_pointer_to_rfc6901",
    "key_path_to_rfc6901",
    "TreeTempIdentityMap",
]

#: The reference notation every tree-temp node answers to, as the engine names
#: it. Reported alongside a computed reference so no caller has to guess.
REFERENCE_NOTATION: str = NOTATION

#: One trailing ``[<digits>]`` group of the editor's bracket array notation.
#: Anchored at the end so it peels indices right-to-left off one path segment.
_ARRAY_INDEX_SUFFIX = re.compile(r"\[(\d+)\]$")


class TreeTempAddressError(ValueError):
    """A tree-temp address names no node, or names more than one.

    A ``ValueError`` on purpose: every tree-temp mutation entry point already
    converts ``ValueError`` into the declared ``INVALID_OPERATION`` result, so
    raising one here keeps the frozen error surface exactly as it is.
    """


def bracket_pointer_to_rfc6901(pointer: str) -> str:
    """Translate the editor's bracket array pointer into canonical RFC 6901.

    ``/items[0]/name`` -> ``/items/0/name``; ``/a[0][1]`` -> ``/a/0/1``. A
    pointer that is already RFC 6901 passes through unchanged, because it has
    no bracket suffix to peel -- which is what lets one entry point accept
    both declared forms without guessing which one it was handed.

    ``""`` is the root pointer. ``"/"`` is accepted as the root as well: the
    marked-tree handler writes the root's pointer as ``"/"``
    (``ai_editor/tree/handlers/json_handler.py`` ``attrs["json_pointer"]``),
    and a lone slash is otherwise indistinguishable from "the root has one
    empty-string key", which no caller means.

    Escaping is left alone. Tokens arrive already escaped per RFC 6901
    (``~0``/``~1``) from a caller, and the bracket notation has never had an
    escape of its own, so re-escaping here would corrupt a legitimate ``~1``.
    The known cost, inherited from the bracket notation rather than introduced
    here: a key whose text ends in ``[<digits>]`` cannot be told apart from an
    array index, and one containing ``/`` cannot be expressed at all.
    """
    if not isinstance(pointer, str):
        raise TreeTempAddressError(
            f"a JSON Pointer must be a str, got {type(pointer).__name__}"
        )
    if pointer in ("", "/"):
        return ""
    if not pointer.startswith("/"):
        raise TreeTempAddressError(
            f"a non-empty JSON Pointer must start with '/': {pointer!r}"
        )
    return _join(_split_bracketed(pointer[1:], "/"))


def key_path_to_rfc6901(key_path: str) -> str:
    """Translate the marked-tree YAML handler's ``key_path`` into RFC 6901.

    ``gamma.inner`` -> ``/gamma/inner``; ``beta[1]`` -> ``/beta/1``; ``""`` is
    the document root. This is the OTHER address notation the editor already
    speaks -- ``ai_editor/tree/handlers/yaml_handler.py`` writes it into every
    preview node's ``attributes["key_path"]`` -- and translating it here is
    what lets a YAML preview node and the tree-temp node it describes be
    recognised as one node.

    It shares the bracket notation's inherited limits and adds one of its own:
    a key containing ``.`` cannot be told apart from a nesting step. That is
    the notation's, not this function's: the handler that emits it has the same
    blind spot, so both sides fail identically and no node is ever silently
    matched to the wrong one.
    """
    if not isinstance(key_path, str):
        raise TreeTempAddressError(
            f"a key_path must be a str, got {type(key_path).__name__}"
        )
    if key_path == "":
        return ""
    return _join(_split_bracketed(key_path, "."))


def _split_bracketed(text: str, separator: str) -> List[str]:
    """Split on ``separator``, peeling trailing ``[<digits>]`` into own tokens."""
    tokens: List[str] = []
    for segment in text.split(separator):
        indices: List[str] = []
        head = segment
        while True:
            match = _ARRAY_INDEX_SUFFIX.search(head)
            if match is None:
                break
            indices.append(match.group(1))
            head = head[: match.start()]
        if head or not indices:
            tokens.append(head)
        tokens.extend(reversed(indices))
    return tokens


def _join(tokens: Sequence[str]) -> str:
    """Join already-escaped tokens into a pointer; ``()`` is the root ``""``."""
    return "".join(f"/{token}" for token in tokens)


def _looks_like_pointer(address: Any) -> bool:
    """True for the two forms this module must translate before resolving."""
    return isinstance(address, str) and (address == "" or address.startswith("/"))


class _Forest:
    """The invisible parent of the forest's roots.

    ``TreeNode`` is a forest, not a tree: a YAML stream or a bare JSON value
    can leave several roots side by side. ``JsonPointerNotation`` walks one
    root, so this wrapper supplies it. It is declared NOT addressable, so it
    never claims a pointer of its own and never appears in the index; a single
    root claims ``""`` instead, exactly as RFC 6901 says the whole document
    does.
    """

    __slots__ = ("children",)

    def __init__(self, roots: Sequence[TreeNode]) -> None:
        self.children: List[TreeNode] = list(roots)


def _forest_step(
    parent: Any, child: Any, ordinal: int
) -> Optional[Tuple[Sequence[str], bool]]:
    """The tree-temp forest's structural step, as the notation contract wants.

    One decision per parent/child pair, and the only place this module encodes
    what a tree-temp container looks like:

    * under the forest wrapper -- a lone root claims the empty pointer, and
      each root of a multi-root forest claims its ordinal, matching how
      ``tree_temp_edit_nodes`` has always addressed a multi-root document;
    * under an ``object`` -- the child's ``key`` is its token;
    * under an ``array`` -- the child's ordinal is its token.

    Anything else (a keyless object member, a child of a scalar) is
    unaddressable and is answered with ``None`` rather than a synthesized
    pointer that would resolve to the wrong node.
    """
    if isinstance(parent, _Forest):
        if len(parent.children) == 1:
            return ((), True)
        return ((str(ordinal),), True)
    if not isinstance(parent, TreeNode) or not isinstance(child, TreeNode):
        return None
    if parent.type == "object":
        if not isinstance(child.key, str):
            return None
        return ((child.key,), True)
    if parent.type == "array":
        return ((str(ordinal),), True)
    return None


class _TreeTempPlugin:
    """Publishes the tree-temp forest's reference notation, plugin-style.

    Duck-typed exactly as ``tree_engine.core.identifier_map.native_reference_of``
    expects: one attribute exposing ``notation`` and ``index(root)``. Stateless
    and shared, because :class:`JsonPointerNotation` is.
    """

    native_reference = JsonPointerNotation(_forest_step, root_addressable=False)


_PLUGIN = _TreeTempPlugin()


class _IndexedNode:
    """One forest node paired with the integer the ShortIdMap issued it.

    ``IdentifierMap.identifiers`` reads ``short_id`` off the value it finds in
    ``nodes_by_id``; the forest's ``TreeNode`` deliberately carries no integer
    of its own, so the pairing lives here and dies with the index.
    """

    __slots__ = ("node", "short_id")

    def __init__(self, node: TreeNode, short_id: int) -> None:
        self.node = node
        self.short_id = short_id


class _ForestDocument:
    """The document view ``tree_engine``'s addressing entry points expect.

    ``normalize_node_address`` and ``IdentifierMap`` are both duck-typed: they
    ask a document for ``nodes_by_id``, ``resolve_short_id``, ``root``,
    ``document_id`` and ``document_version``, and nothing else. Supplying those
    five is what lets the tree-temp forest reuse the engine's resolver instead
    of growing a second one here.
    """

    __slots__ = ("root", "nodes_by_id", "document_id", "document_version", "_short_ids")

    def __init__(
        self,
        roots: Sequence[TreeNode],
        indexed: Dict[uuid.UUID, _IndexedNode],
        short_ids: ShortIdMap,
        version: int,
    ) -> None:
        self.root = _Forest(roots)
        self.nodes_by_id = indexed
        self.document_id: Optional[uuid.UUID] = None
        self.document_version = version
        self._short_ids = short_ids

    def resolve_short_id(self, short_id: int) -> Iterable[uuid.UUID]:
        """Every node_id carrying ``short_id`` -- one, or none at all."""
        node_id = self._short_ids.get_node_id(short_id)
        return () if node_id is None else (node_id,)


def _walk(roots: Sequence[TreeNode]) -> Iterator[TreeNode]:
    """Every node of the forest, root-first, in document order."""
    for node in roots:
        yield node
        yield from _walk(node.children or [])


def _node_uuid(node: TreeNode) -> Optional[uuid.UUID]:
    """The node's canonical UUID4, or ``None`` when its stable_id is not one.

    The same value the engine's pointer index reads off the node, taken from
    the same property, so the map and the index can never disagree about which
    node an identifier belongs to.
    """
    return node.node_id


class TreeTempIdentityMap:
    """One tree-temp document's integer <-> UUID4 <-> JSON Pointer identity.

    Lives on the edit session for as long as the file is open, which is what
    makes the integer stable: :meth:`sync` issues one to every node it has not
    seen before and leaves every node it has already numbered exactly as it
    was, so inserting above a node changes that node's POINTER and leaves its
    INTEGER alone. Deleted nodes are released, and ``ShortIdMap`` never reissues
    a released integer, so a stale address is an unknown address rather than
    someone else's node.
    """

    __slots__ = ("_short_ids", "_version", "_reserved", "_document", "_map")

    def __init__(self) -> None:
        self._short_ids = ShortIdMap()
        self._version = 0
        self._reserved: List[uuid.UUID] = []
        self._document: Optional[_ForestDocument] = None
        self._map: Optional[IdentifierMap] = None

    # -- keeping the map level with the document ----------------------------

    def sync(self, roots: Sequence[TreeNode]) -> "TreeTempIdentityMap":
        """Number every node of ``roots``, preserving every integer already issued.

        Called before each read of the map and after each mutation. Allocation
        is in document order, so a freshly opened document numbers 1..N exactly
        as the positional walk it replaces did; from the first edit onward the
        two diverge, and this one is the correct half.
        """
        live: Dict[uuid.UUID, _IndexedNode] = {}
        for node in _walk(roots):
            node_id = _node_uuid(node)
            if node_id is None or node_id in live:
                continue
            short_id = self._short_ids.get_short_id(node_id)
            if short_id is None:
                short_id = self._short_ids.allocate(node_id)
            live[node_id] = _IndexedNode(node, short_id)
        for gone in self._reserved + [n for n in self._known() if n not in live]:
            self._short_ids.release(gone)
        self._reserved = []
        self._version += 1
        self._document = _ForestDocument(roots, live, self._short_ids, self._version)
        self._map = IdentifierMap(self._document, _PLUGIN)
        return self

    def _known(self) -> List[uuid.UUID]:
        document = self._document
        return [] if document is None else list(document.nodes_by_id)

    # -- reading the map ----------------------------------------------------

    @property
    def notation(self) -> str:
        """The name of the notation ``ref`` values are written in."""
        return REFERENCE_NOTATION

    def _require(self) -> Tuple[_ForestDocument, IdentifierMap]:
        if self._document is None or self._map is None:
            raise TreeTempAddressError("tree-temp identity map used before sync()")
        return self._document, self._map

    def identifiers(self, address: Any) -> NodeIdentifiers:
        """Every identifier the addressed node answers to: integer, UUID4, pointer."""
        document, mapping = self._require()
        del document
        try:
            return mapping.identifiers(self._canonical(address))
        except NodeAddressError as exc:
            raise TreeTempAddressError(
                f"unresolvable tree-temp node address {address!r}"
            ) from exc

    def node(self, address: Any) -> TreeNode:
        """The node ``address`` names, whichever of the three forms it is written in."""
        document, mapping = self._require()
        try:
            node_id = mapping.resolve(self._canonical(address))
        except NodeAddressError as exc:
            raise TreeTempAddressError(
                f"unresolvable tree-temp node address {address!r}"
            ) from exc
        indexed = document.nodes_by_id.get(node_id)
        if indexed is None:
            raise TreeTempAddressError(
                f"unresolvable tree-temp node address {address!r}"
            )
        return indexed.node

    def short_id_for_reference(self, reference: str) -> Optional[int]:
        """The integer naming the node at ``reference``, or ``None`` if there is none.

        ``reference`` is a canonical RFC 6901 pointer -- translate one of the
        editor's own notations with :func:`bracket_pointer_to_rfc6901` or
        :func:`key_path_to_rfc6901` first. Used where the editor holds a node's
        POSITION and needs the identity that outlives it.
        """
        document, mapping = self._require()
        node_id = mapping.node_for_ref(reference)
        if node_id is None:
            return None
        indexed = document.nodes_by_id.get(node_id)
        return None if indexed is None else indexed.short_id

    def reserve_unmapped(self) -> int:
        """An integer for something this document's identity does not cover.

        Issued against a UUID4 that belongs to no node, so it can never collide
        with a real node's integer now or later: ``ShortIdMap`` is monotonic and
        never reissues. The next :meth:`sync` releases it, and an edit addressed
        to it resolves to nothing -- which is the honest answer for a node the
        identity map cannot see.
        """
        reserved = uuid.uuid4()
        self._reserved.append(reserved)
        return int(self._short_ids.allocate(reserved))

    def _canonical(self, address: Any) -> Any:
        """Put a pointer into the canonical notation; leave every other form alone."""
        if _looks_like_pointer(address):
            canonical = bracket_pointer_to_rfc6901(address)
            parse_pointer(canonical)
            return canonical
        if isinstance(address, str):
            return address.strip()
        return address
