"""Safe declarative encoder/decoder for the versioned tree file (C-017).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the *bytes* side of the tree file whose data model is owned by the
sibling :mod:`tree_engine.storage.schema`; nothing declared there is redefined
here. This module adds three things, per {p086}/{p100}: a mapping between a
live common-model ``Document`` and the canonical payload body preserving
``node_id`` (UUID4), ``short_id`` (positive int rendered 0x-prefixed hex per
{p097}), ``extended_type``, ``buffer_range`` and ``references``
(``NodeAddress``) exactly; a deterministic canonicalization
(:func:`canonical_bytes`) pinned by :data:`CODEC_VERSION`, over which
``tree_payload_sha256`` is computed -- covering the payload section only, so
the service ``CHECKSUMS`` section and the checksum field itself are excluded by
construction; and the safe load path, bytes -> UTF-8 -> :func:`json.loads` ->
plain dict lookups and ``str``/``int``/``bool``/``float``/``UUID`` coercions,
with no ``eval``, ``exec``, ``pickle``, ``marshal``, dynamic import or any
other object-loading mechanism. The short_id map is never regenerated: a
caller-supplied ``ShortIdMap`` is carried verbatim and :func:`short_id_map_for`
reuses the values the document's own nodes carry. Non-goals: no file I/O, and
no ``source_sha256`` comparison -- per {p086} a storage-lifecycle concern; the
value is only carried in the envelope.
Source-of-truth labels: {p085}, {p086}, {p087}, {p092}, {p097}, {p100}.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.nodes import Document, Node, NodeKind, walk
from tree_engine.core.short_id import ShortIdError, ShortIdMap, from_hex, to_hex
from tree_engine.exceptions import ChecksumMismatch, TreePayloadInvalid, exception_for_code
from tree_engine.storage.schema import (
    CURRENT_SCHEMA_VERSION, ChecksumsSection, TreeFile, TreeFileEnvelope,
    TreeFilePayload, TreeFileSchemaError,
)

__all__ = [
    "CODEC_VERSION", "DEFAULT_CORE_CONTRACT_VERSION", "UNSPECIFIED_VERSION",
    "NO_SOURCE_SHA256", "DecodedTreeFile", "canonical_bytes", "tree_payload_sha256",
    "short_id_map_for", "encode", "decode", "decode_document"]

#: Pins the tag vocabulary below and the JSON dialect of :func:`canonical_bytes`,
#: hence the exact bytes ``tree_payload_sha256`` covers ({p086}/{p100}).
CODEC_VERSION = "1"

#: Default envelope ``core_contract_version``: the core publishes no constant of
#: its own yet; this matches the ``contract_version`` the shipped plugins declare.
DEFAULT_CORE_CONTRACT_VERSION = "1.0.0"

#: Placeholder for a plugin version the caller did not supply; the schema
#: requires a non-empty string, and inventing a number would lie.
UNSPECIFIED_VERSION = "unspecified"

#: ``source_sha256`` placeholder (sha256 of empty content). Never compared here:
#: per {p086} that is the lifecycle layer's job, and it overwrites this field.
NO_SOURCE_SHA256 = hashlib.sha256(b"").hexdigest()

_NULL, _BOOL, _INT, _FLOAT, _STR, _BYTES, _NODE, _NODES = (
    "null", "bool", "int", "float", "str", "bytes", "node", "nodes")
_SCALARS: Mapping[str, Any] = {_BOOL: bool, _INT: int, _FLOAT: (int, float), _STR: str, _BYTES: str}

@dataclass(frozen=True)
class DecodedTreeFile:
    """Everything :func:`decode` recovers from a tree file's bytes."""

    document: Document
    short_id_map: ShortIdMap
    envelope: TreeFileEnvelope
    checksums: ChecksumsSection

