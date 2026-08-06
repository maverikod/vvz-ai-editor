"""Canonical reference-representation helpers for concept C-008 (ReferenceIntegrity).

Scope (concept C-008, narrowed to the reference-representation surface
only): this module adds the small set of pure helpers that sit directly on
top of the canonical ``NodeAddress`` value type — locality classification,
external string-form parsing, and external string-form serialization. It
owns none of the heavier C-008 machinery: no index maps, no derived
object-reference cache, no generation-based cache invalidation, no
post-mutation local validation, and no full-document validation. Those are
delivered by sibling atomic steps under G-013/T-001 (and, for the object
cache specifically, the step tied to the ``generation-tracked-object-cache``
output). This file also contains no tree traversal and no mutation logic.

Dual-representation contract, per {p080}: references between nodes are
carried by two consistent representations. The canonical one is
``NodeAddress(document_id, node_id)``, imported unchanged from the sibling
C-004 identity module (``tree_engine.core.identity``) — this module does
NOT define a second ``NodeAddress`` type. For an intra-document reference,
``document_id`` may be held implicitly in memory as "the current document"
(represented here, per the C-004 contract, as ``document_id is None``);
but when such a reference is serialized to its external string form, the
document identifier is always made explicit. ``NodeAddress`` is the
canonical source of truth; a direct object reference is only a derived,
accelerating cache with no independent authority over identity — that
cache (and its generation-based invalidation) is owned by a sibling
artifact, not by this file.

External string-form grammar, shared with and kept round-trippable
against the C-004 addressing contract in ``core/address.py``:

    "<document_id>:<node_id>"

where ``<document_id>`` and ``<node_id>`` are each the canonical
hyphenated ``uuid.UUID`` string form (e.g.
``"550e8400-e29b-41d4-a716-446655440000"``), separated by exactly one
``":"`` character, with no leading, trailing, or embedded whitespace and
no additional segments. Parsing performs no I/O, no document loading, and
no resolvability check of any kind — it only accepts or rejects the
syntactic shape of the text and, on acceptance, builds the corresponding
explicit-``document_id`` ``NodeAddress``. Whether either UUID actually
identifies something that exists is a question for local or full
validation, both delivered by sibling steps.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.errors import ErrorCode, error_layer

__all__ = [
    "InvalidNodeAddressError",
    "is_local",
    "is_external",
    "parse_node_address",
    "node_address_to_string",
]


class InvalidNodeAddressError(ValueError):
    """Raised when a NodeAddress external string form cannot be produced or parsed.

    Covers exactly two situations, both purely syntactic / representational
    — never a resolvability or existence check, which belongs to sibling
    local/full validation steps:

    * ``parse_node_address`` was given text that does not match the
      ``"<document_id>:<node_id>"`` grammar (bad UUID segment, wrong
      separator count, missing or extra parts, empty string).
    * ``node_address_to_string`` was asked to serialize a local
      (``document_id is None``) address without an explicit
      ``current_document_id`` to substitute, so no document identifier is
      available to emit.

    Carries the stable ``ErrorCode``/``ErrorLayer`` pair from the shared
    catalog in ``tree_engine.errors`` (see {p023}) instead of inventing a
    new ad-hoc error identifier: ``ErrorCode.INVALID_SELECTOR`` is the
    closest existing catalog entry for "the reference text/shape handed in
    is malformed", as distinct from ``ErrorCode.UNRESOLVED_REFERENCE``,
    which names a semantic resolution failure this module never performs.
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_SELECTOR,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.layer = error_layer(code)


def is_local(address: NodeAddress) -> bool:
    """Return ``True`` iff ``address`` is in the implicit-current-document form.

    Per {p080}, an intra-document reference may hold ``document_id``
    implicitly as "the current document"; the imported C-004
    ``NodeAddress`` contract represents that implicit form as
    ``document_id is None``. This is a pure field check: no I/O, no
    resolvability check, no lookup against any document or index.
    """

    return address.document_id is None


def is_external(address: NodeAddress) -> bool:
    """Return ``True`` iff ``address`` carries an explicit ``document_id``.

    The exact negation of :func:`is_local`. An "external" address here
    means only "this instance names its document explicitly" — it says
    nothing about whether that document is loaded or whether the address
    actually resolves to a real node; both are questions for sibling
    local/full validation steps, never answered here.
    """

    return not is_local(address)


