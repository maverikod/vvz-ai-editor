"""Fallback contract tests for concept C-013 (step G-022/T-001/A-003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.fallback.build_fallback_tree`` against REAL
merged format plugins -- ``PYTHON_FORMAT_PLUGIN`` (LibCST), ``BSL_FORMAT_PLUGIN``
(tree-sitter-bsl), ``JSON_FORMAT_PLUGIN``, ``TOML_FORMAT_PLUGIN``, and
``PLAIN_TEXT_FORMAT_PLUGIN`` itself -- reaching genuine parse failures on
genuinely broken source text, never a stubbed plugin that raises on command.
The one bare ``ValueError`` used below (see
``test_generic_exception_without_error_code_propagates_unchanged``) is not a
plugin double: it exercises a documented property of ``build_fallback_tree``
itself -- "no particular exception class is required" -- a shape no format
plugin here raises, so a bare stdlib exception is the only way to hit that
branch with a real object.

Covered: (1) ``FORMAT_CONTENT_PARSE_FAILED`` from a real plugin's
``parse_document`` (Python, BSL) opens the fallback and builds a structured
tree; (2) every other real failure shape a plugin raises --
``FORMAT_FRAGMENT_PARSE_FAILED`` from BSL's ``parse_fragment``,
``UNSUPPORTED_TRANSLATION`` from Python's ``export_from_common``, and a bare
exception with no ``error_code`` at all -- reaches the caller unchanged, by
identity, never masked by a fallback tree; (3) paragraph order and UUID4 key
invariants on the built tree; (4) every node the fallback builds carries its
own fresh UUID4 ``node_id`` ({p013}) and a positive, unique ``short_id``
({p097}); (5) metadata field preservation -- ``source_format_id`` kept,
``representation_format_id`` fixed to ``"plain_text"``,
``fallback_reason``/``diagnostic`` populated from the real diagnostic, and the
mapping is read-only; (6) the built ``Document`` reports the plain-text
representation while remembering its original source format ({p050}); (7)
undecodable bytes read back as ``U+FFFD`` in a paragraph's human-facing
``text``, through ``PLAIN_TEXT_FORMAT_PLUGIN``'s own real failure.

Also covered: (8) byte-exact fidelity -- rendering a fallback document back out
through ``PLAIN_TEXT_FORMAT_PLUGIN.render_document`` reproduces the input bytes
exactly, across blank-line runs, CRLF and mixed line endings, a missing trailing
newline, a BOM, empty and whitespace-only payloads, a very long line, tabs,
latin-1 bytes, raw binary. This pins a fix: blank-line splitting used to discard
the paragraph separator, the trailing newline and CRLF-vs-LF, and undecodable
bytes were replaced, not preserved. (9) The canonical typed hierarchy of
``tree_engine.exceptions`` -- exposing ``code``, not ``error_code`` -- reaches
the fallback: the JSON plugin's real ``FormatContentParseFailed`` opens it,
TOML's ``FormatFragmentParseFailed`` propagates untouched.

Out of scope: the atomic step's ``test_reload_without_source_plugin``,
``test_explicit_reparse_success``, and
``test_explicit_reparse_failure_leaves_state_unchanged`` objects describe
storage-lifecycle (C-012) policies. ``fallback.py``'s own module docstring is
explicit that it "never touches a storage layer, performs no file I/O, ... and
calls no plugin" and defines no reparse/rebuild operation, so those policies
are not exercised here -- doing so would require mocking a collaborator this
file has no real counterpart for, exactly the "stubbed plugin that raises on
command" this suite must avoid.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from tree_engine.core.nodes import NodeKind, make_node
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import FormatContentParseFailed, FormatFragmentParseFailed
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.contract import (
    FormatPluginContractError,
    UnsupportedTranslationError,
)
from tree_engine.plugins.fallback import (
    PLAIN_TEXT_FORMAT_ID,
    FallbackTree,
    build_fallback_tree,
)
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.toml_format import TOML_FORMAT_PLUGIN

# Real, genuinely-unparseable source for each real plugin -- an unterminated
# parameter list, the same defect LibCST/tree-sitter-bsl themselves reject.
BROKEN_PYTHON_SOURCE = "def broken(:\n    pass\n\ndef also_broken(:\n    pass\n"
BROKEN_BSL_DOCUMENT = "Процедура П(\nКонецПроцедуры\n".encode("utf-8")
BROKEN_BSL_FRAGMENT = "Функция Ф(\nКонецФункции".encode("utf-8")


def _capture_content_parse_failure(parse_document, source) -> FormatPluginContractError:
    """Drive a REAL plugin's ``parse_document`` over broken ``source`` and
    return the ``FormatPluginContractError`` it genuinely raises, failing the
    test outright if the plugin unexpectedly accepts the content."""

    with pytest.raises(FormatPluginContractError) as excinfo:
        parse_document(source)
    return excinfo.value


# -- 1. Fallback triggers only on FORMAT_CONTENT_PARSE_FAILED -----------------


def test_python_parse_failure_triggers_plain_text_fallback() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    assert diagnostic.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED

    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )
    assert isinstance(fallback_tree, FallbackTree)
    assert fallback_tree.metadata.source_format_id == "python"
    assert fallback_tree.document.representation_format_id == PLAIN_TEXT_FORMAT_ID
    assert len(fallback_tree.paragraphs) == 2
    assert len(fallback_tree.order) == 2


def test_bsl_parse_failure_triggers_plain_text_fallback() -> None:
    diagnostic = _capture_content_parse_failure(
        BSL_FORMAT_PLUGIN.parse_document, BROKEN_BSL_DOCUMENT
    )
    assert diagnostic.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED

    fallback_tree = build_fallback_tree(
        BROKEN_BSL_DOCUMENT, diagnostic, source_format_id="bsl"
    )
    assert isinstance(fallback_tree, FallbackTree)
    assert fallback_tree.metadata.source_format_id == "bsl"
    assert fallback_tree.document.representation_format_id == PLAIN_TEXT_FORMAT_ID
    assert len(fallback_tree.paragraphs) >= 1


# -- 2. Every other real failure shape propagates unmasked, by identity -----


def test_bsl_fragment_parse_failure_propagates_unchanged() -> None:
    """A damaged BSL *fragment* is classified ``FORMAT_FRAGMENT_PARSE_FAILED``
    by the real plugin -- distinct from the document code -- and must reach the
    caller unmasked, the same exception object, no fallback tree built."""

    with pytest.raises(FormatPluginContractError) as plugin_excinfo:
        BSL_FORMAT_PLUGIN.parse_fragment(BROKEN_BSL_FRAGMENT)
    diagnostic = plugin_excinfo.value
    assert diagnostic.error_code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED

    with pytest.raises(FormatPluginContractError) as excinfo:
        build_fallback_tree(BROKEN_BSL_FRAGMENT, diagnostic, source_format_id="bsl")
    assert excinfo.value is diagnostic
    assert excinfo.value.error_code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED


def test_unsupported_translation_error_propagates_unchanged() -> None:
    """A real, structurally-unrecognized node fed to the Python plugin's own
    ``export_from_common`` genuinely raises ``UnsupportedTranslationError``
    (``ErrorCode.UNSUPPORTED_TRANSLATION``) -- not a parse failure -- and must
    not be swallowed into a fallback tree."""

    bogus_node = make_node(NodeKind("not_a_real_python_kind"), fields={})
    with pytest.raises(UnsupportedTranslationError) as plugin_excinfo:
        PYTHON_FORMAT_PLUGIN.export_from_common(bogus_node, {})
    diagnostic = plugin_excinfo.value
    assert diagnostic.error_code == ErrorCode.UNSUPPORTED_TRANSLATION

    with pytest.raises(UnsupportedTranslationError) as excinfo:
        build_fallback_tree("irrelevant", diagnostic, source_format_id="python")
    assert excinfo.value is diagnostic


def test_generic_exception_without_error_code_propagates_unchanged() -> None:
    """No ``error_code`` attribute at all must never accidentally equal
    ``FORMAT_CONTENT_PARSE_FAILED``; the module's own gate documents this
    exact acceptance of "any diagnostic shape". A bare ``ValueError`` is the
    real object that exercises it -- no plugin double involved."""

    diagnostic = ValueError("not a plugin diagnostic at all")
    with pytest.raises(ValueError) as excinfo:
        build_fallback_tree("irrelevant", diagnostic, source_format_id="python")
    assert excinfo.value is diagnostic


# -- 3. Paragraph order / UUID4 key invariants -------------------------------


def test_paragraph_order_and_uuid4_invariants() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )

    assert fallback_tree.order == tuple(fallback_tree.paragraphs.keys())
    assert fallback_tree.document.root.children == tuple(
        fallback_tree.paragraphs[node_id] for node_id in fallback_tree.order
    )

    indices = []
    starts = []
    for position, node_id in enumerate(fallback_tree.order):
        assert isinstance(node_id, UUID)
        assert node_id.version == 4
        node = fallback_tree.paragraphs[node_id]
        assert node.node_id == node_id
        assert node.fields["index"] == position
        indices.append(node.fields["index"])
        starts.append(node.fields["line_start"])

    assert indices == list(range(len(fallback_tree.order)))
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)
    assert [n.fields["text"] for n in fallback_tree.paragraphs.values()] == [
        "def broken(:\n    pass",
        "def also_broken(:\n    pass",
    ]


# -- 4. Every fallback node carries a fresh UUID4 node_id ({p013}) ----------


def test_every_fallback_node_has_a_uuid4_node_id() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )

    root = fallback_tree.document.root
    assert isinstance(root.node_id, UUID)
    assert root.node_id.version == 4

    all_ids = [root.node_id]
    short_ids = [root.short_id]
    for child in root.children:
        assert isinstance(child.node_id, UUID)
        assert child.node_id.version == 4
        all_ids.append(child.node_id)
        short_ids.append(child.short_id)

    assert len(all_ids) == len(set(all_ids)), "every node_id must be distinct"
    # {p097}: a compact positive short_id too, unique within the document --
    # without it the query engine cannot address a fallback node at all.
    assert all(isinstance(s, int) and s > 0 for s in short_ids)
    assert len(short_ids) == len(set(short_ids))


# -- 5. Metadata field preservation -------------------------------------------


def test_metadata_field_preservation() -> None:
    diagnostic = _capture_content_parse_failure(
        BSL_FORMAT_PLUGIN.parse_document, BROKEN_BSL_DOCUMENT
    )
    fallback_tree = build_fallback_tree(
        BROKEN_BSL_DOCUMENT, diagnostic, source_format_id="bsl"
    )
    metadata = fallback_tree.metadata

    assert metadata.source_format_id == "bsl"
    assert metadata.representation_format_id == PLAIN_TEXT_FORMAT_ID == "plain_text"
    assert metadata.diagnostic["error_code"] == ErrorCode.FORMAT_CONTENT_PARSE_FAILED.value
    assert metadata.diagnostic["plugin_id"] == "bsl"
    assert metadata.fallback_reason
    assert metadata.fallback_reason in metadata.diagnostic["message"]

    with pytest.raises(TypeError):
        metadata.diagnostic["error_code"] = "tampered"  # read-only mapping


# -- 6. Document remembers its source format under plain-text ({p050}) ------


def test_document_reports_plain_text_while_remembering_source_format() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )
    document = fallback_tree.document

    assert document.source_format_id == "python"
    assert document.representation_format_id == "plain_text"
    assert document.format_id == "plain_text"  # public {p050} alias
    assert document.source_format_id != document.representation_format_id


# -- 7. Undecodable bytes: U+FFFD to read, original bytes to render ---------


def test_undecodable_bytes_are_decoded_with_utf8_replacement() -> None:
    """The plain_text plugin's own real ``parse_document`` genuinely fails on
    undecodable bytes with ``FORMAT_CONTENT_PARSE_FAILED``; feeding that same
    diagnostic and payload back into ``build_fallback_tree`` (a degenerate but
    legitimate plain_text-falls-back-to-plain_text case) exercises the module's
    decode path on a real failure: the human-facing ``text`` shows ``U+FFFD``
    while the rendered document still returns the original bytes."""

    bad_bytes = b"hello \xff\xfe world\n"
    with pytest.raises(FormatPluginContractError) as plugin_excinfo:
        PLAIN_TEXT_FORMAT_PLUGIN.parse_document(bad_bytes)
    diagnostic = plugin_excinfo.value
    assert diagnostic.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED

    fallback_tree = build_fallback_tree(
        bad_bytes, diagnostic, source_format_id="plain_text"
    )
    assert len(fallback_tree.paragraphs) == 1
    (paragraph,) = fallback_tree.paragraphs.values()
    assert paragraph.fields["text"] == "hello �� world"
    assert PLAIN_TEXT_FORMAT_PLUGIN.render_document(fallback_tree.document) == bad_bytes


# -- 8. Confirmed defect: no byte-identical round trip via plain_text render


def test_original_bytes_round_trip_through_plain_text_rendering() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )

    rendered = PLAIN_TEXT_FORMAT_PLUGIN.render_document(fallback_tree.document)
    assert rendered == BROKEN_PYTHON_SOURCE.encode("utf-8")


_BYTE_EXACT_PAYLOADS = [
    pytest.param(b"def f():\n    pass\n\n\ndef g():\n  pass\n", id="blank_line_run"),
    pytest.param(b"a\r\nb\r\n", id="crlf"),
    pytest.param(b"unix\nwindows\r\nold_mac\rtail", id="mixed_line_endings"),
    pytest.param(b"x\n", id="single_line"),
    pytest.param(b"no trailing newline", id="no_trailing_newline"),
    pytest.param(b"a\n\n\n\nb", id="interior_blank_run_no_trailing_newline"),
    pytest.param(b"", id="empty"),
    pytest.param(b"\n\n\n", id="blank_lines_only"),
    pytest.param(b"   \n\t\n", id="whitespace_only"),
    pytest.param(b"\xef\xbb\xbfdef f(:\n", id="utf8_bom"),
    pytest.param(b"\tif x:\n\t\tpass\n", id="tabs"),
    pytest.param(("y" * 200_000).encode("ascii") + b"\ntail\n", id="very_long_line"),
    pytest.param("café naïve\n".encode("latin-1"), id="latin1_bytes"),
    pytest.param(b"\x00\x01\x02\xff\xfe\x80\n\x00", id="raw_binary"),
    pytest.param("Процедура П(\nКонецПроцедуры\n".encode("utf-8"), id="cyrillic_utf8"),
    pytest.param(b"\r\n\r\ndef f(:\r\n\r\n", id="crlf_blank_padding"),
]


@pytest.mark.parametrize("raw", _BYTE_EXACT_PAYLOADS)
def test_fallback_render_is_byte_identical_for_any_payload(raw: bytes) -> None:
    """The fallback exists so an unparseable file survives an open/save cycle
    intact: whatever bytes went in come back out unchanged."""

    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(raw, diagnostic, source_format_id="python")
    assert PLAIN_TEXT_FORMAT_PLUGIN.render_document(fallback_tree.document) == raw


# -- 9. The canonical typed exception hierarchy reaches the fallback --------


def test_typed_content_parse_failure_triggers_fallback() -> None:
    """The JSON plugin raises the canonical typed
    ``tree_engine.exceptions.FormatContentParseFailed`` -- exposing its code as
    ``code``, not ``error_code``, plus ``plain_text_fallback_permitted`` -- on
    malformed JSON. It must open the fallback, not be re-raised."""

    broken_json = b'{"a": }'
    with pytest.raises(FormatContentParseFailed) as excinfo:
        JSON_FORMAT_PLUGIN.parse_document(broken_json, source_format_id="json")
    diagnostic = excinfo.value
    assert diagnostic.code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert diagnostic.plain_text_fallback_permitted is True
    assert getattr(diagnostic, "error_code", None) is None

    fallback_tree = build_fallback_tree(broken_json, diagnostic, source_format_id="json")
    assert fallback_tree.metadata.source_format_id == "json"
    assert fallback_tree.document.representation_format_id == PLAIN_TEXT_FORMAT_ID
    assert fallback_tree.metadata.diagnostic["error_code"] == (
        ErrorCode.FORMAT_CONTENT_PARSE_FAILED.value
    )
    assert fallback_tree.metadata.diagnostic["plugin_id"] == "json"
    assert PLAIN_TEXT_FORMAT_PLUGIN.render_document(fallback_tree.document) == broken_json


def test_typed_non_fallback_failure_propagates_unchanged() -> None:
    """A typed exception that is NOT the fallback-permitting one -- the TOML
    plugin's real ``FormatFragmentParseFailed`` -- must reach the caller
    untouched though it comes from the same hierarchy."""

    with pytest.raises(FormatFragmentParseFailed) as plugin_excinfo:
        TOML_FORMAT_PLUGIN.parse_fragment("key = = 1")
    diagnostic = plugin_excinfo.value
    assert diagnostic.code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED
    assert diagnostic.plain_text_fallback_permitted is False

    with pytest.raises(FormatFragmentParseFailed) as excinfo:
        build_fallback_tree("key = = 1", diagnostic, source_format_id="toml")
    assert excinfo.value is diagnostic
