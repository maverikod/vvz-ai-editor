"""RFC 6901 JSON Pointer: the notation itself, and the walker plugins drive.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the *syntax* of JSON Pointer -- token escaping, joining and splitting --
plus one generic tree walk that turns a plugin's own structural knowledge into
the two directions of a pointer index. Nothing here knows what a JSON object,
a YAML mapping or a TOML table looks like: every structural decision is taken
by the ``step`` callable the plugin supplies to :class:`JsonPointerNotation`.
That is the whole point of this file living beside the plugins rather than in
the core: the core must never contain a branch testing ``if format == "json"``,
and three plugins must not each re-implement ``~0``/``~1`` escaping.

The contract a plugin's ``step`` implements, for one ``child`` of one
``parent``:

* ``None`` -- ``child`` and its whole subtree carry no pointer. A YAML comment,
  a TOML blank line and a JSON member key are not addressable by RFC 6901, and
  saying so is the honest answer; a synthesized pointer would be a lie.
* ``(tokens, addressable)`` -- ``tokens`` are the pointer tokens ``child``
  contributes below its parent's pointer (already unescaped: this module
  escapes them), and ``addressable`` says whether ``child`` ITSELF is the node
  that pointer names. A structural wrapper that routes but is not named --
  ``json:Member``, ``yaml:Pair`` -- returns tokens with ``addressable=False``,
  and its value child then returns ``((), True)`` to claim the pointer the
  wrapper built.

``ordinal`` is the number of preceding siblings that contributed at least one
token, which is exactly the array/sequence index a plugin needs and which no
plugin can compute on its own without re-walking its parent.

A pointer claimed by more than one node is not an identifier: it is dropped
from BOTH directions of the index and reported through
:attr:`PointerIndex.ambiguous`, so a duplicate mapping key can never make the
engine resolve a pointer to an arbitrary one of two nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple
from uuid import UUID

__all__ = [
    "NOTATION",
    "escape_token",
    "unescape_token",
    "build_pointer",
    "parse_pointer",
    "PointerStep",
    "PointerIndex",
    "JsonPointerNotation",
]

#: The name a plugin publishes for this notation, carried alongside every
#: computed reference so a caller never has to guess how to parse one.
NOTATION = "json_pointer"

#: What one ``step`` call may answer. See the module docstring.
PointerStep = Callable[[Any, Any, int], Optional[Tuple[Sequence[str], bool]]]


def escape_token(token: str) -> str:
    """Escape one reference token per RFC 6901 section 3 (``~`` then ``/``).

    The order is not interchangeable: escaping ``/`` first would turn the
    ``~1`` it produces into ``~01``.
    """

    return str(token).replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    """Reverse :func:`escape_token`, decoding ``~1`` before ``~0``."""

    return str(token).replace("~1", "/").replace("~0", "~")


def build_pointer(tokens: Sequence[str]) -> str:
    """Join already-escaped ``tokens`` into a pointer; ``()`` is the root ``""``."""

    return "".join(f"/{token}" for token in tokens)


def parse_pointer(text: str) -> Tuple[str, ...]:
    """Split a pointer into its unescaped tokens; ``""`` yields ``()``.

    Raises ``ValueError`` for anything that is not a pointer -- a non-string,
    or a non-empty value that does not start with ``"/"`` -- rather than
    guessing at a caller's intent.
    """

    if not isinstance(text, str):
        raise ValueError(f"a JSON Pointer must be a str, got {type(text).__name__}")
    if text == "":
        return ()
    if not text.startswith("/"):
        raise ValueError(f"a non-empty JSON Pointer must start with '/': {text!r}")
    return tuple(unescape_token(part) for part in text[1:].split("/"))


@dataclass(frozen=True)
class PointerIndex:
    """Both directions of a document's pointer index, plus what was refused.

    ``by_node`` maps a node's canonical UUID4 to its pointer and ``by_pointer``
    is its exact inverse -- the two are always consistent, because an ambiguous
    pointer is removed from both. ``ambiguous`` holds every pointer more than
    one node claimed, so the reason a node has no reference stays inspectable
    instead of silently absent.
    """

    by_node: Dict[UUID, str]
    by_pointer: Dict[str, UUID]
    ambiguous: Tuple[str, ...]

    def ref_for(self, node_id: UUID) -> Optional[str]:
        """The pointer naming ``node_id``, or ``None`` when it has none."""

        return self.by_node.get(node_id)

    def node_for(self, ref: str) -> Optional[UUID]:
        """The node ``ref`` names, or ``None`` when no node claims it."""

        return self.by_pointer.get(ref)


def _children(node: Any) -> Sequence[Any]:
    """The child sequence of a common-model or live node, or ``()``."""

    children = getattr(node, "children", None)
    return children if isinstance(children, (list, tuple)) else ()


class JsonPointerNotation:
    """One plugin's JSON Pointer support: a ``step`` plus a root convention.

    ``root_addressable`` says whether the tree's own root node is the node the
    empty pointer names. JSON's root value is (``{}`` IS the whole document),
    and so is a TOML document (the document IS the root table); a YAML
    ``yaml:Document`` is not -- it is a stream wrapper whose single value block
    is what ``""`` names, and that block claims the pointer by returning
    ``((), True)``.

    Instances are stateless and immutable: one is built at plugin-module import
    and published as the plugin's ``native_reference`` attribute, exactly as
    ``fragment_container_kinds`` is published today.
    """

    __slots__ = ("_step", "_root_addressable")

    #: The notation name every :class:`PointerIndex` this object builds speaks.
    notation = NOTATION

    def __init__(self, step: PointerStep, *, root_addressable: bool = True) -> None:
        self._step = step
        self._root_addressable = root_addressable

    def index(self, root: Any) -> PointerIndex:
        """Walk ``root`` and build both directions of its pointer index."""

        by_node: Dict[UUID, str] = {}
        by_pointer: Dict[str, UUID] = {}
        ambiguous: List[str] = []
        seen: Set[str] = set()
        for node, pointer in self._walk(root, (), self._root_addressable):
            node_id = getattr(node, "node_id", None)
            if not isinstance(node_id, UUID):
                continue
            if pointer in seen:
                # A second claimant makes the pointer useless as an identifier:
                # withdraw it from the first claimant too rather than resolve it
                # to whichever node happened to be walked first.
                if pointer not in ambiguous:
                    ambiguous.append(pointer)
                owner = by_pointer.pop(pointer, None)
                if owner is not None:
                    by_node.pop(owner, None)
                by_node.pop(node_id, None)
                continue
            seen.add(pointer)
            by_node[node_id] = pointer
            by_pointer[pointer] = node_id
        return PointerIndex(by_node=by_node, by_pointer=by_pointer,
                            ambiguous=tuple(ambiguous))

    def _walk(self, node: Any, tokens: Tuple[str, ...],
              addressable: bool) -> Iterator[Tuple[Any, str]]:
        """Yield ``(node, pointer)`` for every addressable node of the subtree."""

        if addressable:
            yield node, build_pointer(tokens)
        ordinal = 0
        for child in _children(node):
            outcome = self._step(node, child, ordinal)
            if outcome is None:
                continue
            child_tokens, child_addressable = outcome
            escaped = tuple(escape_token(token) for token in child_tokens)
            if escaped:
                ordinal += 1
            yield from self._walk(child, tokens + escaped, bool(child_addressable))
