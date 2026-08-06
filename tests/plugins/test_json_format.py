"""Contract tests for the JSON format plugin (concept C-016,
step G-023/T-001/A-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``tree_engine.plugins.json_format.JsonFormatPlugin`` through
its own public entry points -- parse/fragment, import/export, generate, and
the ``FormatBoundary``-facing render methods -- against REAL ``.json`` files
discovered on this machine (this checkout plus this machine's virtualenv)
and hand-written awkward JSON text, never a mock of the subject.

Covered: metadata shape and ``.json`` extension registration in a real
``FormatPluginRegistry``; byte-identical round trip over nested objects,
arrays, mixed scalars, empty containers, a lone scalar, deep nesting, number
forms (``1.500``, ``1e10``, ``-0``), escapes/non-ASCII, and duplicate keys;
``parse_fragment`` including its no-raise text fallback; malformed input
raising ``FormatContentParseFailed`` (``.code is
ErrorCode.FORMAT_CONTENT_PARSE_FAILED``); circular/unmappable values raising
``UnsupportedTranslationError``; wrong-argument-type calls raising
``FormatPluginContractError``; zero node loss on a complex document; unique
UUID4 ``node_id``/``short_id`` per node; ``implements_format_boundary``.

No input found here fails to round-trip byte-identically; a future failure
is a real subject regression, not a fixture gap.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.core.plugin_boundary import FormatBoundary, implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import FormatContentParseFailed
from tree_engine.plugins.contract import (
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRole,
    UnsupportedTranslationError,
)
from tree_engine.plugins.json_format import FORMAT_ID, JSON_FORMAT_PLUGIN, JsonFormatPlugin
from tree_engine.plugins.registry import FormatPluginRegistry, PluginRegistrationError

PLUGIN = JSON_FORMAT_PLUGIN

# The exact deliberately-ugly document already hand-verified to round-trip
# byte-identically before this suite existed; kept here as a permanent
# regression rather than a one-off manual check.
_UGLY_DOCUMENT = b'{\n  "a":   [1,2 ,  3],\n\t"b" : {"c":null},\n  "d": 1.500,\n  "e": "\\u00e9\\t"\n}\n'

class _FakeExtensionPlugin:
    """Bare-bones candidate exposing only ``metadata``, enough for
    ``register_format_plugin`` to evaluate an extension collision against
    the real json plugin -- mirrors the plain_text suite's own fixture."""

    def __init__(self, *, file_extensions: tuple) -> None:
        self.metadata = FormatPluginMetadata(
            format_id="fake_other_format",
            aliases=(),
            file_extensions=file_extensions,
            plugin_version="1.0.0",
            contract_version="1.0.0",
            capabilities={},
        )

def _discover_real_json_files(limit: int = 20) -> list:
    """Real ``.json`` files genuinely present on this machine: this
    worktree's own checkout plus the shared virtualenv used to run this
    very test suite (see the step's verification command). Each candidate
    must be a small, UTF-8, stdlib-parseable JSON document; anything else
    (binary, oversized, non-JSON despite the extension) is skipped rather
    than forced into the sample."""

    roots = [Path(__file__).resolve().parents[2]]
    main_venv = Path("/home/vasilyvz/projects/tools/ai_editor/.venv")
    if main_venv.is_dir():
        roots.append(main_venv)
    found: list = []
    for root in roots:
        try:
            candidates = sorted(root.rglob("*.json"))
        except OSError:
            continue
        for path in candidates:
            try:
                if not path.is_file():
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            if not raw or len(raw) > 200_000:
                continue
            try:
                text = raw.decode("utf-8")
                json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            found.append((str(path), raw))
            if len(found) >= limit:
                return found
    return found

def _expected_node_count(value) -> int:
    """Number of common-model nodes a plain JSON value must produce: one
    node per object/array/scalar, plus one ``Member`` wrapper node per
    object entry -- mirrors ``json_format._raw_to_node``/``_plain_to_node``
    exactly, so it can catch any silently dropped or added node."""

    if isinstance(value, dict):
        return 1 + sum(1 + _expected_node_count(v) for v in value.values())
    if isinstance(value, list):
        return 1 + sum(_expected_node_count(v) for v in value)
    return 1

