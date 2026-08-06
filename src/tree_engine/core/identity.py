"""Canonical node identity and atomic id-replacement subsystem.

Scope (concept C-004, narrowed to node identity assignment and atomic id
replacement only): this module owns the canonical ``NodeAddress`` value
type, the ``AddressRemap`` result type, fresh UUID4 generation, identifier
stability for unchanged nodes, and the atomic ``replace_node_id`` operation.

Explicitly out of scope here (delivered by sibling artifacts under
T-003/C-008): ``short_id`` allocation and its bidirectional map,
``normalize_node_address``, and reference/object-cache index maintenance.

ACCEPTANCE NOTE (orchestrator integration decision): ``NodeAddress`` as
defined in this module is the single canonical NodeAddress for the whole
tree engine. Sibling artifacts (``address.py`` under T-003,
``references.py`` under T-005) import it from here and must not redefine
it.

This module is self-contained: it depends only on the standard library
(``uuid``, ``dataclasses``, ``typing``) and imports nothing from any
sibling project module.

Source-of-truth requirement labels honored here: {p013}, {p080}, {p084},
{p097}, {p109}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID, uuid4

__all__ = [
    "NodeAddress",
    "AddressRemap",
    "NodeIdentityError",
    "generate_node_id",
    "assign_node_id",
    "replace_node_id",
]


class NodeIdentityError(Exception):
    """Raised when a node-identity operation cannot be completed.

    Covers a syntactically invalid new node_id and a new node_id that
    already collides with an existing entry in the document's internal
    id mapping. Raising this error guarantees the triggering operation
    performed no partial mutation of the document.
    """


@dataclass(frozen=True)
class NodeAddress:
    """Canonical cross-document address of a node.

    ``node_id`` is the required canonical UUID4 identifier of the node.
    ``document_id`` is ``None`` for the implicit-current-document (local)
    form used in memory per {p080}, or an explicit UUID4 document
    identifier for a cross-document / external reference.

    Immutable and hashable: safe as a dict key, and equality is defined
    structurally over the ``(document_id, node_id)`` pair, so two
    instances addressing the same document/node compare equal even if
    constructed separately.
    """

    node_id: UUID
    document_id: Optional[UUID] = None


@dataclass(frozen=True)
class AddressRemap:
    """Result of a successful ``replace_node_id`` call.

    ``old`` is the ``NodeAddress`` that identified the node before the
    replacement; ``new`` is the ``NodeAddress`` that identifies it
    afterwards. Both share the same ``document_id`` as the document the
    replacement was performed against.
    """

    old: NodeAddress
    new: NodeAddress


def generate_node_id() -> UUID:
    """Return a fresh, randomly generated UUID4 node identifier.

    Each call is independent and uses ``uuid.uuid4()``'s cryptographic
    random source, so collisions across calls are not a practical
    concern.
    """

    return uuid4()


def assign_node_id(existing_id: Optional[UUID] = None) -> UUID:
    """Return the canonical node_id to use for a node.

    Per {p013}, identifiers of unchanged nodes are preserved without any
    global old/new tree mapping: when ``existing_id`` is provided it is
    returned unchanged. When ``existing_id`` is ``None`` (a new node), a
    fresh, unique UUID4 is generated and returned.
    """

    if existing_id is not None:
        return existing_id
    return generate_node_id()


def _validate_uuid4(value: Any, *, what: str) -> UUID:
    """Validate that ``value`` is a syntactically valid UUID4.

    Accepts a ``uuid.UUID`` instance directly, or a string/bytes-like
    value that can be parsed into one. Raises ``NodeIdentityError`` when
    the value is not a UUID at all, or is a well-formed UUID of a
    version other than 4.
    """

    candidate: Optional[UUID]
    if isinstance(value, UUID):
        candidate = value
    else:
        try:
            candidate = UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            candidate = None

    if candidate is None:
        raise NodeIdentityError(
            f"{what} is not a syntactically valid UUID: {value!r}"
        )
    if candidate.version != 4:
        raise NodeIdentityError(
            f"{what} is not a valid UUID4 (version={candidate.version}): "
            f"{candidate!r}"
        )
    return candidate


def replace_node_id(document: Any, old_node_id: UUID, new_node_id: UUID) -> AddressRemap:
    """Atomically replace a node's canonical id with a new UUID4.

    ``document`` is assumed to already expose an internal id mapping
    (e.g. a ``nodes_by_id`` dict-like attribute keyed by ``UUID`` and
    valued by the node object) — this function reads and updates that
    existing key, it does not redesign the mapping structure. The
    document object may optionally expose a ``document_id`` attribute
    (a UUID or ``None``); when absent it is treated as ``None`` (the
    implicit-current-document / local form per {p080}).

    Validation, performed before any mutation:
      * ``new_node_id`` must be a syntactically valid UUID4.
      * ``new_node_id`` must not already be present as a key in the
        document's ``nodes_by_id`` mapping (no collisions).
      * ``old_node_id`` must currently be present as a key in that
        mapping (nothing to replace otherwise).

    On any validation failure, ``NodeIdentityError`` is raised and the
    document's mapping is left completely unchanged (no partial
    mutation).

    On success, per {p013}/{p109}, the following happen atomically (as
    seen by any caller — no intermediate state is observable through the
    mapping):
      * the node object's own ``node_id`` field is updated to
        ``new_node_id`` (if the node exposes such an attribute);
      * the mapping's ``old_node_id`` key is removed and a
        ``new_node_id`` key is inserted pointing at the same node
        object;
      * if the node (or its mapping entry) exposes a per-entry
        ``generation`` counter, it is incremented by one, per {p084};
      * the node's ``short_id`` (if present) is left completely
        untouched, per {p097} — replace_node_id must never reassign or
        clear it.

    Returns an ``AddressRemap`` whose ``old`` and ``new`` addresses share
    the document's ``document_id`` and carry ``old_node_id`` /
    ``new_node_id`` respectively.
    """

    nodes_by_id = getattr(document, "nodes_by_id", None)
    if nodes_by_id is None:
        raise NodeIdentityError(
            "document does not expose a 'nodes_by_id' internal id mapping"
        )

    validated_new_id = _validate_uuid4(new_node_id, what="new_node_id")

    if old_node_id not in nodes_by_id:
        raise NodeIdentityError(
            f"old_node_id {old_node_id!r} is not present in the document's "
            "id mapping"
        )

    if validated_new_id in nodes_by_id:
        raise NodeIdentityError(
            f"new_node_id {validated_new_id!r} already present in the "
            "document's id mapping (collision)"
        )

    # All preconditions verified; perform the update atomically. Nothing
    # above this point has mutated the document.
    node = nodes_by_id[old_node_id]

    if hasattr(node, "node_id"):
        try:
            node.node_id = validated_new_id
        except AttributeError:
            # Node forbids attribute assignment (e.g. frozen type); the
            # mapping key swap below is still the authoritative update.
            pass

    if hasattr(node, "generation"):
        try:
            node.generation = node.generation + 1
        except (AttributeError, TypeError):
            pass

    del nodes_by_id[old_node_id]
    nodes_by_id[validated_new_id] = node

    document_id = getattr(document, "document_id", None)
    return AddressRemap(
        old=NodeAddress(document_id=document_id, node_id=old_node_id),
        new=NodeAddress(document_id=document_id, node_id=validated_new_id),
    )
