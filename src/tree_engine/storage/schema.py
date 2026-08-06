"""Versioned tree-file envelope, payload layout, and schema version gate.

Scope (concept C-017, TreeSerializationSchema, narrowed to this atomic
step's target ``src/tree_engine/storage/schema.py``): the data model and
schema version gate for the persisted tree file, per {p085}/{p100}.

A tree file carries three sections: an *envelope* of schema/contract
versions, document identity/version, the short_id allocator state,
format ids, encoding/newline metadata, and plugin identity
(:class:`TreeFileEnvelope`); a *payload* of the canonical tree body and
the short_id-to-UUID4 map, the latter reusing
:class:`tree_engine.core.short_id.ShortIdMap` as-is
(:class:`TreeFilePayload`); and a service *CHECKSUMS* section holding
``source_sha256``/``tree_payload_sha256`` (:class:`ChecksumsSection`).
:class:`TreeFile` composes the three. Per {p087}/{p100} this module also
implements the codec's version gate: an unknown major ``schema_version``
is rejected with ``TREE_SCHEMA_UNSUPPORTED``; compatible minor versions
migrate through the explicit registry :data:`MINOR_MIGRATIONS`.

Non-goals, per {p086}/{p092} and this step's acceptance criteria: no file
I/O, no bytes/JSON parsing, no canonical byte-serialization, and no
checksum computation -- those, plus the pinned codec version fixing
payload canonicalization per {p100}, belong to the sibling codec module.
Deep structural validation of the tree body (UUID4 uniqueness,
parent/child, reference cycles, ...) is the core's job per {p092}; this
module validates only *shape*, rejecting a mismatch with
``TREE_PAYLOAD_INVALID``.

Deserialization here never executes code and never uses pickle-like
object loading: every conversion below is a plain dict lookup plus a
``str``/``int``/``bool``/``uuid.UUID`` coercion -- no ``eval``, ``exec``,
``pickle``, ``marshal``, or dynamic import appears in this file.

Source-of-truth labels honored here: {p085}, {p086}, {p087}, {p092}, {p100}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Tuple
from uuid import UUID

from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode

__all__ = [
    "TreeFileSchemaError",
    "CURRENT_SCHEMA_MAJOR",
    "CURRENT_SCHEMA_MINOR",
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_MAJOR_VERSIONS",
    "MinorMigration",
    "MINOR_MIGRATIONS",
    "parse_schema_version",
    "check_schema_major_supported",
    "apply_minor_migrations",
    "TreeFileEnvelope",
    "TreeFilePayload",
    "ChecksumsSection",
    "TreeFile",
]

# ---- Version gate ---------------------------------------------------------

CURRENT_SCHEMA_MAJOR = 1
CURRENT_SCHEMA_MINOR = 0
CURRENT_SCHEMA_VERSION = f"{CURRENT_SCHEMA_MAJOR}.{CURRENT_SCHEMA_MINOR}"

#: Major ``schema_version`` values readable at all; others are rejected
#: with ``TREE_SCHEMA_UNSUPPORTED`` before any migration, per {p087}.
SUPPORTED_SCHEMA_MAJOR_VERSIONS = frozenset({1})


class TreeFileSchemaError(Exception):
    """Invalid tree-file envelope/payload/checksums dict.

    Carries the originating ``ErrorCode`` as ``self.code``, mirroring
    ``core.nodes.NodeSchemaError``: ``TREE_SCHEMA_UNSUPPORTED`` (unknown
    major schema version) or ``TREE_PAYLOAD_INVALID`` (other mismatch).
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code


def parse_schema_version(value: Any) -> Tuple[int, int]:
    """Parse ``"MAJOR.MINOR"`` into an ``(major, minor)`` int pair.

    Raises ``TreeFileSchemaError`` (``TREE_PAYLOAD_INVALID``) if not a
    str, or not exactly two dot-separated non-negative integers.
    """

    if not isinstance(value, str):
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"schema_version must be a str, got {value!r}")
    parts = value.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise TreeFileSchemaError(
            ErrorCode.TREE_PAYLOAD_INVALID,
            f"schema_version must be 'MAJOR.MINOR' with non-negative integers, got {value!r}",
        )
    return int(parts[0]), int(parts[1])


def check_schema_major_supported(major: int) -> None:
    """Raise ``TREE_SCHEMA_UNSUPPORTED`` if ``major`` is unreadable ({p087})."""

    if major not in SUPPORTED_SCHEMA_MAJOR_VERSIONS:
        raise TreeFileSchemaError(
            ErrorCode.TREE_SCHEMA_UNSUPPORTED,
            f"unsupported major schema_version: {major} (supported: {sorted(SUPPORTED_SCHEMA_MAJOR_VERSIONS)})",
        )


