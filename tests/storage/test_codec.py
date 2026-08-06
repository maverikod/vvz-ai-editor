"""Tests for the tree-file codec (C-017): encode/decode, checksums, refs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.codec`` -- the bytes side of the tree file.
Every document used here is a real one, parsed by a real format plugin from
an actual repository file (a small module of ``tree_engine`` itself through
:class:`PythonFormatPlugin`, and a small JSON file through
:class:`JsonFormatPlugin`, so the codec is not pinned to one plugin's node
shape); no hand-built toy tree is used where a real one already suffices.

The design point pinned hardest here: ``Node.fields`` and ``Node.children``
routinely hold the exact same node objects (every plugin built on the
common model derives ``children`` from the Node-valued entries of
``fields``), so the encoder emits a shared node once under an ``"id"`` and
every later occurrence as ``{"ref": id}``. Losing that dedup either
duplicates shared subtrees (the exponential blowup this format exists to
avoid) or fails to restore shared object identity on decode; both are
pinned explicitly below, not just implied by round-trip equality.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

from tree_engine.core.nodes import Node, walk
from tree_engine.exceptions import ChecksumMismatch, TreePayloadInvalid, TreeSchemaUnsupported
from tree_engine.plugins.json_format import JsonFormatPlugin
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.storage import codec as codec_module
from tree_engine.storage.codec import (
    CODEC_VERSION,
    canonical_bytes,
    decode,
    decode_document,
    encode,
    short_id_map_for,
    tree_payload_sha256,
)
from tree_engine.storage.schema import CURRENT_SCHEMA_VERSION, TreeFilePayload

REPO_ROOT = Path(__file__).resolve().parents[2]
# Small real files so the ~90x payload/source ratio stays cheap to encode.
PY_SOURCE_PATH = REPO_ROOT / "src" / "tree_engine" / "errors.py"
JSON_SOURCE_PATH = REPO_ROOT / "docs" / "projectid.example.json"


# ---- Fixtures: real documents, parsed once and reused ----------------------

@pytest.fixture(scope="module")
def py_source() -> bytes:
    return PY_SOURCE_PATH.read_bytes()


@pytest.fixture(scope="module")
def py_document(py_source: bytes):
    return PythonFormatPlugin().parse_document(py_source)


@pytest.fixture(scope="module")
def py_encoded(py_document, py_source: bytes) -> bytes:
    return encode(
        py_document, source_sha256=hashlib.sha256(py_source).hexdigest(),
        plugin_id="python", plugin_version="1.0.0", plugin_contract_version="1.0.0")


@pytest.fixture(scope="module")
def json_source() -> bytes:
    return JSON_SOURCE_PATH.read_bytes()


@pytest.fixture(scope="module")
def json_document(json_source: bytes):
    return JsonFormatPlugin().parse_document(json_source)


# ---- Structural helpers over the raw encoded payload / live tree -----------

def _iter_node_occurrences(entry: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Walk one encoded node's occurrences in decode order: itself, then --
    unless it is a ``{"ref": id}`` back-pointer -- its fields' node-tagged
    values, then its children. Mirrors ``codec._decode_node`` exactly."""

    yield entry
    if "ref" in entry:
        return
    for _, tagged in entry["fields"]:
        tag, payload = tagged
        if tag == "node":
            yield from _iter_node_occurrences(payload)
        elif tag == "nodes":
            for item in payload:
                yield from _iter_node_occurrences(item)
    for child in entry["children"]:
        yield from _iter_node_occurrences(child)


def _iter_live_node_occurrences(node: Node) -> Iterator[Node]:
    """Same traversal as :func:`_iter_node_occurrences`, over a live
    ``Node`` tree instead of its encoded form; no ref/id distinction
    exists here -- a shared subtree just appears twice by identity."""

    yield node
    for value in node.fields.values():
        if isinstance(value, Node):
            yield from _iter_live_node_occurrences(value)
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, Node):
                    yield from _iter_live_node_occurrences(item)
    for child in node.children:
        yield from _iter_live_node_occurrences(child)


def _resign(raw: Dict[str, Any]) -> None:
    """Recompute ``tree_payload_sha256`` for a mutated raw tree-file dict,
    the way a legitimate re-encode would -- used only to isolate a shape
    mutation from an (already separately pinned) checksum mutation."""

    payload = TreeFilePayload.from_dict(raw["payload"])
    raw["checksums"]["tree_payload_sha256"] = tree_payload_sha256(payload)


def _to_bytes(raw: Dict[str, Any]) -> bytes:
    return json.dumps(raw).encode("utf-8")


# ---- Round trip and determinism ---------------------------------------------

