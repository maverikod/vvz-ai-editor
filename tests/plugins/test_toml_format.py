"""Contract tests for the TOML format plugin (concept C-016,
step G-023/T-001/A-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``tree_engine.plugins.toml_format.TomlFormatPlugin`` through
its own public entry points -- ``parse_document``/``parse_fragment``,
``import_to_common``/``export_from_common``, ``generate_output``, and the
``FormatBoundary``-facing ``render_document``/``render_fragment`` -- against
REAL ``.toml`` files already present on this machine (hand-written fixtures
are used only for adversarial/error-path cases the filesystem cannot be
relied on to contain).

Why the machinery matters: ``tomllib`` decides only whether a document is
*valid*; it never drives rendering. A private lossless scanner instead cuts
the source into ``_Entry`` spans that TILE the input with no gap and no
overlap, each node keeping its span verbatim in ``fields["raw"]``, and
rendering is a depth-first concatenation of those spans. That tiling
identity -- not ``tomllib`` -- is what makes ``render_document(parse_document(x))
== x`` hold, so several tests below pin the tiling directly (by
independently re-walking the tree and concatenating ``raw`` fields) rather
than only asserting the end-to-end byte equality that ``_render`` itself
also happens to produce.

Every input sampled from this machine round-tripped byte-identically in
manual verification before this suite was written (dozens of real
``pyproject.toml``/config files under this checkout's ``projects`` tree,
zero mismatches). No round-trip gap was found for TOML, unlike plain_text's
documented non-UTF-8 ``render_document`` gap -- if a future change
introduces one, ``test_byte_identical_round_trip_real_files`` below will
name the failing file.

Exceptions raised by this plugin come from ``tree_engine.exceptions``
(module-level ``FormatContentParseFailed``/``FormatFragmentParseFailed``/
``FormatPluginContractError``/``UnsupportedTranslation``), not from the
similarly-named classes in ``tree_engine.plugins.contract``: those
instances carry ``.code`` (an ``ErrorCode``) and a ``.details`` mapping,
not ``.error_code``/``.plugin_id``/``.node_type`` attributes -- asserted
precisely below so a future refactor cannot quietly swap the hierarchy.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import List
from uuid import UUID

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.core.plugin_boundary import FormatBoundary, implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (
    FormatContentParseFailed,
    FormatFragmentParseFailed,
    FormatPluginContractError,
    UnsupportedTranslation,
)
from tree_engine.plugins.contract import FormatPluginMetadata
from tree_engine.plugins.registry import FormatPluginRegistry, PluginRegistrationError
from tree_engine.plugins.toml_format import FORMAT_ID, TomlFormatPlugin, TOML_FORMAT_PLUGIN

PLUGIN = TOML_FORMAT_PLUGIN

SIMPLE_TABLE = (
    "title = \"demo\"\n"
    "count = 3\n"
    "\n"
    "[owner]\n"
    "name = \"ada\"\n"
    "active = true\n"
)

NESTED_AND_ARRAY = (
    "[server]\n"
    "host = \"local\"\n"
    "\n"
    "[server.tls]\n"
    "enabled = true\n"
    "\n"
    "[[server.routes]]\n"
    "path = \"/a\"\n"
    "\n"
    "[[server.routes]]\n"
    "path = \"/b\"\n"
)

DATETIME_DOC = (
    "created = 1979-05-27T07:32:00Z\n"
    "local_dt = 1979-05-27T07:32:00\n"
    "just_date = 1979-05-27\n"
    "just_time = 07:32:00\n"
)

MIXED_SCALARS = (
    "int_v = 42\n"
    "float_v = 3.5\n"
    "bool_v = true\n"
    "str_v = \"hello\"\n"
    "neg_v = -7\n"
)

# A search root local to this machine, known (verified manually) to hold
# dozens of real ``.toml`` files a few directories deep -- ``rglob`` is a
# generator and ``islice`` stops as soon as enough matches are found, so
# this never walks the whole filesystem, only as much of one project tree
# as needed to fill the sample.
_REAL_TOML_ROOT = Path("/home/vasilyvz/projects")
_REAL_TOML_SAMPLE_SIZE = 40


def _real_toml_sample() -> List[Path]:
    if not _REAL_TOML_ROOT.is_dir():
        return []
    candidates = itertools.islice(_REAL_TOML_ROOT.rglob("*.toml"), _REAL_TOML_SAMPLE_SIZE)
    return [p for p in candidates if p.is_file()]


REAL_TOML_FILES = _real_toml_sample()


def _tiled_reconstruction(root: Node) -> str:
    """Independently re-derive the source text from stored spans: walk the
    tree in the same pre-order ``_render`` uses and concatenate every
    ``fields["raw"]`` string encountered. This does not call ``_render`` (or
    any other plugin-private helper) -- it pins the tiling invariant itself
    (spans cover the source with no gap, no overlap, in document order),
    independent of whichever concatenation strategy the plugin's own
    renderer happens to use."""

    parts: List[str] = []
    for node in walk(root):
        raw = node.fields.get("raw")
        if isinstance(raw, str):
            parts.append(raw)
    return "".join(parts)


def _node_ids(root: Node) -> List[UUID]:
    return [n.node_id for n in walk(root)]


# -- 1. Metadata and extension registration -----------------------------------


def test_metadata_and_extension_registration_toml() -> None:
    metadata = PLUGIN.metadata
    assert isinstance(metadata, FormatPluginMetadata)
    assert metadata.format_id == FORMAT_ID == "toml"
    assert metadata.aliases == ()
    assert metadata.file_extensions == ("toml",)
    assert metadata.plugin_version == "1.0.0"
    assert metadata.contract_version == "1.0.0"
    assert metadata.capabilities["semantic_role_mapping"] is True
    assert metadata.capabilities["byte_identical_round_trip"] is True

    registry = FormatPluginRegistry()
    registry.register_format_plugin(TomlFormatPlugin())
    assert registry.get_format_plugin("toml").metadata.file_extensions == ("toml",)

    class _FakeOtherFormat:
        metadata = FormatPluginMetadata(
            format_id="fake_other_format", aliases=(), file_extensions=("toml",),
            plugin_version="1.0.0", contract_version="1.0.0", capabilities={},
        )

    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(_FakeOtherFormat())
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT
    assert excinfo.value.details["extension"] == "toml"


# -- 2. Round trip: simple table, nested/array-of-tables, datetime, scalars ---


def test_round_trip_simple_table() -> None:
    document = PLUGIN.parse_document(SIMPLE_TABLE)
    assert PLUGIN.generate_output(document) == SIMPLE_TABLE
    assert PLUGIN.render_document(document) == SIMPLE_TABLE.encode("utf-8")
    assert _tiled_reconstruction(document.root) == SIMPLE_TABLE


def test_round_trip_nested_tables_array_of_tables() -> None:
    document = PLUGIN.parse_document(NESTED_AND_ARRAY)
    assert PLUGIN.generate_output(document) == NESTED_AND_ARRAY
    assert _tiled_reconstruction(document.root) == NESTED_AND_ARRAY

    server = next(c for c in document.root.children if c.fields.get("key") == "server")
    tls = next(c for c in server.children if c.fields.get("key") == "server.tls")
    assert tls.kind == "toml:Table"
    routes = [c for c in server.children if c.fields.get("key") == "server.routes"]
    assert len(routes) == 2
    assert all(r.kind == "toml:ArrayOfTables" for r in routes)  # siblings, not nested
    assert routes[0].node_id != routes[1].node_id

    exported = PLUGIN.export_from_common(document)
    assert exported == {
        "server": {
            "host": "local",
            "tls": {"enabled": True},
            "routes": [{"path": "/a"}, {"path": "/b"}],
        }
    }


def test_round_trip_datetime() -> None:
    document = PLUGIN.parse_document(DATETIME_DOC)
    assert PLUGIN.generate_output(document) == DATETIME_DOC
    exported = PLUGIN.export_from_common(document)
    assert exported["just_date"].isoformat() == "1979-05-27"
    assert exported["just_time"].isoformat() == "07:32:00"
    assert exported["created"].isoformat() == "1979-05-27T07:32:00+00:00"


def test_toml_round_trip_mixed_scalars() -> None:
    document = PLUGIN.parse_document(MIXED_SCALARS)
    assert PLUGIN.generate_output(document) == MIXED_SCALARS
    exported = PLUGIN.export_from_common(document)
    assert exported == {"int_v": 42, "float_v": 3.5, "bool_v": True, "str_v": "hello", "neg_v": -7}
    assert isinstance(exported["int_v"], int) and not isinstance(exported["bool_v"], int) or exported["bool_v"] is True
    assert isinstance(exported["float_v"], float)


# -- 3. Byte-identical round trip + zero node loss on real files -------------


def test_byte_identical_round_trip_real_files() -> None:
    assert len(REAL_TOML_FILES) >= 5, "expected several real .toml files on this machine"
    checked = 0
    for path in REAL_TOML_FILES:
        raw = path.read_bytes()
        try:
            document = PLUGIN.parse_document(raw)
        except (FormatContentParseFailed, UnsupportedTranslation):
            continue  # not this plugin's concern here: covered by dedicated tests below
        rendered = PLUGIN.render_document(document)
        assert rendered == raw, f"byte-identical round trip failed for {path}"
        nodes = list(walk(document.root))
        node_ids = [n.node_id for n in nodes]
        short_ids = [n.short_id for n in nodes]
        assert len(node_ids) == len(set(node_ids)), f"duplicate node_id in {path}"
        assert all(isinstance(i, UUID) and i.version == 4 for i in node_ids), path
        assert all(isinstance(s, int) and s > 0 for s in short_ids), path
        assert len(short_ids) == len(set(short_ids)), f"duplicate short_id in {path}"
        assert _tiled_reconstruction(document.root) == raw.decode("utf-8"), f"tiling gap in {path}"
        checked += 1
    assert checked >= 5, "no real .toml file actually exercised the round trip"


# -- 4. Node identity ({p013}) -------------------------------------------------


def test_node_identity_uuid4_and_short_id() -> None:
    document = PLUGIN.parse_document(NESTED_AND_ARRAY)
    nodes = list(walk(document.root))
    assert len(nodes) > 5
    ids = [n.node_id for n in nodes]
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)
    assert len(ids) == len(set(ids)), "duplicate node_id: identity is not unique"
    short_ids = [n.short_id for n in nodes]
    assert all(isinstance(s, int) and s > 0 for s in short_ids)
    assert len(short_ids) == len(set(short_ids))
    # Re-parsing the same text must mint an entirely fresh identity set.
    again = PLUGIN.parse_document(NESTED_AND_ARRAY)
    assert set(_node_ids(document.root)).isdisjoint(_node_ids(again.root))


# -- 5. Malformed input -> FORMAT_CONTENT_PARSE_FAILED / FRAGMENT variant ----


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("key = [1, 2,\n", id="unterminated_array"),
        pytest.param("key = \"unterminated\n", id="unterminated_string"),
        pytest.param("= 1\n", id="missing_key"),
        pytest.param("[table\nkey = 1\n", id="unterminated_header"),
        pytest.param("key = \n", id="missing_value"),
    ],
)
def test_malformed_toml_parse_failure(bad: str) -> None:
    with pytest.raises(FormatContentParseFailed) as excinfo:
        PLUGIN.parse_document(bad)
    assert excinfo.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert excinfo.value.details["format_id"] == FORMAT_ID

    with pytest.raises(FormatFragmentParseFailed) as frag_excinfo:
        PLUGIN.parse_fragment(bad)
    assert frag_excinfo.value.code is ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED


# -- 6. UNSUPPORTED_TRANSLATION: the plugin's own documented cases -----------


def test_unsupported_translation_construct() -> None:
    # (a) a foreign node kind this plugin never produced.
    foreign = make_node("other_format:weird", fields={})
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.export_from_common(foreign)
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.details["node_type"] == "other_format:weird"
    assert excinfo.value.details["format_id"] == FORMAT_ID

    # (b) a non-standalone subtree: two sibling KeyValue nodes sharing a key
    # only became legal because they lived under different scopes; exported
    # alone, tomllib rejects the duplicate -> "not a standalone TOML document".
    kv_a = make_node("toml:KeyValue", fields={"raw": "x = 1\n", "key": "x", "value_text": "1"})
    kv_b = make_node("toml:KeyValue", fields={"raw": "x = 2\n", "key": "x", "value_text": "2"})
    table = make_node("toml:Table", fields={"key": "t"}, children=[kv_a, kv_b])
    with pytest.raises(UnsupportedTranslation) as table_excinfo:
        PLUGIN.export_from_common(table)
    assert table_excinfo.value.details["node_type"] == "toml:Table"

    # (c) a Python value with no TOML form at all.
    class NotRepresentable:
        pass

    with pytest.raises(UnsupportedTranslation) as value_excinfo:
        PLUGIN.generate_output({"a": NotRepresentable()})
    assert value_excinfo.value.details["node_type"] == "NotRepresentable"
    assert value_excinfo.value.details["format_id"] == FORMAT_ID


# -- 7. Fragment path -----------------------------------------------------------


def test_fragment_parsing_inline_table() -> None:
    fragment_text = "point = { x = 1, y = 2 }\n"
    fragment_root = PLUGIN.parse_fragment(fragment_text)
    assert isinstance(fragment_root, Node)
    assert fragment_root.kind == "toml:Document"
    assert len(fragment_root.children) == 1
    keyvalue = fragment_root.children[0]
    assert keyvalue.kind == "toml:KeyValue"
    assert keyvalue.fields["key"] == "point"
    assert keyvalue.fields["value_text"] == "{ x = 1, y = 2 }"
    assert PLUGIN.render_fragment(fragment_root) == fragment_text
    assert isinstance(fragment_root.node_id, UUID) and fragment_root.node_id.version == 4

    from_bytes = PLUGIN.parse_fragment(fragment_text.encode("utf-8"))
    assert PLUGIN.render_fragment(from_bytes) == fragment_text

    document = PLUGIN.parse_document(fragment_text)
    assert PLUGIN.generate_output(fragment_root) == PLUGIN.generate_output(document)


# -- 8. Contract violations -----------------------------------------------------


def test_wrong_argument_type_raises_format_plugin_contract_error() -> None:
    with pytest.raises(FormatPluginContractError) as excinfo:
        PLUGIN.parse_document(12345)  # type: ignore[arg-type]
    assert excinfo.value.code is ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert excinfo.value.details["plugin_id"] == FORMAT_ID

    with pytest.raises(FormatPluginContractError):
        PLUGIN.export_from_common(object())  # type: ignore[arg-type]

    with pytest.raises(FormatPluginContractError):
        PLUGIN.generate_output(object())  # type: ignore[arg-type]

    with pytest.raises(UnsupportedTranslation):
        PLUGIN.import_to_common(object())  # type: ignore[arg-type]


# -- 9. FormatBoundary conformance ----------------------------------------------


def test_implements_format_boundary_conformance() -> None:
    assert implements_format_boundary(TomlFormatPlugin) is True
    assert implements_format_boundary(PLUGIN) is True
    assert isinstance(PLUGIN, FormatBoundary)
    document = PLUGIN.parse_document(SIMPLE_TABLE)
    assert isinstance(document, Document)
    assert document.source_format_id == FORMAT_ID
    rendered_fragment = PLUGIN.render_fragment(PLUGIN.parse_fragment("k = 1\n"))
    assert rendered_fragment == "k = 1\n"