# -- 1. Metadata and extension registration -----------------------------------

def test_metadata_and_extension_registration() -> None:
    metadata = PLUGIN.metadata
    assert isinstance(metadata, FormatPluginMetadata)
    assert metadata.format_id == FORMAT_ID == "json"
    assert metadata.aliases == ()
    assert metadata.file_extensions == ("json",)
    assert metadata.plugin_version == "1.0.0"
    assert metadata.contract_version == "1.0.0"
    assert metadata.capabilities["semantic_role_mapping"] is True
    assert metadata.capabilities["byte_identical_round_trip"] is True

    registry = FormatPluginRegistry()
    registry.register_format_plugin(JsonFormatPlugin())
    assert registry.get_format_plugin("json").metadata.file_extensions == ("json",)
    # A different format_id claiming "json" collides -- proves ".json" is
    # actually indexed in the shared registry, not merely declared.
    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(_FakeExtensionPlugin(file_extensions=("json",)))
    assert excinfo.value.details["extension"] == "json"
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT

    # JSON models none of function/method/class/module ({p056}): empty, not
    # an omission -- roles_for returns () rather than raising.
    assert PLUGIN.semantic_role_mapping().node_type_to_role == {}
    assert PLUGIN.semantic_role_mapping().roles_for(SemanticRole.FUNCTION) == ()

# -- 2. Round-trip integrity ---------------------------------------------------

def test_round_trip_nested_object() -> None:
    original = {"level1": {"level2": {"level3": {"value": 42, "flag": True}}}}
    raw = json.dumps(original, indent=2).encode("utf-8")
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    assert PLUGIN.export_from_common(document) == original

def test_round_trip_arrays() -> None:
    raw = b'[1, "two", {"three": 3}, [4, 5, {"six": [6]}], null, false]'
    document = PLUGIN.parse_document(raw)
    assert document.root.kind == f"{FORMAT_ID}:Array"
    assert PLUGIN.render_document(document) == raw
    assert PLUGIN.export_from_common(document) == json.loads(raw)
    # No reordering: item positions survive the whole pipeline.
    assert [c.fields.get("value") for c in document.root.children[:2]] == [1, "two"]

def test_round_trip_mixed_scalars() -> None:
    raw = b'{"n": null, "t": true, "f": false, "i": 7, "fl": -3.5, "s": "hi"}'
    document = PLUGIN.parse_document(raw)
    exported = PLUGIN.export_from_common(document)
    assert exported["n"] is None
    assert exported["t"] is True and exported["f"] is False
    assert exported["i"] == 7 and isinstance(exported["i"], int) and not isinstance(exported["i"], bool)
    assert exported["fl"] == -3.5 and isinstance(exported["fl"], float)
    assert exported["s"] == "hi"
    assert PLUGIN.render_document(document) == raw

def test_round_trip_empty_containers() -> None:
    raw = b'{"empty_obj": {}, "empty_arr": [], "nested": {"inner": []}}'
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    assert PLUGIN.export_from_common(document) == {"empty_obj": {}, "empty_arr": [], "nested": {"inner": []}}
    for lone in (b"{}", b"[]"):
        lone_document = PLUGIN.parse_document(lone)
        assert PLUGIN.render_document(lone_document) == lone
        assert lone_document.root.children == ()

@pytest.mark.parametrize("raw", [b"42", b'"just a string"', b"true", b"false", b"null", b"-3.14"])
def test_round_trip_lone_scalar_document(raw: bytes) -> None:
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    assert PLUGIN.export_from_common(document) == json.loads(raw)

def test_round_trip_number_forms_and_negative_zero() -> None:
    raw = b'{"a": 1.500, "b": 1e10, "c": -0, "d": -0.0, "e": 3.14159265358979, "f": 2E-3}'
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    exported = PLUGIN.export_from_common(document)
    assert exported["a"] == 1.5 and exported["b"] == 1e10 and exported["f"] == 2e-3