def test_encode_is_deterministic_for_identical_arguments(py_document, py_source) -> None:
    kwargs = dict(source_sha256=hashlib.sha256(py_source).hexdigest(), plugin_id="python")
    assert encode(py_document, **kwargs) == encode(py_document, **kwargs)


def test_decode_then_reencode_reproduces_original_bytes(py_encoded: bytes) -> None:
    """Round-trip determinism per the acceptance criteria: decoding and
    re-encoding with the envelope's own carried metadata reproduces the
    exact original bytes, not just an equivalent tree."""

    decoded = decode(py_encoded)
    reencoded = encode(
        decoded.document, short_id_map=decoded.short_id_map,
        document_id=decoded.envelope.document_id, document_version=decoded.envelope.document_version,
        core_contract_version=decoded.envelope.core_contract_version, encoding=decoded.envelope.encoding,
        newline=decoded.envelope.newline, trailing_newline=decoded.envelope.trailing_newline,
        plugin_id=decoded.envelope.plugin_id, plugin_version=decoded.envelope.plugin_version,
        plugin_contract_version=decoded.envelope.plugin_contract_version,
        format_metadata=decoded.envelope.format_metadata, source_sha256=decoded.checksums.source_sha256)
    assert reencoded == py_encoded


def test_json_plugin_document_round_trips(json_document) -> None:
    """A second, unrelated format plugin round-trips too -- the codec is
    not accidentally pinned to the Python plugin's node shape."""

    data = encode(json_document, plugin_id="json")
    decoded = decode(data)
    assert decoded.document.root.kind == json_document.root.kind
    assert decoded.envelope.representation_format_id == "json"
    live_count = sum(1 for _ in walk(json_document.root))
    decoded_count = sum(1 for _ in walk(decoded.document.root))
    assert decoded_count == live_count


