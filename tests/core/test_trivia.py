"""Tests for the trivia/comment/format-attribute containers (C-002).

Targets ``src/tree_engine/core/trivia.py`` per {p008}/{p022}: byte-for-byte
lossless preservation of whitespace, newlines (CRLF/tabs included), and
comments, plus the extensible ``FormatAttributes`` side-channel.

The module has only the data containers -- no parser, no tree-level
reconstruction function (explicitly out of scope; left to format plugins).
The roundtrip tests build a small node tree and its trivia bindings by
hand, then reconstruct text with a local ``render`` helper that just
concatenates ``Trivia.leading_text``/``trailing_text`` around each token's
field text -- it adds no capability to the module itself.
"""

from dataclasses import FrozenInstanceError

import pytest

from tree_engine.core.nodes import make_node
from tree_engine.core.trivia import (
    CommentPlacement,
    CommentSlot,
    FormatAttributes,
    NodeTriviaBinding,
    Trivia,
    TriviaError,
    TriviaKind,
    TriviaPiece,
)
from tree_engine.errors import ErrorCode


def render(children, bindings):
    """Concatenate leading trivia + token text + trailing trivia in order."""
    parts = []
    for child, binding in zip(children, bindings):
        parts.append(binding.trivia.leading_text)
        parts.append(child.fields.get("text", ""))
        parts.append(binding.trivia.trailing_text)
    return "".join(parts)

@pytest.fixture
def two_token_document():
    """A tiny two-line fixture mixing CRLF, tabs, blank lines, a
    trailing inline comment, and a standalone leading comment."""
    source = "x = 1\t# value\r\n\r\n# note\ny = 2\n"
    inline_slot = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# value"),
        placement=CommentPlacement.INLINE,
        leading_whitespace=(TriviaPiece(TriviaKind.WHITESPACE, "\t"),),
        trailing_whitespace=(TriviaPiece(TriviaKind.NEWLINE, "\r\n"),),
    )
    node1 = make_node("token", fields={"text": "x = 1"})
    binding1 = NodeTriviaBinding(node=node1, trivia=Trivia(trailing=(inline_slot,)))
    standalone_slot = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# note"),
        placement=CommentPlacement.LEADING,
        trailing_whitespace=(TriviaPiece(TriviaKind.NEWLINE, "\n"),),
    )
    blank_line = TriviaPiece(TriviaKind.NEWLINE, "\r\n")
    node2 = make_node("token", fields={"text": "y = 2"})
    binding2 = NodeTriviaBinding(
        node=node2,
        trivia=Trivia(
            leading=(blank_line, standalone_slot),
            trailing=(TriviaPiece(TriviaKind.NEWLINE, "\n"),),
        ),
    )
    root = make_node("document", children=(node1, node2))
    return root, (binding1, binding2), source

def test_leading_trivia_slot_attaches_and_preserves_content():
    leading = (
        TriviaPiece(TriviaKind.WHITESPACE, "  "),
        TriviaPiece(TriviaKind.NEWLINE, "\r\n"),
        TriviaPiece(TriviaKind.WHITESPACE, "\t"),
    )
    trivia = Trivia(leading=leading)
    assert trivia.leading_text == "  \r\n\t"
    assert trivia.raw_text == "  \r\n\t"
    assert trivia.trailing == ()

def test_trailing_trivia_slot_attaches_and_preserves_content():
    trailing = (
        TriviaPiece(TriviaKind.WHITESPACE, "\t\t"),
        TriviaPiece(TriviaKind.NEWLINE, "\r\n"),
    )
    trivia = Trivia(trailing=trailing)
    assert trivia.trailing_text == "\t\t\r\n"
    assert trivia.raw_text == "\t\t\r\n"
    assert trivia.leading == ()

def test_standalone_comment_slot_attaches_to_node():
    slot = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# standalone comment"),
        placement=CommentPlacement.LEADING,
        leading_whitespace=(TriviaPiece(TriviaKind.WHITESPACE, "    "),),
        trailing_whitespace=(TriviaPiece(TriviaKind.NEWLINE, "\n"),),
    )
    trivia = Trivia(leading=(slot,))
    assert trivia.leading[0] is slot
    assert slot.placement is CommentPlacement.LEADING
    assert slot.piece.text == "# standalone comment"
    assert slot.raw_text == "    # standalone comment\n"

def test_inline_comment_slot_attaches_to_node():
    slot = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# inline"),
        placement=CommentPlacement.INLINE,
        leading_whitespace=(TriviaPiece(TriviaKind.WHITESPACE, " "),),
    )
    trivia = Trivia(trailing=(slot,))
    assert trivia.trailing[0] is slot
    assert slot.placement is CommentPlacement.INLINE
    assert slot.placement is not CommentPlacement.LEADING
    assert slot.raw_text == " # inline"

