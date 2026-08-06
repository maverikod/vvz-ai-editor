"""Contract tests for the plain_text format plugin (concept C-016,
step G-023/T-001/A-002).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``tree_engine.plugins.plain_text.PlainTextFormatPlugin``
through its own public entry points -- ``parse_document``/``parse_fragment``,
``import_to_common``/``export_from_common``, ``generate_output``, and the
``FormatBoundary``-facing ``render_document``/``render_fragment`` -- against
REAL files written to and read back from this machine's filesystem, not
in-memory literals alone. Plain text is the mandatory fallback
representation ({p060}), so the one property that matters above all others
is that nothing is ever lost: every awkward input below (CRLF line endings,
a missing trailing newline, an empty file, a UTF-8 BOM, mixed line-ending
styles, a very long single line, truncated/invalid multi-byte content) is
proven to round-trip through ``parse_document`` -> ``render_document``
byte-for-byte identical to the original file, or, where the subject
genuinely cannot do that, the gap is asserted honestly against the real
behavior and called out below rather than hidden or worked around.

Also covered: published metadata shape; extension registration in a real
``FormatPluginRegistry``; multi-paragraph order preservation through every
pipeline stage and a re-parse; ``parse_fragment`` consistency with
``parse_document`` including the single-paragraph fragment export path;
zero node loss at every stage; UUID4 ``node_id`` identity and ``short_id``
presence ({p013}); ``FORMAT_CONTENT_PARSE_FAILED`` on damaged/undecodable
input; ``FormatPluginContractError`` on wrong-argument-type calls;
``UnsupportedTranslationError`` on a foreign node kind; and structural
conformance with ``implements_format_boundary``.

Known, reported gap (not a test bug -- see the step report): ``generate_output``
preserves a non-UTF-8-decoded string exactly, but ``render_document``
unconditionally re-encodes as UTF-8, so a source read with an explicit
non-UTF-8 ``options["encoding"]`` does NOT round-trip byte-identically
through the ``FormatBoundary`` bytes path, only through the str-level
``generate_output`` path. Asserted directly below, not weakened.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.core.plugin_boundary import FormatBoundary, implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import (
    FormatPluginContractError,
    FormatPluginMetadata,
    UnsupportedTranslationError,
)
from tree_engine.plugins.plain_text import (
    FORMAT_ID,
    PLAIN_TEXT_FORMAT_PLUGIN,
    PlainTextFormatPlugin,
    PlainTextTree,
)
from tree_engine.plugins.registry import FormatPluginRegistry, PluginRegistrationError

PLUGIN = PLAIN_TEXT_FORMAT_PLUGIN
SAMPLE_TEXT = "alpha\nbeta\ngamma\ndelta\nepsilon"  # last line has no trailing newline


def _write(tmp_path: Path, name: str, data: bytes) -> bytes:
    """Write real bytes to a real file on disk under ``tmp_path`` and read
    them back -- the bytes fed to the plugin genuinely passed through the
    filesystem, not just an in-memory literal."""

    path = tmp_path / name
    path.write_bytes(data)
    return path.read_bytes()


def _paragraph_texts(root: Node) -> list:
    return [child.fields.get("text", "") for child in root.children]


class _FakeExtensionPlugin:
    """Bare-bones candidate exposing only ``metadata``, enough for
    ``register_format_plugin`` to evaluate an extension collision against
    the real plain_text plugin -- mirrors the sibling registry suite's own
    ``_MinimalContractPlugin`` fixture."""

    def __init__(self, *, file_extensions: tuple) -> None:
        self.metadata = FormatPluginMetadata(
            format_id="fake_other_format",
            aliases=(),
            file_extensions=file_extensions,
            plugin_version="1.0.0",
            contract_version="1.0.0",
            capabilities={},
        )


# -- 1. Metadata and extension registration ----------------------------------


def test_metadata_published_shape() -> None:
    metadata = PLUGIN.metadata
    assert isinstance(metadata, FormatPluginMetadata)
    assert metadata.format_id == FORMAT_ID == "plain_text"
    assert metadata.aliases == ()
    assert metadata.file_extensions == ("txt", "text")
    assert metadata.plugin_version == "1.0.0"
    assert metadata.contract_version == "1.0.0"
    assert metadata.capabilities["semantic_role_mapping"] is True
    assert metadata.capabilities["byte_identical_round_trip"] is True
    assert metadata.capabilities["fallback_representation"] is True


def test_extension_registration_txt() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PlainTextFormatPlugin())
    assert registry.get_format_plugin("plain_text").metadata.file_extensions[0] == "txt"
    # A different format_id claiming "txt" collides -- proves ".txt" is
    # actually indexed in the shared registry, not merely declared.
    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(_FakeExtensionPlugin(file_extensions=("txt",)))
    assert excinfo.value.details["extension"] == "txt"
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT


def test_extension_registration_text_variants() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PlainTextFormatPlugin())
    assert "text" in registry.get_format_plugin("plain_text").metadata.file_extensions
    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(_FakeExtensionPlugin(file_extensions=("text",)))
    assert excinfo.value.details["extension"] == "text"


# -- 2. Multi-paragraph round trip and order preservation --------------------


def test_multi_paragraph_roundtrip_parse_to_paragraphs() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    texts = _paragraph_texts(document.root)
    assert texts == SAMPLE_TEXT.splitlines(keepends=True)
    assert "".join(texts) == SAMPLE_TEXT


def test_order_preservation_through_import_to_common() -> None:
    tree = PlainTextTree()
    ids = [tree.append_paragraph(t) for t in ("one\n", "two\n", "three")]
    root = PLUGIN.import_to_common(tree, as_document=False)
    assert [child.node_id for child in root.children] == ids
    assert _paragraph_texts(root) == ["one\n", "two\n", "three"]


def test_order_preservation_through_export_from_common() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    exported = PLUGIN.export_from_common(document)
    assert isinstance(exported, PlainTextTree)
    assert list(exported.paragraphs.values()) == SAMPLE_TEXT.splitlines(keepends=True)
    assert list(exported.paragraphs.keys()) == [c.node_id for c in document.root.children]


def test_order_preservation_through_generate_output() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    assert PLUGIN.generate_output(document) == SAMPLE_TEXT


def test_order_preservation_through_reparse() -> None:
    first = PLUGIN.parse_document(SAMPLE_TEXT)
    second = PLUGIN.parse_document(SAMPLE_TEXT)
    assert _paragraph_texts(first.root) == _paragraph_texts(second.root)
    first_ids = [c.node_id for c in first.root.children]
    second_ids = [c.node_id for c in second.root.children]
    assert first_ids != second_ids
    assert set(first_ids).isdisjoint(second_ids)


# -- 3. Fragment path ----------------------------------------------------------


def test_parse_fragment_consistency_with_document() -> None:
    fragment_root = PLUGIN.parse_fragment(SAMPLE_TEXT)
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    assert isinstance(fragment_root, Node)
    assert fragment_root.kind == document.root.kind
    assert _paragraph_texts(fragment_root) == _paragraph_texts(document.root)
    assert PLUGIN.generate_output(fragment_root) == PLUGIN.generate_output(document)
    from_bytes = PLUGIN.parse_fragment(SAMPLE_TEXT.encode("utf-8"))
    assert _paragraph_texts(from_bytes) == _paragraph_texts(fragment_root)


def test_export_single_paragraph_fragment_node() -> None:
    fragment_root = PLUGIN.parse_fragment("only one line\n")
    paragraph_node = fragment_root.children[0]
    assert paragraph_node.kind == "plain_text:paragraph"
    exported = PLUGIN.export_from_common(paragraph_node)
    assert list(exported.paragraphs.values()) == ["only one line\n"]
    assert PLUGIN.generate_output(exported) == "only one line\n"


# -- 4. Damaged / undecodable input -------------------------------------------


def test_damaged_input_raises_format_content_parse_failed() -> None:
    # An unknown codec name is a LookupError, caught by the same branch as
    # a genuine decode failure -- FORMAT_CONTENT_PARSE_FAILED either way.
    with pytest.raises(FormatPluginContractError) as excinfo:
        PLUGIN.parse_document(b"hello", {"encoding": "not-a-real-codec"})
    assert excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert excinfo.value.plugin_id == FORMAT_ID


def test_undecodable_input_raises_format_content_parse_failed(tmp_path: Path) -> None:
    truncated = _write(tmp_path, "truncated.bin", b"caf\xe2\x82")  # incomplete multi-byte seq
    with pytest.raises(FormatPluginContractError) as excinfo:
        PLUGIN.parse_document(truncated)
    assert excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    with pytest.raises(FormatPluginContractError) as frag_excinfo:
        PLUGIN.parse_fragment(truncated)
    assert frag_excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED


def test_no_silent_truncation_on_errors() -> None:
    # A valid prefix followed by an undecodable suffix must reject the
    # WHOLE input -- never return the valid prefix as a partial result.
    valid_prefix = "valid text before the bad byte\n".encode("utf-8")
    bad_suffix = b"\xff\xfe broken"
    with pytest.raises(FormatPluginContractError):
        PLUGIN.parse_document(valid_prefix + bad_suffix)


# -- 5. Zero node loss at every stage ------------------------------------------


def test_zero_node_loss_parse_stage() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    expected = len(SAMPLE_TEXT.splitlines(keepends=True))
    assert len(document.root.children) == expected
    assert len(list(walk(document.root))) == expected + 1  # + the root itself


def test_zero_node_loss_import_stage() -> None:
    tree = PlainTextTree()
    for text in ("a\n", "b\n", "c\n", "d"):
        tree.append_paragraph(text)
    root = PLUGIN.import_to_common(tree, as_document=False)
    assert len(root.children) == len(tree.paragraphs) == 4


def test_zero_node_loss_export_stage() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    exported = PLUGIN.export_from_common(document)
    assert len(exported.paragraphs) == len(document.root.children)


def test_zero_node_loss_generate_stage() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    output = PLUGIN.generate_output(document)
    assert len(output) == sum(len(t) for t in _paragraph_texts(document.root))
    assert output == SAMPLE_TEXT


# -- 6. Node identity ({p013}) -------------------------------------------------


def test_uuid4_keyed_paragraphs_structure() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    nodes = list(walk(document.root))
    ids = [n.node_id for n in nodes]
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)
    assert len(ids) == len(set(ids)), "duplicate node_id: identity is not unique"
    # Every node also carries a short_id ({p097}): a positive integer, unique
    # within the document. Without it the query engine cannot address a
    # plain-text node at all.
    short_ids = [n.short_id for n in nodes]
    assert all(isinstance(s, int) and s > 0 for s in short_ids)
    assert len(short_ids) == len(set(short_ids))


def test_root_container_structure() -> None:
    document = PLUGIN.parse_document(SAMPLE_TEXT)
    assert isinstance(document, Document)
    assert document.source_format_id == FORMAT_ID
    root = document.root
    assert isinstance(root, Node)
    assert root.kind == "plain_text:root"
    assert isinstance(root.node_id, UUID) and root.node_id.version == 4
    assert all(child.kind == "plain_text:paragraph" for child in root.children)


# -- 7. Byte-identical round trip on real, awkward files ----------------------

_AWKWARD_CASES = [
    pytest.param(b"first line\r\nsecond line\r\nthird\r\n", id="crlf_line_endings"),
    pytest.param(b"alpha\nbeta\nno newline at end", id="no_trailing_newline"),
    pytest.param(b"", id="empty_file"),
    pytest.param(b"\xef\xbb\xbfhello world\nsecond line\n", id="utf8_bom_not_stripped"),
    pytest.param(b"unix\nwindows\r\nold_mac\rnext", id="mixed_line_endings"),
    pytest.param(("x" * 200_000).encode("ascii") + b"\nshort tail\n", id="very_long_single_line"),
    pytest.param(b"\n\n\n", id="blank_lines_only"),
]


@pytest.mark.parametrize("raw", _AWKWARD_CASES)
def test_byte_identical_round_trip_awkward_inputs(tmp_path: Path, raw: bytes) -> None:
    on_disk = _write(tmp_path, "awkward.bin", raw)
    document = PLUGIN.parse_document(on_disk)
    rendered = PLUGIN.render_document(document)
    assert isinstance(rendered, bytes)
    assert rendered == on_disk  # byte-identical, including a missing trailing newline
    assert PLUGIN.generate_output(document).encode("utf-8") == on_disk


def test_non_utf8_encoding_option_breaks_render_document_byte_identity(tmp_path: Path) -> None:
    """Documents a real gap (see module docstring / step report): a source
    decoded via an explicit non-UTF-8 ``options["encoding"]`` keeps its
    string content exact through ``generate_output``, but
    ``render_document`` (``plain_text.py``: ``text.encode("utf-8")``)
    unconditionally re-encodes as UTF-8, so the returned bytes are NOT
    byte-identical to the original latin-1-encoded file whenever it
    contains non-ASCII bytes. Asserted as actual behavior, not weakened."""

    raw = _write(tmp_path, "latin1.bin", "café naïve latin-1 text\n".encode("latin-1"))
    with pytest.raises(FormatPluginContractError):
        PLUGIN.parse_document(raw)  # default utf-8 decode rejects it outright
    document = PLUGIN.parse_document(raw, {"encoding": "latin-1"})
    assert PLUGIN.generate_output(document) == raw.decode("latin-1")
    rendered = PLUGIN.render_document(document)
    assert rendered == PLUGIN.generate_output(document).encode("utf-8")
    assert rendered != raw  # the documented gap: NOT byte-identical


# -- 8. Contract violations -----------------------------------------------------


def test_wrong_argument_type_raises_format_plugin_contract_error() -> None:
    with pytest.raises(FormatPluginContractError) as excinfo:
        PLUGIN.parse_document(12345)  # type: ignore[arg-type]
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert excinfo.value.plugin_id == FORMAT_ID

    with pytest.raises(FormatPluginContractError):
        PLUGIN.import_to_common("not-a-PlainTextTree")

    with pytest.raises(FormatPluginContractError):
        PLUGIN.export_from_common(object())  # type: ignore[arg-type]

    with pytest.raises(FormatPluginContractError):
        PLUGIN.generate_output(object())  # type: ignore[arg-type]


def test_export_unsupported_node_raises_unsupported_translation() -> None:
    foreign_child = make_node("other_format:weird", fields={})
    root = make_node("plain_text:root", fields={}, children=[foreign_child])
    document = Document(root=root, source_format_id=FORMAT_ID)
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PLUGIN.export_from_common(document)
    assert excinfo.value.node_type == "other_format:weird"
    assert excinfo.value.format_id == FORMAT_ID
    assert excinfo.value.error_code == ErrorCode.UNSUPPORTED_TRANSLATION


# -- 9. FormatBoundary conformance ----------------------------------------------


def test_implements_format_boundary_conformance() -> None:
    assert implements_format_boundary(PlainTextFormatPlugin) is True
    assert implements_format_boundary(PLUGIN) is True
    assert isinstance(PLUGIN, FormatBoundary)
    rendered_fragment = PLUGIN.render_fragment(PLUGIN.parse_fragment("hello\n"))
    assert rendered_fragment == "hello\n"