def test_payload_tree_carries_codec_version(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    assert raw["payload"]["tree"]["codec_version"] == CODEC_VERSION == "1"


# ---- Checksums ---------------------------------------------------------------

def test_tree_payload_sha256_matches_recomputed_canonical_hash(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    payload = TreeFilePayload.from_dict(raw["payload"])
    expected = hashlib.sha256(canonical_bytes(payload.to_dict())).hexdigest()
    assert raw["checksums"]["tree_payload_sha256"] == expected == tree_payload_sha256(payload)


def test_tree_payload_sha256_stable_across_repeated_encodes(py_document, py_source) -> None:
    first = json.loads(encode(py_document, source_sha256="a" * 64).decode("utf-8"))
    second = json.loads(encode(py_document, source_sha256="a" * 64).decode("utf-8"))
    assert first["checksums"]["tree_payload_sha256"] == second["checksums"]["tree_payload_sha256"]


def test_source_sha256_does_not_affect_tree_payload_sha256(py_document) -> None:
    one = json.loads(encode(py_document, source_sha256="1" * 64).decode("utf-8"))
    other = json.loads(encode(py_document, source_sha256="2" * 64).decode("utf-8"))
    assert one["checksums"]["source_sha256"] != other["checksums"]["source_sha256"]
    assert one["checksums"]["tree_payload_sha256"] == other["checksums"]["tree_payload_sha256"]


def test_canonical_bytes_is_independent_of_input_key_order() -> None:
    forward = {"a": 1, "b": {"x": 1, "y": 2}}
    reversed_order = {"b": {"y": 2, "x": 1}, "a": 1}
    assert list(reversed_order.keys()) != list(forward.keys())
    assert canonical_bytes(forward) == canonical_bytes(reversed_order)


# ---- Shared-object ref/memo design (the key non-obvious behavior) ----------

def test_shared_field_and_children_nodes_are_deduplicated_via_ref(py_document, py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    occurrences = list(_iter_node_occurrences(raw["payload"]["tree"]["root"]))
    ids = [entry for entry in occurrences if "ref" not in entry]
    refs = [entry for entry in occurrences if "ref" in entry]
    live_unique = {id(node) for node in _iter_live_node_occurrences(py_document.root)}

    # There is real sharing in this document (every field-valued Node also
    # appears in its parent's ``children``), and each shared object is
    # emitted exactly once under "id" -- never duplicated in full.
    assert len(refs) > 0
    assert len(ids) == len(live_unique)
    assert len({entry["id"] for entry in ids}) == len(ids)


def test_decoded_document_restores_shared_node_object_identity(py_encoded: bytes) -> None:
    """Decoding must reconstruct the *same* Python object for every
    occurrence of a shared node, not a structurally-equal copy -- proven
    by identity (``id()``), which structural equality could not catch."""

    decoded = decode(py_encoded)
    occurrences = list(_iter_live_node_occurrences(decoded.document.root))
    assert len({id(node) for node in occurrences}) < len(occurrences)


def test_ref_to_undefined_id_rejected(py_encoded: bytes) -> None:
    """A ``{"ref": id}`` naming an id that was never (yet) defined --
    including one that simply does not exist -- is rejected instead of
    resolving to ``None`` or crashing with a bare ``KeyError``."""

    raw = json.loads(py_encoded.decode("utf-8"))
    root = raw["payload"]["tree"]["root"]
    ids, refs = 0, None
    for entry in _iter_node_occurrences(root):
        if "ref" in entry:
            refs = entry
        else:
            ids += 1
    assert refs is not None, "fixture document must contain real sharing"
    refs["ref"] = ids  # one past the highest id ever assigned: never defined
    _resign(raw)
    with pytest.raises(TreePayloadInvalid, match="precedes its definition"):
        decode(_to_bytes(raw))


# ---- Tamper detection ---------------------------------------------------------

def test_tampered_node_field_without_resign_raises_checksum_mismatch(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    raw["payload"]["tree"]["root"]["kind"] += "-tampered"  # no _resign(raw) call
    with pytest.raises(ChecksumMismatch):
        decode(_to_bytes(raw))


def test_resigned_but_shape_broken_node_raises_tree_payload_invalid(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    raw["payload"]["tree"]["root"]["kind"] = ""  # correctly re-signed, still an invalid node shape
    _resign(raw)
    with pytest.raises(TreePayloadInvalid, match="kind"):
        decode(_to_bytes(raw))


# ---- Schema version gate -----------------------------------------------------

def test_unknown_major_schema_version_rejected(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    assert raw["envelope"]["schema_version"] == CURRENT_SCHEMA_VERSION
    raw["envelope"]["schema_version"] = "999.0"  # gate runs before checksum recomputation
    with pytest.raises(TreeSchemaUnsupported):
        decode(_to_bytes(raw))


# ---- Malformed / corrupted bytes --------------------------------------------

def test_truncated_bytes_rejected(py_encoded: bytes) -> None:
    with pytest.raises(TreePayloadInvalid):
        decode(py_encoded[: len(py_encoded) // 2])


def test_non_utf8_bytes_rejected() -> None:
    with pytest.raises(TreePayloadInvalid):
        decode(b"\xff\xfe\xfd\xfc not utf-8 and not json")


def test_top_level_json_array_rejected() -> None:
    with pytest.raises(TreePayloadInvalid):
        decode(json.dumps([1, 2, 3]).encode("utf-8"))


def test_non_bytes_input_rejected() -> None:
    with pytest.raises(TreePayloadInvalid):
        decode("not-bytes-a-str")  # type: ignore[arg-type]


def test_bytearray_and_memoryview_input_accepted(py_encoded: bytes) -> None:
    assert decode(bytearray(py_encoded)).document.root.kind == decode(py_encoded).document.root.kind
    assert decode(memoryview(py_encoded)).document.root.kind == decode(py_encoded).document.root.kind


# ---- Safety: no code execution on load --------------------------------------

def test_codec_module_never_executes_data() -> None:
    source = inspect.getsource(codec_module)
    forbidden = ("eval(", "exec(", "import pickle", "pickle.", "import marshal", "marshal.",
                 "__import__(", "compile(")
    for token in forbidden:
        assert token not in source, f"codec.py must not contain {token!r}"


def test_string_field_shaped_like_code_round_trips_as_inert_string(py_encoded: bytes) -> None:
    raw = json.loads(py_encoded.decode("utf-8"))
    marker = "__import__('os').system('true')"
    raw["payload"]["tree"]["root"]["extended_type"] = marker
    _resign(raw)
    decoded = decode(_to_bytes(raw))  # must not execute; must come back as plain str
    assert decoded.document.root.extended_type == marker
    assert isinstance(decoded.document.root.extended_type, str)


# ---- Envelope / convenience API --------------------------------------------

def test_decoded_envelope_contains_all_required_fields(py_encoded: bytes) -> None:
    env = decode(py_encoded).envelope
    assert env.schema_version == CURRENT_SCHEMA_VERSION
    assert env.representation_format_id == "python"
    assert env.source_format_id == "python"
    assert env.plugin_id == "python"
    for attr in ("core_contract_version", "document_version", "next_short_id", "encoding",
                 "newline", "trailing_newline", "plugin_version", "plugin_contract_version"):
        assert getattr(env, attr) is not None


def test_decode_document_matches_decode_document_field(py_encoded: bytes) -> None:
    assert decode_document(py_encoded).root.kind == decode(py_encoded).document.root.kind


def test_short_id_map_for_matches_document_short_ids(py_document) -> None:
    result = short_id_map_for(py_document)
    for node in walk(py_document.root):
        if node.node_id is not None and node.short_id is not None:
            assert result.get_short_id(node.node_id) == node.short_id
