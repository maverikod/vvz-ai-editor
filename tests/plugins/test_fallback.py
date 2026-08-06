"""Fallback contract tests for concept C-013 (step G-022/T-001/A-003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.fallback.build_fallback_tree`` against REAL
merged format plugins -- ``PYTHON_FORMAT_PLUGIN`` (LibCST), ``BSL_FORMAT_PLUGIN``
(tree-sitter-bsl), and ``PLAIN_TEXT_FORMAT_PLUGIN`` itself -- reaching genuine
parse failures on genuinely broken source text, never a stubbed plugin that
raises on command. The one bare ``ValueError`` used below (see
``test_generic_exception_without_error_code_propagates_unchanged``) is not a
plugin double: it exercises a documented property of ``build_fallback_tree``
itself -- "no particular exception class is required" -- a shape no format
plugin in this codebase ever actually raises (every real plugin failure here
already carries an ``error_code``), so a bare stdlib exception is the only
way to hit that branch with a real object instead of inventing a fake one.

Covered: (1) ``FORMAT_CONTENT_PARSE_FAILED`` from a real plugin's
``parse_document`` (Python, BSL) opens the fallback and builds a structured
tree; (2) every other real failure shape a plugin actually raises --
``FORMAT_FRAGMENT_PARSE_FAILED`` from BSL's ``parse_fragment``,
``UNSUPPORTED_TRANSLATION`` from Python's ``export_from_common``, and a bare
exception with no ``error_code`` at all -- reaches the caller unchanged, by
identity, never masked by a fallback tree; (3) paragraph order and UUID4 key
invariants on the built tree; (4) every node the fallback builds (root and
paragraphs) carries its own fresh UUID4 ``node_id`` ({p013}); (5) metadata
field preservation -- ``source_format_id`` kept, ``representation_format_id``
fixed to ``"plain_text"``, ``fallback_reason``/``diagnostic`` populated from
the real diagnostic, and the mapping is read-only; (6) the built ``Document``
itself reports the plain-text representation while remembering its original
source format ({p050}); (7) raw, undecodable bytes are lossily-but-safely
decoded with UTF-8 replacement, exercised through ``PLAIN_TEXT_FORMAT_PLUGIN``'s
own real undecodable-bytes failure.

One confirmed defect is recorded, not hidden, per this project's own xfail
convention (see e.g. ``tests/test_tree_temp_yaml_comment_token_crash_regression.py``):
``test_original_bytes_do_not_round_trip_through_plain_text_rendering`` is an
``xfail(strict=False)`` proving that ``build_fallback_tree``'s blank-line
paragraph splitting does NOT achieve a byte-identical round trip once the
resulting document is rendered back out through
``PLAIN_TEXT_FORMAT_PLUGIN.render_document`` -- the paragraph separator
(blank line count), any trailing newline, and CRLF-vs-LF are all discarded
and never reconstructed by ``generate_output``'s bare ``"".join(...)`` over
paragraph texts with no separator at all. See that test's own docstring for
the minimal reproducer.

Out of scope for this file: the atomic step's ``test_reload_without_source_plugin``,
``test_explicit_reparse_success``, and
``test_explicit_reparse_failure_leaves_state_unchanged`` objects describe
storage-lifecycle (concept C-012) policies. ``fallback.py``'s own module
docstring is explicit that it "never touches a storage layer, performs no
file I/O, ... and calls no plugin" and defines no reparse/rebuild operation;
no ``tree_engine.storage`` module implementing that lifecycle is part of
this file's assigned subject, so those three policies are not exercised
here -- doing so would require mocking an entire collaborator this test
file has no real counterpart for, which is exactly the "stubbed plugin that
raises on command" this suite is required to avoid.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from tree_engine.core.nodes import NodeKind, make_node
from tree_engine.errors import ErrorCode
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
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN

# Real, genuinely-unparseable source for each real plugin -- an unterminated
# parameter list, the same defect LibCST/tree-sitter-bsl themselves reject.
BROKEN_PYTHON_SOURCE = "def broken(:\n    pass\n\ndef also_broken(:\n    pass\n"
BROKEN_BSL_DOCUMENT = "Процедура П(\nКонецПроцедуры\n".encode("utf-8")
BROKEN_BSL_FRAGMENT = "Функция Ф(\nКонецФункции".encode("utf-8")


def _capture_content_parse_failure(parse_document, source) -> FormatPluginContractError:
    """Drive a REAL plugin's ``parse_document`` over broken ``source`` and
    return the ``FormatPluginContractError`` it genuinely raises, failing
    the test outright if the plugin unexpectedly accepts the content."""

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
    by the real plugin -- distinct from the document code -- and must reach
    the caller unmasked, exactly the same exception object, no fallback
    tree built in its place."""

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
    (``ErrorCode.UNSUPPORTED_TRANSLATION``) -- not a parse failure at all --
    and must not be swallowed into a fallback tree."""

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
    for child in root.children:
        assert isinstance(child.node_id, UUID)
        assert child.node_id.version == 4
        all_ids.append(child.node_id)

    assert len(all_ids) == len(set(all_ids)), "every node_id must be distinct"


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


# -- 7. Undecodable bytes are decoded losslessly-for-safety with replacement -


def test_undecodable_bytes_are_decoded_with_utf8_replacement() -> None:
    """The plain_text plugin's own real ``parse_document`` genuinely fails on
    undecodable bytes with ``FORMAT_CONTENT_PARSE_FAILED``; feeding that same
    diagnostic and payload back into ``build_fallback_tree`` (a degenerate
    but legitimate plain_text-falls-back-to-plain_text case) exercises the
    module's own UTF-8-with-replacement decode path on a real failure."""

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


# -- 8. Confirmed defect: no byte-identical round trip via plain_text render


@pytest.mark.xfail(
    reason=(
        "build_fallback_tree splits at blank-line boundaries and joins each "
        "paragraph's lines with a normalized '\\n', discarding the blank-line "
        "separator between paragraphs, any trailing newline, and CRLF-vs-LF. "
        "PLAIN_TEXT_FORMAT_PLUGIN.generate_output then concatenates paragraph "
        "texts with NO separator at all, so rendering the fallback document "
        "back out never reproduces the original bytes for any multi-paragraph "
        "input or any input with a trailing newline -- confirmed defect, not "
        "yet fixed in fallback.py."
    ),
    strict=False,
)
def test_original_bytes_do_not_round_trip_through_plain_text_rendering() -> None:
    diagnostic = _capture_content_parse_failure(
        PYTHON_FORMAT_PLUGIN.parse_document, BROKEN_PYTHON_SOURCE
    )
    fallback_tree = build_fallback_tree(
        BROKEN_PYTHON_SOURCE, diagnostic, source_format_id="python"
    )

    rendered = PLAIN_TEXT_FORMAT_PLUGIN.render_document(fallback_tree.document)
    assert rendered == BROKEN_PYTHON_SOURCE.encode("utf-8")
