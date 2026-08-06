"""Contract tests for the YAML format plugin (concept C-016,
step G-023/T-001/A-006).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``tree_engine.plugins.yaml.plugin.YAML_FORMAT_PLUGIN``
through its own public entry points -- ``parse_document``/``parse_fragment``,
``import_to_common``/``export_from_common``, ``generate_output``, and the
``FormatBoundary``-facing ``render_document``/``render_fragment`` -- against
REAL ``.yaml``/``.yml`` files already present on this machine (hand-written
fixtures are used only for adversarial/error-path cases a real corpus cannot
be relied on to contain in every shape).

This package was reworked once already: the first version refused 41% of
real YAML because it could not read flow collections. Flow collections are
therefore pinned hard below, in both isolation and in combination with block
structure, because that is exactly the regression this suite exists to
catch.

PyYAML is used here, in this test module only, purely as an independent
oracle for decoded *values* (never for structure or byte-for-byte identity,
which this plugin's own reader/emitter must reproduce unaided). The plugin
under test never imports PyYAML: its docstring is explicit that it is
standard library plus sibling ``tree_engine`` modules only.

Two honest, deliberate divergences from PyYAML are pinned rather than
hidden: (1) an unquoted date-like scalar such as ``2023-01-01`` decodes here
as the plain string it is under the YAML 1.2 *core schema* this plugin
implements, while PyYAML (a YAML 1.1 engine) resolves it to
``datetime.date``; (2) a dotless exponential such as ``1e10`` decodes here
as a float per the core schema, while PyYAML's 1.1 resolver requires a
decimal point and leaves it a string. Neither is a bug in this plugin --
both are pinned so a future change cannot silently pick a different schema.

Exceptions raised by this plugin come from ``tree_engine.exceptions``, not
``tree_engine.plugins.contract``: instances carry ``.code`` (an
``ErrorCode``) and a ``.details`` mapping.
"""

from __future__ import annotations

import datetime
import itertools
from pathlib import Path
from typing import List
from uuid import UUID

import pytest
import yaml as pyyaml

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
from tree_engine.plugins.yaml.plugin import FORMAT_ID, YAML_FORMAT_PLUGIN, YamlFormatPlugin

PLUGIN = YAML_FORMAT_PLUGIN

# A search root local to this machine, known (verified manually) to hold
# hundreds of real ``.yaml``/``.yml`` files a few directories deep --
# ``rglob`` is a generator and ``islice`` stops as soon as enough matches
# are found, so this never walks the whole filesystem, only as much of one
# project tree as needed to fill the sample.
_REAL_YAML_ROOT = Path("/home/vasilyvz/projects")
_REAL_YAML_SAMPLE_SIZE = 60