def canonical_bytes(data: Mapping[str, Any]) -> bytes:
    """Render ``data`` to canonical UTF-8 JSON -- sorted keys, fixed separators,
    non-finite floats rejected -- so equal data always yields equal bytes."""

    try:
        text = json.dumps(
            data, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TreePayloadInvalid(f"payload is not canonically serializable: {exc}") from exc
    return text.encode("utf-8")

def tree_payload_sha256(payload: TreeFilePayload) -> str:
    """Hash the canonical bytes of the payload section only, per {p086}."""

    return hashlib.sha256(canonical_bytes(payload.to_dict())).hexdigest()

def _schema(call: Callable[..., Any], *args: Any) -> Any:
    """Map a schema constructor's ``TreeFileSchemaError`` onto the public
    exception class for the ``ErrorCode`` it already carries."""

    try:
        return call(*args)
    except TreeFileSchemaError as exc:
        raise exception_for_code(exc.code)(str(exc)) from exc

def _as_uuid4(value: Any, label: str) -> UUID:
    candidate = value if isinstance(value, UUID) else None
    if candidate is None and isinstance(value, str):
        try:
            candidate = UUID(value)
        except ValueError:
            candidate = None
    if candidate is None or candidate.version != 4:
        raise TreePayloadInvalid(f"{label} must be a UUID4, got {value!r}")
    return candidate

def _encode_short_id(value: Any) -> str:
    try:
        return to_hex(value)
    except ValueError as exc:
        raise TreePayloadInvalid(f"short_id must be a positive integer: {value!r}") from exc

def _decode_short_id(value: Any) -> int:
    try:
        return from_hex(value)
    except ShortIdError as exc:
        raise TreePayloadInvalid(f"short_id hex is malformed: {value!r}") from exc

def _bounds(value: Any) -> Optional[List[int]]:
    """Validate a ``buffer_range`` int pair, normalized to a plain list."""
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise TreePayloadInvalid(f"buffer_range must be a (start, end) pair, got {value!r}")
    if any(isinstance(bound, bool) or not isinstance(bound, int) for bound in value):
        raise TreePayloadInvalid(f"buffer_range bounds must be ints, got {value!r}")
    return [value[0], value[1]]

def _ext_type(value: Any) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise TreePayloadInvalid(f"extended_type must be a str or null, got {value!r}")
    return value

def _encode_address(address: Any) -> Dict[str, Any]:
    if not isinstance(address, NodeAddress):
        raise TreePayloadInvalid(f"reference must be a NodeAddress, got {type(address).__name__}")
    doc_id = address.document_id
    return {"node_id": str(_as_uuid4(address.node_id, "reference node_id")),
            "document_id": None if doc_id is None
            else str(_as_uuid4(doc_id, "reference document_id"))}

def _decode_address(data: Any) -> NodeAddress:
    if not isinstance(data, dict):
        raise TreePayloadInvalid(f"reference must be an object, got {type(data).__name__}")
    doc_id = data.get("document_id")
    return NodeAddress(node_id=_as_uuid4(data.get("node_id"), "reference node_id"),
                       document_id=None if doc_id is None
                       else _as_uuid4(doc_id, "reference document_id"))

def _encode_value(name: str, value: Any, memo: Dict[int, int]) -> List[Any]:
    """Encode a ``Node.fields`` value as a ``[tag, payload]`` pair over the
    ``FieldValue`` union; ``bool`` precedes ``int``, being its subclass."""

    if value is None:
        return [_NULL, None]
    if isinstance(value, Node):
        return [_NODE, _encode_node(value, memo)]
    if isinstance(value, (tuple, list)):
        return [_NODES, [_encode_node(item, memo) for item in value]]
    if isinstance(value, bytes):
        return [_BYTES, base64.b64encode(value).decode("ascii")]
    for kind, tag in ((bool, _BOOL), (int, _INT), (float, _FLOAT), (str, _STR)):
        if isinstance(value, kind):
            return [tag, kind(value)]
    raise TreePayloadInvalid(f"field {name!r} has unsupported value type {type(value).__name__}")

def _decode_value(name: str, entry: Any, memo: Dict[int, Node]) -> Any:
    """Rebuild one ``Node.fields`` value from its ``[tag, payload]`` pair."""

    if not isinstance(entry, list) or len(entry) != 2:
        raise TreePayloadInvalid(f"field {name!r} must encode as a [tag, value] pair")
    tag, raw = entry
    if tag == _NODE:
        return _decode_node(raw, memo)
    if tag == _NODES:
        if not isinstance(raw, list):
            raise TreePayloadInvalid(f"field {name!r} tagged nodes holds {type(raw).__name__}")
        return tuple(_decode_node(item, memo) for item in raw)
    if tag == _NULL:
        if raw is not None:
            raise TreePayloadInvalid(f"field {name!r} tagged null holds {raw!r}")
        return None
    expected = _SCALARS.get(tag)
    if expected is None:
        raise TreePayloadInvalid(f"field {name!r} carries unknown value tag {tag!r}")
    if not isinstance(raw, expected) or (tag != _BOOL and isinstance(raw, bool)):
        raise TreePayloadInvalid(f"field {name!r} tagged {tag} holds {raw!r}")
    if tag == _FLOAT:
        return float(raw)
    if tag == _BYTES:
        try:
            return base64.b64decode(raw.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise TreePayloadInvalid(f"field {name!r} has malformed base64: {exc}") from exc
    return raw

def _encode_node(node: Any, memo: Dict[int, int]) -> Dict[str, Any]:
    """Encode a ``Node`` subtree into plain JSON-native data. ``fields`` and
    ``children`` routinely hold the SAME node objects, so each is emitted once
    under an ``"id"`` and every later occurrence becomes a ``{"ref": id}``
    back-pointer -- without which a shared subtree would be duplicated once per
    path and blow up exponentially with depth. ``fields`` is an ordered
    ``[name, value]`` list so field order survives canonical key sorting."""

    if not isinstance(node, Node):
        raise TreePayloadInvalid(f"expected a Node, got {type(node).__name__}")
    if id(node) in memo:
        return {"ref": memo[id(node)]}
    memo[id(node)] = index = len(memo)
    return {
        "id": index, "kind": str(node.kind), "extended_type": _ext_type(node.extended_type),
        "node_id": None if node.node_id is None else str(_as_uuid4(node.node_id, "node_id")),
        "short_id": None if node.short_id is None else _encode_short_id(node.short_id),
        "buffer_range": _bounds(node.buffer_range),
        "references": [_encode_address(item) for item in node.references],
        "fields": [[name, _encode_value(name, val, memo)] for name, val in node.fields.items()],
        "children": [_encode_node(child, memo) for child in node.children]}

def _decode_node(data: Any, memo: Dict[int, Node]) -> Node:
    """Rebuild a ``Node``, resolving ``{"ref": id}`` back-pointers through ``memo``
    so shared subtrees stay shared, shape-checking every value, then building the
    frozen dataclass directly -- the documented path for a validated node."""

    if not isinstance(data, dict):
        raise TreePayloadInvalid(f"node must be an object, got {type(data).__name__}")
    if "ref" in data:
        shared = memo.get(data["ref"]) if isinstance(data["ref"], int) else None
        if shared is None:
            raise TreePayloadInvalid(f"node ref {data['ref']!r} precedes its definition")
        return shared
    kind = data.get("kind")
    if not isinstance(kind, str) or not kind:
        raise TreePayloadInvalid(f"node kind must be a non-empty str, got {kind!r}")
    for key in ("fields", "children", "references"):
        if not isinstance(data.get(key), list):
            raise TreePayloadInvalid(
                f"node {key} must be a list, got {type(data.get(key)).__name__}")
    fields: Dict[str, Any] = {}
    for entry in data["fields"]:
        if (not isinstance(entry, list) or len(entry) != 2
                or not isinstance(entry[0], str) or not entry[0]):
            raise TreePayloadInvalid(f"node field must be a [name, value] pair, got {entry!r}")
        fields[entry[0]] = _decode_value(entry[0], entry[1], memo)
    bounds = _bounds(data.get("buffer_range"))
    node_id, short_id, index = data.get("node_id"), data.get("short_id"), data.get("id")
    node = Node(
        kind=NodeKind(kind), fields=MappingProxyType(fields),
        children=tuple(_decode_node(child, memo) for child in data["children"]),
        node_id=None if node_id is None else _as_uuid4(node_id, "node_id"),
        short_id=None if short_id is None else _decode_short_id(short_id),
        extended_type=_ext_type(data.get("extended_type")),
        buffer_range=None if bounds is None else (bounds[0], bounds[1]),
        references=tuple(_decode_address(item) for item in data["references"]))
    if isinstance(index, bool) or not isinstance(index, int) or index in memo:
        raise TreePayloadInvalid(f"node id {index!r} is missing, malformed, or duplicated")
    memo[index] = node
    return node

def short_id_map_for(document: Document) -> ShortIdMap:
    """Build the payload's short_id map from the document's own nodes, reusing the
    exact ``short_id`` each carries -- never allocating a fresh one ({p097})."""

    incoming: Dict[UUID, int] = {}
    for node in walk(document.root):
        if node.node_id is None or node.short_id is None:
            continue
        node_id = _as_uuid4(node.node_id, "node_id")
        if node_id in incoming:
            raise TreePayloadInvalid(f"duplicate node_id in the tree: {node_id}")
        if isinstance(node.short_id, bool) or not isinstance(node.short_id, int) or node.short_id < 1:
            raise TreePayloadInvalid(f"short_id must be a positive integer: {node.short_id!r}")
        incoming[node_id] = node.short_id
    result = ShortIdMap(next_short_id=1)
    try:
        result.merge_insert(incoming)
    except ShortIdError as exc:
        raise TreePayloadInvalid(f"short_id map cannot hold the document's ids: {exc}") from exc
    return result

def _check_identity_consistency(root: Node, short_id_map: ShortIdMap) -> None:
    """Reject a tree whose node ids duplicate or contradict the map ({p092})."""

    seen = set()
    for node in walk(root):
        if node.node_id is None:
            continue
        node_id = _as_uuid4(node.node_id, "node_id")
        if node_id in seen:
            raise TreePayloadInvalid(f"duplicate node_id in the tree: {node_id}")
        seen.add(node_id)
        mapped = short_id_map.get_short_id(node_id)
        if mapped is not None and node.short_id is not None and mapped != node.short_id:
            raise TreePayloadInvalid(
                f"short_id map says {mapped} for node {node_id}, tree says {node.short_id!r}")

def _derive_document_id(payload_dict: Mapping[str, Any]) -> UUID:
    """Derive a stable version-4 document id from the canonical payload,
    used only when neither caller nor document supplies one; being a pure
    function of those bytes it keeps :func:`encode` deterministic."""

    digest = bytearray(hashlib.sha256(canonical_bytes(payload_dict)).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(digest))

def encode(
    document: Document, *,
    short_id_map: Optional[ShortIdMap] = None, document_id: Optional[Any] = None,
    document_version: int = 0, source_sha256: Optional[str] = None,
    core_contract_version: str = DEFAULT_CORE_CONTRACT_VERSION,
    plugin_id: Optional[str] = None, plugin_version: str = UNSPECIFIED_VERSION,
    plugin_contract_version: str = UNSPECIFIED_VERSION, encoding: str = "utf-8",
    newline: str = "\n", trailing_newline: bool = True,
    format_metadata: Optional[Mapping[str, Any]] = None,
) -> bytes:
    """Serialize ``document`` to the canonical tree-file bytes. Deterministic:
    the same document and arguments always produce the same bytes.
    ``tree_payload_sha256`` covers the payload's canonical bytes, excluding the
    ``CHECKSUMS`` section and the checksum field itself ({p086});
    ``source_sha256`` is carried, never compared. Raises ``TreePayloadInvalid``
    for a tree the codec cannot express, or ``TreeSchemaUnsupported`` if the
    schema gate rejects the envelope."""

    if not isinstance(document, Document):
        raise TreePayloadInvalid(f"document must be a Document, got {type(document).__name__}")
    resolved_map = short_id_map if short_id_map is not None else short_id_map_for(document)
    _check_identity_consistency(document.root, resolved_map)
    payload = TreeFilePayload(short_id_map=resolved_map,
        tree={"codec_version": CODEC_VERSION, "root": _encode_node(document.root, {})})
    payload_dict = payload.to_dict()
    given = document_id if document_id is not None else document.document_id
    envelope_id = (_as_uuid4(given, "document_id") if given is not None
                   else _derive_document_id(payload_dict))
    envelope = _schema(TreeFileEnvelope.from_dict, {
        "schema_version": CURRENT_SCHEMA_VERSION, "document_id": str(envelope_id),
        "core_contract_version": core_contract_version, "document_version": document_version,
        "next_short_id": resolved_map.snapshot().next_short_id,
        "representation_format_id": document.representation_format_id,
        "source_format_id": document.source_format_id, "encoding": encoding,
        "newline": newline, "trailing_newline": trailing_newline,
        "plugin_id": plugin_id if plugin_id is not None else document.representation_format_id,
        "plugin_version": plugin_version, "plugin_contract_version": plugin_contract_version,
        "format_metadata": dict(format_metadata or {}),
    })
    checksums = _schema(ChecksumsSection.from_dict, {
        "source_sha256": source_sha256 or NO_SOURCE_SHA256,
        "tree_payload_sha256": hashlib.sha256(canonical_bytes(payload_dict)).hexdigest()})
    return canonical_bytes(
        TreeFile(envelope=envelope, payload=payload, checksums=checksums).to_dict())

def decode(data: bytes) -> DecodedTreeFile:
    """Parse tree-file bytes back into document, map, envelope, checksums.
    Gate order: JSON shape, then the schema module's version gate and explicit
    minor migrations (an unknown major raises ``TreeSchemaUnsupported`` there,
    per {p087}/{p100}), then the ``tree_payload_sha256`` recomputation, then the
    tree body. Anything structurally unexpected raises ``TreePayloadInvalid``; a
    checksum discrepancy raises ``ChecksumMismatch``. Nothing executes data."""

    data = bytes(data) if isinstance(data, (bytearray, memoryview)) else data
    if not isinstance(data, bytes):
        raise TreePayloadInvalid(f"tree file must be bytes, got {type(data).__name__}")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TreePayloadInvalid(f"tree file is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise TreePayloadInvalid(f"tree file must be a JSON object, got {type(raw).__name__}")
    tree_file = _schema(TreeFile.from_dict, raw)
    recomputed = tree_payload_sha256(tree_file.payload)
    if recomputed != tree_file.checksums.tree_payload_sha256:
        raise ChecksumMismatch("tree_payload_sha256 does not match the canonical payload bytes",
            expected=tree_file.checksums.tree_payload_sha256, recomputed=recomputed)
    body = tree_file.payload.tree
    if body.get("codec_version") != CODEC_VERSION:
        raise TreePayloadInvalid(f"payload codec_version {body.get('codec_version')!r} is not 1")
    root = _decode_node(body.get("root"), {})
    short_id_map, envelope = tree_file.payload.short_id_map, tree_file.envelope
    _check_identity_consistency(root, short_id_map)
    stored_next = short_id_map.snapshot().next_short_id
    if stored_next != envelope.next_short_id:
        raise TreePayloadInvalid(f"envelope next_short_id != the map's {stored_next}")
    document = Document(root=root, source_format_id=envelope.source_format_id,
                        representation_format_id=envelope.representation_format_id)
    document.document_id = envelope.document_id
    return DecodedTreeFile(document=document, short_id_map=short_id_map,
                           envelope=envelope, checksums=tree_file.checksums)

def decode_document(data: bytes) -> Document:
    """Convenience wrapper returning only the document of :func:`decode`."""

    return decode(data).document