def test_multiple_trivia_and_comment_segments_preserve_order():
    blank1 = TriviaPiece(TriviaKind.NEWLINE, "\n")
    comment1 = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# first"),
        placement=CommentPlacement.LEADING,
        trailing_whitespace=(TriviaPiece(TriviaKind.NEWLINE, "\n"),),
    )
    blank2 = TriviaPiece(TriviaKind.NEWLINE, "\n")
    comment2 = CommentSlot(
        piece=TriviaPiece(TriviaKind.COMMENT, "# second"),
        placement=CommentPlacement.LEADING,
        trailing_whitespace=(TriviaPiece(TriviaKind.NEWLINE, "\n"),),
    )
    trivia = Trivia(leading=(blank1, comment1, blank2, comment2))
    assert trivia.leading == (blank1, comment1, blank2, comment2)
    assert trivia.leading_text == "\n# first\n\n# second\n"

def test_format_details_container_accepts_arbitrary_plugin_keys():
    fa = FormatAttributes()
    fa = fa.set("acme_plugin", "weird_key", {"nested": 1})
    fa = fa.set("acme_plugin", "another", [1, 2, 3])
    assert fa.get("acme_plugin", "weird_key") == {"nested": 1}
    assert fa.get("acme_plugin", "another") == [1, 2, 3]
    assert fa.get("acme_plugin", "missing", "fallback") == "fallback"
    assert "acme_plugin" in fa.namespaces()
    assert dict(fa.items("acme_plugin")) == {
        "weird_key": {"nested": 1},
        "another": [1, 2, 3],
    }
    other = FormatAttributes().set("acme_plugin", "weird_key", "overridden").set("other_ns", "k", "v")
    merged = fa.merge(other)
    assert merged.get("acme_plugin", "weird_key") == "overridden"
    assert merged.get("acme_plugin", "another") == [1, 2, 3]
    assert merged.get("other_ns", "k") == "v"

def test_format_details_container_does_not_mutate_base_schema_fields():
    node = make_node("token", fields={"value": "x"})
    fa = FormatAttributes().set("bsl", "indent_style", "tabs")
    binding = NodeTriviaBinding(node=node, format_attributes=fa)
    assert dict(binding.node.fields) == {"value": "x"}
    assert "indent_style" not in binding.node.fields
    assert not hasattr(node, "format_attributes")
    copied = binding.copy()
    assert dict(copied.node.fields) == {"value": "x"}
    assert copied.format_attributes.get("bsl", "indent_style") == "tabs"

def test_empty_trivia_and_comment_slots_default_safely():
    node = make_node("token", fields={"text": "x"})
    binding = NodeTriviaBinding(node=node)
    assert binding.trivia is None
    assert binding.format_attributes is None
    empty_trivia = Trivia()
    assert empty_trivia.leading == ()
    assert empty_trivia.trailing == ()
    assert empty_trivia.raw_text == ""
    with_trivia = binding.with_trivia(empty_trivia)
    assert with_trivia.trivia.raw_text == ""
    copied = binding.copy()
    assert copied.trivia is None
    assert copied.format_attributes is None

def test_roundtrip_reconstruction_is_byte_for_byte(two_token_document):
    root, bindings, source = two_token_document
    assert render(root.children, bindings) == source

def test_roundtrip_unchanged_subtree_stays_byte_for_byte(two_token_document):
    root, bindings, source = two_token_document
    binding1, binding2 = bindings
    node2 = root.children[1]
    untouched_before = render((node2,), (binding2,))

    new_node1 = make_node("token", fields={"text": "x = 999"})
    new_binding1 = NodeTriviaBinding(node=new_node1, trivia=binding1.trivia)
    new_root = make_node("document", children=(new_node1, node2))
    new_bindings = (new_binding1, binding2)
    assert render(new_root.children, new_bindings) != source
    untouched_after = render((new_root.children[1],), (new_bindings[1],))
    assert untouched_after == untouched_before == "\r\n# note\ny = 2\n"

def test_frozen_structures_reject_mutation_and_malformed_input_raises_trivia_error():
    piece = TriviaPiece(TriviaKind.WHITESPACE, " ")
    with pytest.raises(FrozenInstanceError):
        piece.text = "x"

    with pytest.raises(TriviaError) as excinfo:
        TriviaPiece(kind="not-a-kind", text=" ")
    assert excinfo.value.code is ErrorCode.INVALID_PARENT_TYPE

    with pytest.raises(TriviaError):
        CommentSlot(piece=TriviaPiece(TriviaKind.WHITESPACE, " "), placement=CommentPlacement.LEADING)

    with pytest.raises(TriviaError):
        FormatAttributes().get("", "key")