#: Upgrades an envelope dict declaring ``"{major}.{minor}"`` to
#: ``"{major}.{minor + 1}"``, returning a new dict (input never mutated).
MinorMigration = Callable[[Dict[str, Any]], Dict[str, Any]]

#: Explicit registry of minor-version migrations, keyed by the
#: ``(major, minor)`` an envelope declares. Empty today: ``1.0`` is the
#: only minor version shipped under major version 1 so far; a future
#: compatible minor bump adds its migration here under its own key.
MINOR_MIGRATIONS: Mapping[Tuple[int, int], MinorMigration] = {}


def apply_minor_migrations(
    data: Mapping[str, Any],
    migrations: Mapping[Tuple[int, int], MinorMigration] = MINOR_MIGRATIONS,
) -> Dict[str, Any]:
    """Migrate an envelope dict through explicit, testable minor steps.

    Rejects an unsupported major version, then repeatedly looks up
    ``(major, minor)`` in ``migrations`` and applies the matching step
    until none is registered; each result is re-validated the same way.
    Raises ``TreeFileSchemaError`` (``TREE_PAYLOAD_INVALID``) on a cycle.
    Returns a new dict; ``data`` is never mutated.
    """

    major, minor = parse_schema_version(data.get("schema_version"))
    check_schema_major_supported(major)
    migrated: Dict[str, Any] = dict(data)
    seen = {(major, minor)}
    while (major, minor) in migrations:
        migrated = migrations[(major, minor)](migrated)
        major, minor = parse_schema_version(migrated.get("schema_version"))
        check_schema_major_supported(major)
        if (major, minor) in seen:
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID,
                f"minor-version migration cycle detected at schema_version {major}.{minor}",
            )
        seen.add((major, minor))
    migrated["schema_version"] = f"{major}.{minor}"
    return migrated


# ---- Shape-validation helpers (no parsing, no I/O) -------------------------

def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be a non-empty str, got {value!r}")
    return value

def _require_int(data: Mapping[str, Any], key: str, *, minimum: int) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be an int >= {minimum}, got {value!r}")
    return value