def test_round_trip_escape_sequences_and_non_ascii() -> None:
    raw = (
        b'{"tab": "a\\tb", "newline": "a\\nb", "quote": "a\\"b", '
        b'"backslash": "a\\\\b", "unicode_escape": "\\u00e9\\u00e8", '
        b'"literal_utf8": "h\xc3\xa9llo caf\xc3\xa9"}'
    )
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    exported = PLUGIN.export_from_common(document)
    assert exported["tab"] == "a\tb"
    assert exported["unicode_escape"] == "éè"
    assert exported["literal_utf8"] == "héllo café"

def test_round_trip_duplicate_keys() -> None:
    raw = b'{"a": 1, "a": 2, "b": 3}'
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw  # raw text preserved regardless
    members = document.root.children
    assert len(members) == 3, "both 'a' members must survive as distinct nodes"
    assert [m.fields["key"] for m in members] == ["a", "a", "b"]
    # export_from_common follows plain-dict JSON semantics: last key wins,
    # same as json.loads -- a documented, not silent, collapse.
    assert PLUGIN.export_from_common(document) == {"a": 2, "b": 3}

def test_round_trip_deep_nesting() -> None:
    nested = {"v": 0}
    for _ in range(50):
        nested = {"child": nested}
    raw = json.dumps(nested).encode("utf-8")
    document = PLUGIN.parse_document(raw)
    assert PLUGIN.render_document(document) == raw
    assert PLUGIN.export_from_common(document) == nested

def test_round_trip_hand_written_ugly_document() -> None:
    document = PLUGIN.parse_document(_UGLY_DOCUMENT)
    assert PLUGIN.render_document(document) == _UGLY_DOCUMENT
    assert PLUGIN.generate_output(document).encode("utf-8") == _UGLY_DOCUMENT

def test_round_trip_real_json_files_on_this_machine() -> None:
    files = _discover_real_json_files(limit=20)
    assert len(files) >= 5, "expected several real .json files discoverable on this machine"
    failures = []
    for path, raw in files:
        document = PLUGIN.parse_document(raw)
        if PLUGIN.render_document(document) != raw:
            failures.append(path)
    assert not failures, f"not byte-identical for: {failures}"

# -- 3. Fragment path -----------------------------------------------------------

def test_parse_fragment_recognized_and_unrecognized() -> None:
    node = PLUGIN.parse_fragment('{"x": 1}')
    assert isinstance(node, Node) and node.kind == f"{FORMAT_ID}:Object"
    assert PLUGIN.generate_output(node) == '{"x": 1}'

    from_bytes = PLUGIN.parse_fragment(b'{"y": 2}')
    assert isinstance(from_bytes, Node)

    # Unrecognized/malformed fragment text: the fallback sentinel is the
    # fragment's own text, never raised, never None.
    for bad in (b'{"a": 1', b"not json {{{", b""):
        fallback = PLUGIN.parse_fragment(bad)
        assert fallback == (bad.decode("utf-8") if isinstance(bad, bytes) else bad)

    with pytest.raises(FormatPluginContractError):
        PLUGIN.parse_fragment(12345)  # type: ignore[arg-type]

# -- 4. Malformed input ----------------------------------------------------------

_MALFORMED_INPUTS = [
    pytest.param(b'{"a": 1', id="unclosed_object"),
    pytest.param(b"[1, 2", id="unclosed_array"),
    pytest.param(b"{} trailing garbage", id="trailing_content"),
    pytest.param(b'{"a" 1}', id="missing_colon"),
    pytest.param(b'{"a":1 "b":2}', id="missing_comma"),
    pytest.param(b"{1: 2}", id="non_string_key"),
    pytest.param(b'{"a": "unterminated}', id="unterminated_string"),
    pytest.param(b"", id="empty_input"),
]

@pytest.mark.parametrize("raw", _MALFORMED_INPUTS)
def test_malformed_input_parse_failure(raw: bytes) -> None:
    with pytest.raises(FormatContentParseFailed) as excinfo:
        PLUGIN.parse_document(raw)
    assert excinfo.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED

# -- 5. Unsupported translation ---------------------------------------------------