def _parse_uuid_segment(segment: str, *, what: str, original_text: str) -> UUID:
    """Parse one ``:``-delimited segment of an external address as a UUID.

    Raises :class:`InvalidNodeAddressError` when ``segment`` is empty or is
    not a syntactically valid UUID. This performs no interpretation beyond
    UUID syntax: it does not require UUID version 4 specifically, since the
    address grammar's job is only to recognize the ``"a:b"`` shape, not to
    police identifier-generation policy (that is owned by the C-004
    identity module for freshly minted ids).
    """

    if not segment:
        raise InvalidNodeAddressError(
            f"malformed node address {original_text!r}: {what} segment is empty"
        )
    try:
        return UUID(segment)
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidNodeAddressError(
            f"malformed node address {original_text!r}: {what} segment "
            f"{segment!r} is not a valid UUID"
        ) from exc


def parse_node_address(text: str) -> NodeAddress:
    """Parse the external string form into a ``NodeAddress`` with an explicit document_id.

    Accepts only text matching the ``"<document_id>:<node_id>"`` grammar
    documented at module level: exactly one ``":"`` separator and two
    non-empty UUID segments. Performs no I/O, no document loading, and no
    resolvability check of any kind — local and full validation are owned
    by sibling steps under G-013/T-001.

    Raises :class:`InvalidNodeAddressError` for every syntactically
    malformed input, including (non-exhaustively): a non-string argument,
    the empty string, text with no ``":"`` separator, text with more than
    one ``":"`` (extra segments), a missing document_id or node_id
    segment, and a segment that is not a syntactically valid UUID.

    On success, always returns a ``NodeAddress`` whose ``document_id`` is
    not ``None`` — the external form has no implicit-document case, per
    {p080} ("at serialization of an external reference, document_id is
    given explicitly").
    """

    if not isinstance(text, str):
        raise InvalidNodeAddressError(
            f"malformed node address: expected a str, got {type(text).__name__}"
        )

    parts = text.split(":")
    if len(parts) != 2:
        raise InvalidNodeAddressError(
            f"malformed node address {text!r}: expected exactly one ':' "
            f"separator (document_id:node_id), found {len(parts) - 1}"
        )

    document_part, node_part = parts
    document_id = _parse_uuid_segment(document_part, what="document_id", original_text=text)
    node_id = _parse_uuid_segment(node_part, what="node_id", original_text=text)

    return NodeAddress(document_id=document_id, node_id=node_id)


def node_address_to_string(
    address: NodeAddress,
    current_document_id: Optional[UUID] = None,
) -> str:
    """Serialize ``address`` to its external string form with an explicit document_id.

    Per {p080}, an external serialization always names its document
    explicitly, even when the in-memory ``NodeAddress`` held it implicitly
    as "the current document" (``document_id is None``). Contract:

    * If ``address.document_id`` is already set, it is used verbatim and
      ``current_document_id`` is ignored (no conflict check is performed
      between the two — the instance's own explicit id always wins, since
      it unambiguously already names one document).
    * If ``address.document_id`` is ``None`` (the local/implicit case),
      the caller MUST supply ``current_document_id`` so a document
      identifier is available to emit; when both are ``None``, no
      document identifier exists to serialize and
      :class:`InvalidNodeAddressError` is raised instead of silently
      guessing or omitting it.

    The output always matches the ``"<document_id>:<node_id>"`` grammar
    parsed by :func:`parse_node_address`, using each UUID's canonical
    hyphenated string form, so round-tripping through
    ``parse_node_address(node_address_to_string(addr))`` reproduces an
    equal ``NodeAddress`` whenever ``addr`` already carries an explicit
    ``document_id``.
    """

    document_id = address.document_id if address.document_id is not None else current_document_id
    if document_id is None:
        raise InvalidNodeAddressError(
            "cannot serialize NodeAddress to its external string form: "
            "address.document_id is None (implicit current-document form) "
            "and no current_document_id was supplied to substitute"
        )

    return f"{document_id}:{address.node_id}"
