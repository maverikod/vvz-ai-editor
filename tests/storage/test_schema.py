"""Tests for the tree-file envelope/payload/checksums schema and version gate.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.schema`` -- ``TreeFile``/``TreeFileEnvelope``/
``TreeFilePayload``/``ChecksumsSection`` round-trip, canonical serialization,
the schema-version gate (major rejection, explicit minor migration), and
per-field/per-section shape validation. Every tree body used here is built
from a document actually parsed by the real Python format plugin -- no
mocked subject and no fake trees where a real one is possible.

Deep structural validation of the tree body (UUID4 uniqueness, parent/child,
cycles) and checksum *value* computation are explicitly out of scope for
this module (per its own docstring) and are not exercised here.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from typing import Any, Dict

import pytest

from tree_engine.core.nodes import Node, walk
from tree_engine.errors import ErrorCode
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.storage import schema as schema_module
from tree_engine.storage.schema import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_MAJOR_VERSIONS,
    ChecksumsSection,
    TreeFile,
    TreeFileEnvelope,
    TreeFilePayload,
    TreeFileSchemaError,
    apply_minor_migrations,
)

PLUGIN = PythonFormatPlugin()

PY_SOURCE = (
    b"class Greeter:\n"
    b"    def greet(self, name):\n"
    b"        return 'hi ' + name\n"
)


def _node_to_plain(node: Node) -> Dict[str, Any]:
    """Convert a real parsed ``Node`` into a plain JSON-safe mapping.

    Not the production codec (a sibling module, out of scope here) --
    schema.py's own contract only requires ``payload.tree`` to be *a
    mapping*; deep shape is the codec/core's job. This gives the tests a
    real, non-trivial tree body instead of a hand-rolled fake one.
    """

    def _field(value: Any) -> Any:
        if isinstance(value, Node):
            return _node_to_plain(value)
        if isinstance(value, tuple):
            return [_field(item) for item in value]
        return value

    return {
        "kind": str(node.kind),
        "fields": {key: _field(val) for key, val in node.fields.items()},
        "children": [_node_to_plain(child) for child in node.children],
    }


def _short_id_map_dict(root: Node) -> Dict[str, Any]:
    """Build a real ``ShortIdMap.to_dict()``-shaped mapping from the actual
    node_id/short_id pairs a real parse assigned while walking the tree."""

    entries: Dict[str, str] = {}
    max_short = 0
    for node in walk(root):
        if node.node_id is not None and node.short_id is not None:
            entries[str(node.short_id)] = str(node.node_id)
            max_short = max(max_short, node.short_id)
    return {"entries": entries, "next_short_id": max_short + 1}


def _valid_envelope_dict(document_id: uuid.UUID, next_short_id: int) -> Dict[str, Any]:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "core_contract_version": "1.0.0",
        "document_id": str(document_id),
        "document_version": 1,
        "next_short_id": next_short_id,
        "representation_format_id": "python",
        "source_format_id": "python",
        "encoding": "utf-8",
        "newline": "\n",
        "trailing_newline": True,
        "plugin_id": "python",
        "plugin_version": "1.0.0",
        "plugin_contract_version": "1.0.0",
        "format_metadata": {"note": "test envelope"},
    }


def _valid_checksums_dict() -> Dict[str, str]:
    return {
        "source_sha256": hashlib.sha256(PY_SOURCE).hexdigest(),
        "tree_payload_sha256": hashlib.sha256(b"payload placeholder").hexdigest(),
    }


def _valid_tree_file_dict() -> Dict[str, Any]:
    document = PLUGIN.parse_document(PY_SOURCE)
    short_id_map = _short_id_map_dict(document.root)
    return {
        "envelope": _valid_envelope_dict(uuid.uuid4(), short_id_map["next_short_id"]),
        "payload": {"tree": _node_to_plain(document.root), "short_id_map": short_id_map},
        "checksums": _valid_checksums_dict(),
    }


REQUIRED_ENVELOPE_FIELDS = [
    "schema_version",
    "core_contract_version",
    "document_id",
    "document_version",
    "next_short_id",
    "representation_format_id",
    "source_format_id",
    "encoding",
    "newline",
    "trailing_newline",
    "plugin_id",
    "plugin_version",
    "plugin_contract_version",
]


# ---- Round trip and canonical form -----------------------------------------

def test_valid_tree_file_round_trips_through_to_dict_and_from_dict() -> None:
    """A valid tree file built from a real parsed document survives
    from_dict -> to_dict -> from_dict -> to_dict with the payload tree and
    checksums preserved exactly, and the second cycle is idempotent."""

    data = _valid_tree_file_dict()
    tree_file = TreeFile.from_dict(data)
    rendered = tree_file.to_dict()

    assert rendered["envelope"]["document_id"] == data["envelope"]["document_id"]
    assert rendered["payload"]["tree"] == data["payload"]["tree"]
    assert rendered["checksums"] == data["checksums"]

    again = TreeFile.from_dict(rendered)
    assert again.to_dict() == rendered


def test_payload_and_checksums_shape_keys() -> None:
    """Payload and checksums sections render exactly the documented key
    set -- pins the shape contract per {p085}, not just value equality."""

    data = _valid_tree_file_dict()
    tree_file = TreeFile.from_dict(data)
    assert set(tree_file.payload.to_dict().keys()) == {"tree", "short_id_map"}
    assert set(tree_file.checksums.to_dict().keys()) == {"source_sha256", "tree_payload_sha256"}


def test_to_dict_canonical_form_independent_of_input_key_order() -> None:
    """to_dict's key order is fixed by the code, not by the order keys
    happened to appear in the input dict at any nesting level."""

    data = _valid_tree_file_dict()

    def _reversed(mapping: Dict[str, Any]) -> Dict[str, Any]:
        return {key: mapping[key] for key in reversed(list(mapping.keys()))}

    reordered = {
        "checksums": _reversed(data["checksums"]),
        "payload": {
            "short_id_map": _reversed(data["payload"]["short_id_map"]),
            "tree": data["payload"]["tree"],
        },
        "envelope": _reversed(data["envelope"]),
    }
    # Confirm the reordering actually changed iteration order (a real input
    # difference), not just a no-op relabeling.
    assert list(reordered["envelope"].keys()) != list(data["envelope"].keys())

    canonical_a = TreeFile.from_dict(data).to_dict()
    canonical_b = TreeFile.from_dict(reordered).to_dict()
    assert canonical_a == canonical_b
    assert json.dumps(canonical_a) == json.dumps(canonical_b)
    assert list(canonical_a["envelope"].keys()) == list(canonical_b["envelope"].keys())


# ---- Version gate -----------------------------------------------------------

def test_version_gate_accepts_current_supported_version() -> None:
    data = _valid_tree_file_dict()
    assert data["envelope"]["schema_version"] == CURRENT_SCHEMA_VERSION
    tree_file = TreeFile.from_dict(data)
    assert tree_file.envelope.schema_version == CURRENT_SCHEMA_VERSION


def test_unsupported_major_schema_version_rejected() -> None:
    data = _valid_tree_file_dict()
    data["envelope"]["schema_version"] = "999.0"
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_SCHEMA_UNSUPPORTED
    assert 999 not in SUPPORTED_SCHEMA_MAJOR_VERSIONS


def test_apply_minor_migrations_upgrades_through_injected_registry() -> None:
    """MINOR_MIGRATIONS ships empty (schema 1.0 is the only minor so far),
    so the generic migration engine is exercised directly through its
    documented ``migrations`` override parameter."""

    major = next(iter(SUPPORTED_SCHEMA_MAJOR_VERSIONS))
    data = {"schema_version": f"{major}.0", "marker": "old"}

    def _bump(envelope_data: Dict[str, Any]) -> Dict[str, Any]:
        migrated = dict(envelope_data)
        migrated["schema_version"] = f"{major}.1"
        migrated["marker"] = "new"
        return migrated

    result = apply_minor_migrations(data, {(major, 0): _bump})
    assert result["schema_version"] == f"{major}.1"
    assert result["marker"] == "new"
    assert data["marker"] == "old"  # input dict never mutated


def test_apply_minor_migrations_detects_cycle() -> None:
    major = next(iter(SUPPORTED_SCHEMA_MAJOR_VERSIONS))
    data = {"schema_version": f"{major}.0"}

    def _loop(envelope_data: Dict[str, Any]) -> Dict[str, Any]:
        return dict(envelope_data)  # never advances the minor version

    with pytest.raises(TreeFileSchemaError) as exc_info:
        apply_minor_migrations(data, {(major, 0): _loop})
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_envelope_from_dict_migrates_through_real_registry(monkeypatch) -> None:
    """Wires a migration into the real, module-level MINOR_MIGRATIONS
    registry (auto-restored by monkeypatch) to prove TreeFileEnvelope.from_dict
    actually consults it -- not just the standalone engine function."""

    major = next(iter(SUPPORTED_SCHEMA_MAJOR_VERSIONS))

    def _bump(envelope_data: Dict[str, Any]) -> Dict[str, Any]:
        migrated = dict(envelope_data)
        migrated["schema_version"] = f"{major}.1"
        return migrated

    monkeypatch.setitem(schema_module.MINOR_MIGRATIONS, (major, 0), _bump)

    data = _valid_tree_file_dict()
    data["envelope"]["schema_version"] = f"{major}.0"
    tree_file = TreeFile.from_dict(data)
    assert tree_file.envelope.schema_version == f"{major}.1"


# ---- Required envelope fields -----------------------------------------------

@pytest.mark.parametrize("field_name", REQUIRED_ENVELOPE_FIELDS)
def test_envelope_missing_required_field_rejected(field_name: str) -> None:
    data = _valid_tree_file_dict()
    del data["envelope"][field_name]
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_envelope_invalid_document_id_rejected() -> None:
    """A syntactically valid UUID that is not version 4 is rejected."""
    data = _valid_tree_file_dict()
    data["envelope"]["document_id"] = str(uuid.uuid1())
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_envelope_wrong_type_rejected() -> None:
    data = _valid_tree_file_dict()
    data["envelope"] = "not-a-mapping"
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


# ---- Checksums ---------------------------------------------------------------

def test_missing_checksums_section_rejected() -> None:
    data = _valid_tree_file_dict()
    del data["checksums"]
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


@pytest.mark.parametrize("field_name", ["source_sha256", "tree_payload_sha256"])
@pytest.mark.parametrize(
    "bad_value",
    ["g" * 64, "a" * 63, "a" * 65, ""],
    ids=["non_hex_char", "too_short", "too_long", "empty"],
)
def test_malformed_checksum_rejected(field_name: str, bad_value: str) -> None:
    data = _valid_tree_file_dict()
    data["checksums"][field_name] = bad_value
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


# ---- Payload shape ------------------------------------------------------------

def test_payload_tree_wrong_type_rejected() -> None:
    data = _valid_tree_file_dict()
    data["payload"]["tree"] = ["not", "a", "mapping"]
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_payload_short_id_map_wrong_type_rejected() -> None:
    data = _valid_tree_file_dict()
    data["payload"]["short_id_map"] = "not-a-mapping"
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("entries"),
        lambda m: m.pop("next_short_id"),
        lambda m: m.__setitem__("entries", {"not-an-int": str(uuid.uuid4())}),
        lambda m: m.__setitem__("entries", {"1": "not-a-uuid"}),
    ],
    ids=["missing_entries", "missing_next_short_id", "non_int_short_id_key", "non_uuid_node_id"],
)
def test_short_id_map_malformed_rejected(mutate) -> None:
    data = _valid_tree_file_dict()
    mutate(data["payload"]["short_id_map"])
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(data)
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_short_id_map_entries_not_a_mapping_rejected() -> None:
    """A non-mapping ``short_id_map.entries`` makes ShortIdMap.from_dict call
    ``.items()`` on it. That AttributeError must not escape: like every other
    malformed field it has to surface as TreeFileSchemaError with
    TREE_PAYLOAD_INVALID, which is what this module's contract promises."""

    for probe in ("not-a-mapping", ["a"], 42, None):
        data = _valid_tree_file_dict()
        data["payload"]["short_id_map"]["entries"] = probe
        with pytest.raises(TreeFileSchemaError) as exc_info:
            TreeFile.from_dict(data)
        assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