def test_unsupported_translation_circular() -> None:
    circular_obj: dict = {}
    circular_obj["self"] = circular_obj
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PLUGIN.import_to_common(circular_obj)
    assert excinfo.value.error_code == ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.format_id == FORMAT_ID
    assert excinfo.value.node_type == "object"

    circular_list: list = []
    circular_list.append(circular_list)
    with pytest.raises(UnsupportedTranslationError) as excinfo2:
        PLUGIN.import_to_common(circular_list)
    assert excinfo2.value.node_type == "array"

def test_unsupported_translation_other_constructs() -> None:
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PLUGIN.import_to_common({1: "x"})  # non-string key has no JSON representation
    assert excinfo.value.node_type == "object-key"

    class _NotJson:
        pass

    with pytest.raises(UnsupportedTranslationError) as excinfo2:
        PLUGIN.import_to_common(_NotJson())
    assert excinfo2.value.node_type == "_NotJson"

    # A foreign node kind reaching export_from_common has no JSON mapping.
    foreign = make_node("other_format:weird", fields={})
    document = Document(root=foreign, source_format_id=FORMAT_ID)
    with pytest.raises(UnsupportedTranslationError) as excinfo3:
        PLUGIN.export_from_common(document)
    assert excinfo3.value.node_type == "other_format:weird"

# -- 6. Contract violations -------------------------------------------------------

def test_wrong_argument_types_raise_contract_error() -> None:
    with pytest.raises(FormatPluginContractError) as excinfo:
        PLUGIN.parse_document(12345)  # type: ignore[arg-type]
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert excinfo.value.plugin_id == FORMAT_ID

    with pytest.raises(FormatPluginContractError):
        PLUGIN.export_from_common("not a Node or Document")  # type: ignore[arg-type]

    with pytest.raises(FormatPluginContractError):
        PLUGIN.generate_output(object())  # type: ignore[arg-type]

# -- 7. Zero node loss -------------------------------------------------------------

def test_no_silent_node_loss() -> None:
    original = {
        "object": {"nested": {"deep": [1, 2, {"x": True}]}},
        "array": [1, "two", None, {"three": 3}, [4, [5, 6]]],
        "scalars": {"n": None, "t": True, "f": False, "i": 1, "s": "s"},
    }
    raw = json.dumps(original).encode("utf-8")
    document = PLUGIN.parse_document(raw)
    assert len(list(walk(document.root))) == _expected_node_count(original)
    exported = PLUGIN.export_from_common(document)
    assert exported == original
    # Round back through the raw-less import path: still zero node loss.
    reimported_root = PLUGIN.import_to_common(exported)
    assert len(list(walk(reimported_root))) == _expected_node_count(original)

# -- 8. Node identity ({p013}) -----------------------------------------------------

def test_every_node_has_unique_uuid4_node_id_and_short_id() -> None:
    raw = json.dumps({"a": [1, 2, {"b": None, "c": True}], "d": "text"}).encode("utf-8")
    document = PLUGIN.parse_document(raw)
    nodes = list(walk(document.root))
    assert len(nodes) > 1
    ids = [n.node_id for n in nodes]
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)
    assert len(ids) == len(set(ids)), "duplicate node_id: identity is not unique"
    short_ids = [n.short_id for n in nodes]
    assert all(isinstance(s, int) and s > 0 for s in short_ids)
    assert len(short_ids) == len(set(short_ids))

# -- 9. FormatBoundary conformance --------------------------------------------------

def test_implements_format_boundary_and_render_roundtrip() -> None:
    assert implements_format_boundary(JsonFormatPlugin) is True
    assert implements_format_boundary(PLUGIN) is True
    assert isinstance(PLUGIN, FormatBoundary)

    document = PLUGIN.parse_document('{"a": 1}')
    rendered = PLUGIN.render_document(document)
    assert isinstance(rendered, bytes) and rendered == b'{"a": 1}'

    fragment_node = PLUGIN.parse_fragment('{"a": 1}')
    assert PLUGIN.render_fragment(fragment_node) == '{"a": 1}'