def _require_bool(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be a bool, got {value!r}")
    return value

def _require_uuid4(data: Mapping[str, Any], key: str) -> UUID:
    value = data.get(key)
    candidate = value if isinstance(value, UUID) else None
    if candidate is None:
        try:
            candidate = UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            candidate = None
    if candidate is None or candidate.version != 4:
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be a UUID4, got {value!r}")
    return candidate

def _require_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise TreeFileSchemaError(ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be a mapping, got {type(value).__name__}")
    return value

_SHA256_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

def _require_sha256_hex(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _SHA256_HEX_DIGITS:
        raise TreeFileSchemaError(
            ErrorCode.TREE_PAYLOAD_INVALID, f"{key} must be a 64-hex-digit sha256 string, got {value!r}"
        )
    return value.lower()


# ---- Envelope ---------------------------------------------------------------

@dataclass(frozen=True)
class TreeFileEnvelope:
    """The tree file's envelope section, per {p085} and {p100}.

    ``format_metadata`` is an open slot for other format metadata beyond
    the named fields ({p100}); defaults to empty, round-trips verbatim.
    """

    schema_version: str
    core_contract_version: str
    document_id: UUID
    document_version: int
    next_short_id: int
    representation_format_id: str
    source_format_id: str
    encoding: str
    newline: str
    trailing_newline: bool
    plugin_id: str
    plugin_version: str
    plugin_contract_version: str
    format_metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TreeFileEnvelope":
        """Validate and construct an envelope from a plain dict.

        Applies the version gate first (:func:`apply_minor_migrations`),
        then validates every other field. Raises ``TreeFileSchemaError``:
        ``TREE_SCHEMA_UNSUPPORTED`` for an unknown major version,
        ``TREE_PAYLOAD_INVALID`` for anything else malformed.
        """

        if not isinstance(data, Mapping):
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID, f"envelope must be a mapping, got {type(data).__name__}"
            )
        migrated = apply_minor_migrations(data)
        raw_metadata = migrated.get("format_metadata", {})
        if not isinstance(raw_metadata, Mapping):
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID,
                f"format_metadata must be a mapping, got {type(raw_metadata).__name__}",
            )
        return cls(
            schema_version=migrated["schema_version"],
            core_contract_version=_require_str(migrated, "core_contract_version"),
            document_id=_require_uuid4(migrated, "document_id"),
            document_version=_require_int(migrated, "document_version", minimum=0),
            next_short_id=_require_int(migrated, "next_short_id", minimum=1),
            representation_format_id=_require_str(migrated, "representation_format_id"),
            source_format_id=_require_str(migrated, "source_format_id"),
            encoding=_require_str(migrated, "encoding"),
            newline=_require_str(migrated, "newline"),
            trailing_newline=_require_bool(migrated, "trailing_newline"),
            plugin_id=_require_str(migrated, "plugin_id"),
            plugin_version=_require_str(migrated, "plugin_version"),
            plugin_contract_version=_require_str(migrated, "plugin_contract_version"),
            format_metadata=MappingProxyType(dict(raw_metadata)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Render to a dict; key order is fixed here, not by any input
        dict's ordering, so equal envelopes always encode equal."""

        return {
            "schema_version": self.schema_version,
            "core_contract_version": self.core_contract_version,
            "document_id": str(self.document_id),
            "document_version": self.document_version,
            "next_short_id": self.next_short_id,
            "representation_format_id": self.representation_format_id,
            "source_format_id": self.source_format_id,
            "encoding": self.encoding,
            "newline": self.newline,
            "trailing_newline": self.trailing_newline,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "plugin_contract_version": self.plugin_contract_version,
            "format_metadata": dict(self.format_metadata),
        }


# ---- Payload (tree body + short_id map) --------------------------------------

@dataclass(frozen=True)
class TreeFilePayload:
    """The tree file's payload section: tree body plus short_id map.

    ``tree`` is the opaque canonical tree body as a plain mapping; its
    deep shape is owned by the core/codec, not here, per {p092} -- only
    presence is checked. ``short_id_map`` reuses
    :class:`tree_engine.core.short_id.ShortIdMap` as-is.
    """

    tree: Mapping[str, Any]
    short_id_map: ShortIdMap

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TreeFilePayload":
        if not isinstance(data, Mapping):
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID, f"payload must be a mapping, got {type(data).__name__}"
            )
        tree = _require_mapping(data, "tree")
        short_id_map_data = _require_mapping(data, "short_id_map")
        try:
            short_id_map = ShortIdMap.from_dict(dict(short_id_map_data))
        except (KeyError, ValueError, TypeError) as exc:
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID, f"payload.short_id_map is malformed: {exc}"
            ) from exc
        return cls(tree=dict(tree), short_id_map=short_id_map)

    def to_dict(self) -> Dict[str, Any]:
        return {"tree": dict(self.tree), "short_id_map": self.short_id_map.to_dict()}


# ---- Checksums ----------------------------------------------------------------

@dataclass(frozen=True)
class ChecksumsSection:
    """The tree file's service CHECKSUMS section, per {p085}.

    ``source_sha256`` covers the exact source bytes; ``tree_payload_sha256``
    covers the payload's canonical serialization. Neither is computed
    here -- only checked as a well-formed 64-hex-digit string; computing
    them from real bytes is the codec's job, per {p086}.
    """

    source_sha256: str
    tree_payload_sha256: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChecksumsSection":
        if not isinstance(data, Mapping):
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID, f"checksums must be a mapping, got {type(data).__name__}"
            )
        return cls(
            source_sha256=_require_sha256_hex(data, "source_sha256"),
            tree_payload_sha256=_require_sha256_hex(data, "tree_payload_sha256"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "source_sha256": self.source_sha256,
            "tree_payload_sha256": self.tree_payload_sha256,
        }


# ---- Whole tree file ------------------------------------------------------

@dataclass(frozen=True)
class TreeFile:
    """The whole tree-file data model: envelope + payload + checksums."""

    envelope: TreeFileEnvelope
    payload: TreeFilePayload
    checksums: ChecksumsSection

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TreeFile":
        """Validate and construct a whole tree file from a plain dict.

        ``data`` is assumed already parsed from bytes by the codec (this
        module parses nothing of its own); it must map the three
        top-level section names to their own mappings. Raises
        ``TREE_SCHEMA_UNSUPPORTED`` for an unknown major schema version,
        ``TREE_PAYLOAD_INVALID`` for any other malformed field.
        """

        if not isinstance(data, Mapping):
            raise TreeFileSchemaError(
                ErrorCode.TREE_PAYLOAD_INVALID, f"tree file must be a mapping, got {type(data).__name__}"
            )
        envelope = TreeFileEnvelope.from_dict(_require_mapping(data, "envelope"))
        payload = TreeFilePayload.from_dict(_require_mapping(data, "payload"))
        checksums = ChecksumsSection.from_dict(_require_mapping(data, "checksums"))
        return cls(envelope=envelope, payload=payload, checksums=checksums)

    def to_dict(self) -> Dict[str, Any]:
        """Render to a dict; section/field order is fixed here and by the
        section-level ``to_dict`` methods, not by any input dict's key
        ordering, so equal data always renders to equal output."""

        return {
            "envelope": self.envelope.to_dict(),
            "payload": self.payload.to_dict(),
            "checksums": self.checksums.to_dict(),
        }