def test_top_level_not_a_mapping_rejected() -> None:
    with pytest.raises(TreeFileSchemaError) as exc_info:
        TreeFile.from_dict(["not", "a", "mapping"])  # type: ignore[arg-type]
    assert exc_info.value.code == ErrorCode.TREE_PAYLOAD_INVALID


# ---- No code execution on load -----------------------------------------------

def test_schema_module_never_executes_data() -> None:
    """Static pin of the module's own safety claim: no eval/exec/pickle/
    marshal/dynamic-import call appears anywhere in schema.py's source, so
    no load path through it can execute data."""

    source = inspect.getsource(schema_module)
    forbidden = ("eval(", "exec(", "import pickle", "pickle.", "import marshal", "marshal.", "__import__(", "compile(")
    for token in forbidden:
        assert token not in source, f"schema.py must not contain {token!r}"


def test_untrusted_string_field_round_trips_as_inert_string() -> None:
    """A value shaped like an execution attempt is round-tripped as a
    plain, unevaluated string -- never invoked as code."""
    data = _valid_tree_file_dict()
    payload_marker = "__import__('os').system('true')"
    data["envelope"]["format_metadata"] = {"payload": payload_marker}
    tree_file = TreeFile.from_dict(data)
    assert tree_file.envelope.format_metadata["payload"] == payload_marker
    assert isinstance(tree_file.envelope.format_metadata["payload"], str)
