"""Canonical address-normalization layer for concept C-004 (NodeIdentityAndAddressing).

Scope (concept C-004, narrowed to string-form serialization of ``NodeAddress``
and the mandatory ``normalize_node_address`` entry point): this module owns
the ``to_str``/``from_str`` external string-form helpers for the imported
``NodeAddress`` type, the single ``normalize_node_address`` function every
public node-address operation must call first per {j9rh}, the
``NodeAddressError`` exception hierarchy, and the {p021} node-view helper
``build_node_address_view``.

ACCEPTANCE NOTE (orchestrator integration decision): the canonical
``NodeAddress`` and ``AddressRemap`` types are defined in the sibling module
``tree_engine.core.identity`` -- this file imports ``NodeAddress`` from
there and never redefines it. This module is read-only with respect to
document state: no code path here mutates a short_id map, a node table, a
generation counter, or an allocator.

Sibling contract not yet available as an importable module in this worktree
-- the document-local bidirectional short_id<->UUID4 map (``short_id.py``,
delivered by a parallel T-001 artifact) -- is consumed here only as a
caller-injected, duck-typed callable, following the same pattern already
used by ``core/validation.py`` (``next_short_id``) and ``core/node_types.py``
(``index_map_hook``): this file never imports that sibling module and never
stubs a fake replacement for it.

``document`` is consumed only through minimal, duck-typed attributes, the
same convention ``core/identity.py``'s ``replace_node_id`` and
``core/validation.py``'s ``validate_mutation`` already rely on:

* ``document.nodes_by_id`` -- a mapping (supports ``in``) of canonical
  ``uuid.UUID`` node_id to node object. Read-only here.
* ``document.resolve_short_id(short_id: int) -> Sequence[uuid.UUID]`` --
  the short-id-map module's public accessor, consulted only when no
  ``resolve_short_id`` callable is explicitly injected into
  :func:`normalize_node_address`. It returns the sequence of node_id
  matches for ``short_id`` (normally zero or one; more than one is treated
  defensively as an ambiguous resolution rather than assumed impossible).

Source-of-truth requirement labels honored here: {j9rh}, {p021}, {p080}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Union
from uuid import UUID

from tree_engine.core.identity import NodeAddress

__all__ = [
    "to_str",
    "serialize",
    "from_str",
    "parse",
    "NodeAddressError",
    "UnknownAddressError",
    "AmbiguousAddressError",
    "ForeignDocumentAddressError",
    "ShortIdResolver",
    "normalize_node_address",
    "NodeAddressView",
    "build_node_address_view",
]

# Duck-typed accessor injected by a caller (or looked up on ``document`` as
# ``document.resolve_short_id``) to resolve a positive-int short_id to the
# sequence of matching canonical node_id values. See module docstring.
ShortIdResolver = Callable[[int], Sequence[UUID]]

_HEX_PREFIXES = ("0x", "0X")


# --------------------------------------------------------------------------
# External string-form serialization ({p080} explicit round-trip form)
# --------------------------------------------------------------------------


def to_str(address: NodeAddress) -> str:
    """Serialize ``address`` to its ``"document_id:node_id"`` string form.

    Both parts are always emitted explicitly as canonical hyphenated UUID4
    strings, regardless of the implicit-local in-memory form ``NodeAddress``
    otherwise permits. Raises ``ValueError`` when ``address.document_id`` is
    ``None`` (the implicit-local form), since no document identifier is
    then available to emit.
    """

    if address.document_id is None:
        raise ValueError(
            "cannot serialize NodeAddress to its string form: document_id "
            "is None (implicit-local form carries no explicit document_id)"
        )
    return f"{address.document_id}:{address.node_id}"


# Alias, per the step spec's "to_str/serialize" naming.
serialize = to_str


def from_str(text: str) -> NodeAddress:
    """Parse the ``"document_id:node_id"`` string form into a ``NodeAddress``.

    Both parts are required. Raises ``ValueError`` for any malformed input:
    a non-string argument, a missing or extra ``":"`` separator, an empty
    segment, or a segment that is not a syntactically valid UUID.
    """

    if not isinstance(text, str):
        raise ValueError(f"expected a str, got {type(text).__name__}")

    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"malformed node address {text!r}: expected exactly one ':' "
            f"separator (document_id:node_id), found {len(parts) - 1}"
        )

    document_part, node_part = parts
    if not document_part or not node_part:
        raise ValueError(f"malformed node address {text!r}: empty segment")

    try:
        document_id = UUID(document_part)
        node_id = UUID(node_part)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"malformed node address {text!r}: invalid UUID segment") from exc

    return NodeAddress(document_id=document_id, node_id=node_id)


# Alias, per the step spec's "from_str/parse" naming.
parse = from_str


# --------------------------------------------------------------------------
# Exception hierarchy
# --------------------------------------------------------------------------


class NodeAddressError(Exception):
    """Base error for a rejected node-address normalization.

    Always carries the offending raw ``address`` argument exactly as given
    to :func:`normalize_node_address`, so a caller can inspect what was
    rejected without re-parsing an error message.
    """

    def __init__(self, raw_address: Any, message: Optional[str] = None) -> None:
        self.raw_address = raw_address
        super().__init__(message or f"invalid node address: {raw_address!r}")


class UnknownAddressError(NodeAddressError):
    """Raised when ``address`` cannot be resolved to any node of the document.

    Covers a UUID4 node_id absent from the document's node table and an
    int/hex short_id absent from the document's short_id map.
    """


class AmbiguousAddressError(NodeAddressError):
    """Raised when short_id resolution defensively detects more than one match.

    The short_id<->UUID4 map is a bidirectional map and should never
    legitimately produce more than one match for a single short_id; this
    error exists purely as a defensive guard against that invariant being
    violated, rather than an assumption that it cannot happen.
    """


class ForeignDocumentAddressError(NodeAddressError):
    """Raised when ``address`` explicitly names a document_id other than the current one.

    Raised immediately, before any local short_id-map or node-table lookup
    is attempted -- ``document_id`` carries the offending foreign document
    identifier.
    """

    def __init__(self, raw_address: Any, document_id: UUID, message: Optional[str] = None) -> None:
        self.document_id = document_id
        super().__init__(
            raw_address,
            message
            or (
                f"node address {raw_address!r} names foreign document_id "
                f"{document_id!r}"
            ),
        )


# --------------------------------------------------------------------------
# normalize_node_address -- the single mandatory entry point per {j9rh}
# --------------------------------------------------------------------------


def _validate_node_id_presence(document: Any, node_id: UUID, raw_address: Any) -> UUID:
    """Confirm ``node_id`` is present in ``document.nodes_by_id``, or reject.

    Pure lookup: never mutates ``document`` or anything reachable from it.
    """

    nodes_by_id = getattr(document, "nodes_by_id", None)
    if nodes_by_id is None or node_id not in nodes_by_id:
        raise UnknownAddressError(raw_address)
    return node_id


def _resolve_node_address_value(
    document: Any,
    node_address: NodeAddress,
    raw_address: Any,
    current_document_id: Optional[UUID],
) -> UUID:
    """Apply the foreign-document check, then validate the local node_id."""

    if node_address.document_id is not None and node_address.document_id != current_document_id:
        raise ForeignDocumentAddressError(raw_address, node_address.document_id)
    return _validate_node_id_presence(document, node_address.node_id, raw_address)


def _resolve_short_id(
    document: Any,
    short_id: int,
    raw_address: Any,
    resolve_short_id: Optional[ShortIdResolver],
) -> UUID:
    """Resolve a positive-int short_id via the injected or duck-typed accessor.

    Never touches the short-id-map's internal storage directly: it only
    calls the public accessor, either explicitly injected by the caller or
    found as ``document.resolve_short_id``. Read-only: performs no
    mutation regardless of outcome.
    """

    resolver = resolve_short_id if resolve_short_id is not None else getattr(
        document, "resolve_short_id", None
    )
    if resolver is None:
        # No accessor available at all: the address cannot be resolved.
        raise UnknownAddressError(raw_address)

    matches = list(resolver(short_id))
    if len(matches) == 0:
        raise UnknownAddressError(raw_address)
    if len(matches) > 1:
        raise AmbiguousAddressError(raw_address)
    return matches[0]


def normalize_node_address(
    document: Any,
    address: Union[UUID, int, str, NodeAddress],
    *,
    current_document_id: Optional[UUID],
    resolve_short_id: Optional[ShortIdResolver] = None,
) -> UUID:
    """Resolve any accepted address form to its canonical ``uuid.UUID`` node_id.

    The single mandatory entry point every public node-address operation
    must call first, per {j9rh}. Accepts ``address`` as:

    * ``uuid.UUID`` -- a canonical node_id, validated against
      ``document.nodes_by_id``.
    * ``int`` -- a positive document-local short_id, resolved through the
      short_id map.
    * ``str`` -- a ``"0x"``-prefixed hex short_id, a DECIMAL-digit short_id,
      a bare UUID string, or a serialized ``"document_id:node_id"``
      ``NodeAddress`` (see :func:`from_str`). The decimal form is tried
      before the UUID form and resolves exactly like the ``int`` it spells,
      so ``"3"`` and ``3`` are the same address: callers that carry a
      short_id through a string-typed protocol field -- the editor's
      ``node_ref`` is one -- would otherwise fall through every branch and
      be rejected as unknown. Only ASCII digits count, so a non-ASCII
      decimal digit is not silently reinterpreted.
    * ``NodeAddress`` -- resolved directly.

    A ``NodeAddress``-shaped address (an explicit ``NodeAddress`` instance
    or a serialized string form) whose ``document_id`` differs from
    ``current_document_id`` raises :class:`ForeignDocumentAddressError`
    immediately, before any local short_id-map or node-table lookup. An
    unresolvable UUID or short_id raises :class:`UnknownAddressError`. A
    defensively-detected multi-match short_id resolution raises
    :class:`AmbiguousAddressError`. Every rejection path is read-only: no
    mutation of the short_id map, node table, generation counters, or
    allocator state, and no partial operation is ever started.

    Returns the canonical ``uuid.UUID`` node_id -- the canonicalization
    target per {j9rh} -- never a ``NodeAddress``.
    """

    raw_address = address

    if isinstance(address, NodeAddress):
        return _resolve_node_address_value(document, address, raw_address, current_document_id)

    if isinstance(address, UUID):
        return _validate_node_id_presence(document, address, raw_address)

    if isinstance(address, bool):
        # bool is a subclass of int in Python; explicitly not an accepted
        # address form.
        raise UnknownAddressError(raw_address)

    if isinstance(address, int):
        if address <= 0:
            raise UnknownAddressError(raw_address)
        return _resolve_short_id(document, address, raw_address, resolve_short_id)

    if isinstance(address, str):
        if address.startswith(_HEX_PREFIXES):
            try:
                short_id = int(address, 16)
            except ValueError:
                raise UnknownAddressError(raw_address) from None
            if short_id <= 0:
                raise UnknownAddressError(raw_address)
            return _resolve_short_id(document, short_id, raw_address, resolve_short_id)

        if ":" in address:
            try:
                parsed_address = from_str(address)
            except ValueError:
                raise UnknownAddressError(raw_address) from None
            return _resolve_node_address_value(
                document, parsed_address, raw_address, current_document_id
            )

        if address.isascii() and address.isdigit():
            short_id = int(address)
            if short_id <= 0:
                raise UnknownAddressError(raw_address)
            return _resolve_short_id(document, short_id, raw_address, resolve_short_id)

        try:
            node_id = UUID(address)
        except ValueError:
            raise UnknownAddressError(raw_address) from None
        return _validate_node_id_presence(document, node_id, raw_address)

    raise UnknownAddressError(raw_address)


# --------------------------------------------------------------------------
# View contract per {p021}
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeAddressView:
    """The pair of identifiers {p021} requires every node view to expose.

    ``short_id_hex`` is the compact, ``"0x"``-prefixed hexadecimal
    rendering used for later re-addressing; ``node_id`` is the canonical
    UUID4 string. ``short_id_hex`` never replaces ``node_id`` -- both are
    always present together.
    """

    short_id_hex: str
    node_id: str


def build_node_address_view(node_id: Union[UUID, str], short_id: int) -> NodeAddressView:
    """Build the {p021} view pair from a canonical node_id and its short_id.

    ``node_id`` may be given as a ``uuid.UUID`` or its canonical string
    form; ``short_id`` is the positive document-local integer id. Every
    node listing/view assembler elsewhere in the tree engine is expected to
    call this helper so ``short_id_hex`` and ``node_id`` are always
    populated together.
    """

    node_id_value = node_id if isinstance(node_id, UUID) else UUID(str(node_id))
    return NodeAddressView(
        short_id_hex=f"0x{int(short_id):x}",
        node_id=str(node_id_value),
    )