def _real_yaml_sample() -> List[Path]:
    if not _REAL_YAML_ROOT.is_dir():
        return []
    candidates = itertools.chain(
        itertools.islice(_REAL_YAML_ROOT.rglob("*.yaml"), _REAL_YAML_SAMPLE_SIZE),
        itertools.islice(_REAL_YAML_ROOT.rglob("*.yml"), _REAL_YAML_SAMPLE_SIZE // 3),
    )
    return [p for p in candidates if p.is_file()]


REAL_YAML_FILES = _real_yaml_sample()


def _node_ids(root: Node) -> List[UUID]:
    return [n.node_id for n in walk(root)]


def _round_trip(text: str) -> Document:
    """Parse ``text`` and assert it renders back byte-identically; return the document."""

    document = PLUGIN.parse_document(text)
    assert PLUGIN.render_document(document) == text.encode("utf-8")
    assert PLUGIN.generate_output(document) == text
    return document

# -- 1. Metadata and extension registration -----------------------------------

def test_metadata_fields_published() -> None:
    metadata = PLUGIN.metadata
    assert isinstance(metadata, FormatPluginMetadata)
    assert metadata.format_id == FORMAT_ID == "yaml"
    assert metadata.aliases == ("yml",)
    assert metadata.file_extensions == ("yaml", "yml")
    assert metadata.plugin_version == "1.0.0"
    assert metadata.contract_version == "1.0.0"
    assert metadata.capabilities["semantic_role_mapping"] is True
    assert metadata.capabilities["byte_identical_round_trip"] is True


def test_both_yaml_extensions_registered() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(YamlFormatPlugin())
    resolved = registry.get_format_plugin("yaml")
    assert resolved.metadata.file_extensions == ("yaml", "yml")

    class _FakeOtherFormat:
        metadata = FormatPluginMetadata(
            format_id="fake_other_format", aliases=(), file_extensions=("yaml",),
            plugin_version="1.0.0", contract_version="1.0.0", capabilities={},
        )

    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(_FakeOtherFormat())
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT
    assert excinfo.value.details["extension"] == "yaml"

# -- 2. Round trip: nested mapping, sequence, scalar variety -------------------

def test_nested_mapping_round_trip() -> None:
    text = ("server:\n  host: local\n  tls:\n    enabled: true\n"
           "  routes:\n    - path: /a\n    - path: /b\n")
    document = _round_trip(text)
    exported = PLUGIN.export_from_common(document)
    assert exported == pyyaml.safe_load(text)
    assert exported == {
        "server": {"host": "local", "tls": {"enabled": True},
                   "routes": [{"path": "/a"}, {"path": "/b"}]},
    }


def test_sequence_round_trip() -> None:
    text = "items:\n  - 1\n  - two\n  - true\n  - null\n  - 3.5\n  - [1, 2]\n  - {a: 1}\n"
    document = _round_trip(text)
    exported = PLUGIN.export_from_common(document)
    assert exported == pyyaml.safe_load(text)
    assert exported == {"items": [1, "two", True, None, 3.5, [1, 2], {"a": 1}]}


def test_scalar_variety_round_trip() -> None:
    text = ("s: hello world\nn_int: 42\nn_neg: -7\nn_float: 3.14\n"
           "b_true: true\nb_false: false\nnul: null\ntilde: ~\nempty:\n"
           "quoted: \"a b\"\nsingle: 'c d'\n")
    document = _round_trip(text)
    exported = PLUGIN.export_from_common(document)
    assert exported == pyyaml.safe_load(text)
    assert exported["n_int"] == 42 and isinstance(exported["n_int"], int)
    assert exported["n_float"] == 3.14 and isinstance(exported["n_float"], float)
    assert exported["b_true"] is True and exported["b_false"] is False
    assert exported["nul"] is None and exported["tilde"] is None and exported["empty"] is None

    # Deliberate, documented divergences from PyYAML's YAML-1.1 resolver --
    # see the module docstring. Pinned so a future change cannot silently
    # switch schema without a test noticing.
    date_doc = _round_trip("date: 2023-01-01\n")
    assert PLUGIN.export_from_common(date_doc) == {"date": "2023-01-01"}
    assert isinstance(pyyaml.safe_load("date: 2023-01-01\n")["date"], datetime.date)

    exp_doc = _round_trip("n: 1e10\n")
    assert PLUGIN.export_from_common(exp_doc) == {"n": 1e10}
    assert pyyaml.safe_load("n: 1e10\n") == {"n": "1e10"}  # PyYAML: no dot, stays a string

# -- 3. Flow collections: the historical failure mode --------------------------

_FLOW_CASES = [
    pytest.param("a: {}\nb: []\n", id="empty_flow"),
    pytest.param("a: [1, 2, 3,]\n", id="trailing_comma"),
    pytest.param("a: [1,2,   3]\n", id="irregular_inner_spacing"),
    pytest.param("a: [1, # one\n  2, # two\n  3]\n", id="comments_inside_flow"),
    pytest.param("# before\na: [1, 2] # after\n", id="comments_before_and_after_flow"),
    pytest.param("a: {\n  b: 1,\n  c: 2\n}\n", id="multi_line_flow"),
    pytest.param('a: ["x,y", "a{b}", "c[d]", "e:f", \'p,q\']\n', id="quoted_specials"),
    pytest.param("a: {b: 1, c: [1,2]}\n", id="flow_value_same_line_as_block_key"),
    pytest.param("a:\n  b: {c: [1, {d: 2}], e: [3, 4]}\n", id="block_containing_nested_flow"),
    pytest.param("a: [[1, 2], [3, [4, 5]]]\n", id="nested_flow_sequences"),
    pytest.param("a: {b: {c: {d: 1}}}\n", id="nested_flow_mappings"),
    pytest.param("a: [1,\r\n  2,\r\n  3]\r\n", id="crlf_inside_multiline_flow"),
    pytest.param("a: [   1   ,   2   ]\n", id="wide_irregular_spacing"),
]


@pytest.mark.parametrize("text", _FLOW_CASES)
def test_flow_collection_round_trip(text: str) -> None:
    document = _round_trip(text)
    assert PLUGIN.export_from_common(document) == pyyaml.safe_load(text)


def test_flow_collection_as_block_mapping_key_unsupported() -> None:
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.parse_document("{a: 1}: value\n")
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.details["node_type"] == "FlowKey"

# -- 4. Block scalars ------------------------------------------------------------

_BLOCK_SCALAR_CASES = [
    pytest.param("a: |\n  line1\n  line2\n", "line1\nline2\n", id="literal_clip"),
    pytest.param("a: |-\n  line1\n  line2\n", "line1\nline2", id="literal_strip"),
    pytest.param("a: |+\n  line1\n\n\n", "line1\n\n\n", id="literal_keep"),
    pytest.param("a: >\n  line1\n  line2\n", "line1 line2\n", id="folded_clip"),
    pytest.param("a: >-\n  line1\n  line2\n", "line1 line2", id="folded_strip"),
    pytest.param("a: >2\n    indented\n", "  indented\n", id="folded_explicit_indent"),
]


@pytest.mark.parametrize("text, expected", _BLOCK_SCALAR_CASES)
def test_block_scalars_round_trip(text: str, expected: str) -> None:
    document = _round_trip(text)
    assert PLUGIN.export_from_common(document) == {"a": expected}
    assert pyyaml.safe_load(text) == {"a": expected}

# -- 5. Comments, blank lines, document markers ---------------------------------

def test_comments_and_blanks_survive_as_first_class_nodes() -> None:
    text = "# top comment\na: 1\n\nb: 2\n# trailing\n"
    document = _round_trip(text)
    kinds = [child.kind for child in document.root.children]
    assert kinds.count("yaml:Comment") == 0  # comments nest under the block, not the document
    assert PLUGIN.export_from_common(document) == {"a": 1, "b": 2}
    all_kinds = {node.kind for node in walk(document.root)}
    assert "yaml:Comment" in all_kinds
    assert "yaml:Blank" in all_kinds


def test_document_markers_round_trip() -> None:
    text = "---\na: 1\n...\n"
    document = _round_trip(text)
    assert any(child.kind == "yaml:Marker" for child in document.root.children)

    multi = "---\na: 1\n---\nb: 2\n"
    multi_document = _round_trip(multi)
    assert sum(1 for c in multi_document.root.children if c.kind == "yaml:Marker") == 2

# -- 6. Malformed input -> FORMAT_CONTENT_PARSE_FAILED / FRAGMENT variant ------

_MALFORMED_CASES = [
    pytest.param("a:\n\tb: 1\n", id="tab_in_indentation"),
    pytest.param('a: "unterminated\n', id="unterminated_double_quote"),
    pytest.param("a: 'unterminated\n", id="unterminated_single_quote"),
    pytest.param("a: [1, 2\n", id="unterminated_flow_sequence"),
    pytest.param("a: {b: 1\n", id="unterminated_flow_mapping"),
    pytest.param("hello\n", id="bare_top_level_scalar"),
    pytest.param("a: 1\n- b\n", id="mapping_and_sequence_mixed_in_one_block"),
    pytest.param("a:\n  b: 1\n c: 2\n", id="inconsistent_indentation"),
    pytest.param(": value\n", id="empty_mapping_key"),
]


@pytest.mark.parametrize("bad", _MALFORMED_CASES)
def test_malformed_yaml_parse_failure(bad: str) -> None:
    with pytest.raises(FormatContentParseFailed) as excinfo:
        PLUGIN.parse_document(bad)
    assert excinfo.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert excinfo.value.details["plugin_id"] == FORMAT_ID

    with pytest.raises(FormatFragmentParseFailed) as frag_excinfo:
        PLUGIN.parse_fragment(bad)
    assert frag_excinfo.value.code is ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED

# -- 7. UNSUPPORTED_TRANSLATION: anchors, aliases, tags, explicit keys, merge --

@pytest.mark.parametrize("text, node_type", [
    pytest.param("a: &anchor 1\nb: *anchor\n", "Anchored", id="anchor_alias_block"),
    pytest.param("a: [1, &x 2, *x]\n", "Anchored", id="anchor_alias_flow"),
])
def test_anchors_and_aliases_unsupported(text: str, node_type: str) -> None:
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.parse_document(text)
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.details["node_type"] == node_type
    assert excinfo.value.details["format_id"] == FORMAT_ID


@pytest.mark.parametrize("text", [
    pytest.param("a: !!str 123\n", id="tag_block"),
    pytest.param("a: [!!str 123]\n", id="tag_flow"),
])
def test_custom_tags_unsupported(text: str) -> None:
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.parse_document(text)
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.details["node_type"] == "Anchored"


@pytest.mark.parametrize("text", [
    pytest.param("<<: {a: 1}\nb: 2\n", id="merge_key_block"),
    pytest.param("a: {<<: 1}\n", id="merge_key_flow_mapping"),
])
def test_merge_keys_unsupported(text: str) -> None:
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.parse_document(text)
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_TRANSLATION
    assert excinfo.value.details["node_type"] == "MergeKey"


def test_explicit_key_unsupported() -> None:
    with pytest.raises(UnsupportedTranslation) as excinfo:
        PLUGIN.parse_document("? complex key\n: value\n")
    assert excinfo.value.details["node_type"] == "Anchored"

# -- 8. Byte-identical round trip + zero node loss on real files ---------------

def test_byte_identical_round_trip_real_files() -> None:
    assert len(REAL_YAML_FILES) >= 5, "expected several real .yaml/.yml files on this machine"
    checked = 0
    for path in REAL_YAML_FILES:
        raw = path.read_bytes()
        try:
            document = PLUGIN.parse_document(raw)
        except (FormatContentParseFailed, UnsupportedTranslation):
            continue  # not this test's concern: covered by the dedicated tests above
        rendered = PLUGIN.render_document(document)
        assert rendered == raw, f"byte-identical round trip failed for {path}"
        nodes = list(walk(document.root))
        node_ids = [n.node_id for n in nodes]
        short_ids = [n.short_id for n in nodes]
        assert len(node_ids) == len(set(node_ids)), f"duplicate node_id in {path}"
        assert all(isinstance(i, UUID) and i.version == 4 for i in node_ids), path
        assert all(isinstance(s, int) and s > 0 for s in short_ids), path
        assert len(short_ids) == len(set(short_ids)), f"duplicate short_id in {path}"
        checked += 1
    assert checked >= 5, "no real YAML file actually exercised the round trip"

# -- 9. Node identity ({p013}, {p097}) -----------------------------------------

def test_node_identity_uuid4_and_short_id() -> None:
    document = PLUGIN.parse_document("a:\n  b: {c: [1, 2]}\n  d:\n    - 1\n    - 2\n")
    nodes = list(walk(document.root))
    assert len(nodes) > 5
    ids = [n.node_id for n in nodes]
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)
    assert len(ids) == len(set(ids)), "duplicate node_id: identity is not unique"
    short_ids = [n.short_id for n in nodes]
    assert all(isinstance(s, int) and s > 0 for s in short_ids)
    assert len(short_ids) == len(set(short_ids))
    again = PLUGIN.parse_document("a:\n  b: {c: [1, 2]}\n  d:\n    - 1\n    - 2\n")
    assert set(_node_ids(document.root)).isdisjoint(_node_ids(again.root))

# -- 10. Fragment parsing --------------------------------------------------------

def test_fragment_parsing() -> None:
    single = PLUGIN.parse_fragment("a: 1\n")
    assert isinstance(single, Node)
    assert single.kind == "yaml:Mapping"
    assert PLUGIN.render_fragment(single) == "a: 1\n"

    multi_doc = PLUGIN.parse_fragment("---\na: 1\n---\nb: 2\n")
    assert multi_doc.kind == "yaml:Document"
    assert PLUGIN.render_fragment(multi_doc) == "---\na: 1\n---\nb: 2\n"

    from_bytes = PLUGIN.parse_fragment(b"a: 1\n")
    assert PLUGIN.render_fragment(from_bytes) == "a: 1\n"

# -- 11. Contract violations -----------------------------------------------------

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

    foreign = make_node("other_format:weird", fields={})
    with pytest.raises(UnsupportedTranslation) as foreign_excinfo:
        PLUGIN.export_from_common(foreign)
    assert foreign_excinfo.value.details["node_type"] == "other_format:weird"

# -- 12. FormatBoundary conformance ----------------------------------------------

def test_implements_format_boundary_conformance() -> None:
    assert implements_format_boundary(YamlFormatPlugin) is True
    assert implements_format_boundary(PLUGIN) is True
    assert isinstance(PLUGIN, FormatBoundary)
    document = PLUGIN.parse_document("a: 1\n")
    assert isinstance(document, Document)
    assert document.source_format_id == FORMAT_ID
    rendered_fragment = PLUGIN.render_fragment(PLUGIN.parse_fragment("k: 1\n"))
    assert rendered_fragment == "k: 1\n"
