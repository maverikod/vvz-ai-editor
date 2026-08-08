"""Tests for the three-way identifier map: short_id <-> node_id <-> native ref.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Everything here runs against real documents parsed by the real, registered
format plugins through the public facade -- there is no stand-in document and
no stub plugin, because the whole claim under test is that the three
identifiers of a genuinely parsed tree name the same node.

The four properties asserted are the ones the map exists for: the three forms
are interchangeable as INPUT; the integer is stable under an edit that moves a
node's position; the display style changes only what is REPORTED; and a format
whose plugin declares no reference notation reports the absence rather than a
synthesized string.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

import pytest

from tree_engine import facade
from tree_engine.core.identifier_map import (
    IdentifierMap, IdentifierStyle, NodeIdentifiers, native_reference_of,
)
from tree_engine.exceptions import NodeNotFound
from tree_engine.plugins.json_pointer import (
    NOTATION, build_pointer, escape_token, parse_pointer, unescape_token,
)

JSON_SOURCE = '{"a": [1, 2], "b": "x"}\n'
YAML_SOURCE = "a:\n  - 1\n  - 2\nb: x\n"
TOML_SOURCE = "# head\n[a]\nb = 1\n\n[[c]]\nd = 2\n\n[[c]]\nd = 3\n"
TEXT_SOURCE = "alpha\nbravo\ncharlie\n"

TREE_TEMP_FORMATS = (("json", JSON_SOURCE), ("yaml", YAML_SOURCE), ("toml", TOML_SOURCE))


# -- RFC 6901 syntax --------------------------------------------------------


@pytest.mark.parametrize("raw, escaped", [("a", "a"), ("a/b", "a~1b"), ("a~b", "a~0b"),
                                          ("~1", "~01"), ("m~n/o", "m~0n~1o")])
def test_token_escaping_round_trips_and_orders_tilde_before_slash(raw, escaped):
    assert escape_token(raw) == escaped
    assert unescape_token(escaped) == raw


def test_pointer_build_and_parse_are_inverses_including_the_root():
    assert build_pointer(()) == ""
    assert parse_pointer("") == ()
    assert build_pointer(("a", "0")) == "/a/0"
    assert parse_pointer("/a/0") == ("a", "0")
    assert parse_pointer("/a~1b") == ("a/b",)


@pytest.mark.parametrize("bad", ["a", "a/b", 5, None])
def test_parse_pointer_refuses_anything_that_is_not_a_pointer(bad):
    with pytest.raises(ValueError):
        parse_pointer(bad)


# -- the plugin declaration -------------------------------------------------


@pytest.mark.parametrize("format_id", ["json", "yaml", "toml"])
def test_data_format_plugins_declare_the_json_pointer_notation(format_id):
    declared = native_reference_of(facade._plugin(format_id))
    assert declared is not None
    assert declared.notation == NOTATION


def test_plain_text_declares_no_notation_and_the_map_says_so():
    assert native_reference_of(facade._plugin("plain_text")) is None
    document = facade.loads(TEXT_SOURCE, format_id="plain_text")
    assert facade.reference_notation(document) is None
    assert all(entry.ref is None and entry.notation is None
               for entry in facade.identifier_map(document).entries())


def test_a_half_written_declaration_is_ignored_rather_than_half_used():
    class NoIndex:
        notation = "made_up"

    class NotAName:
        notation = 42

        def index(self, root):  # pragma: no cover - never reached
            raise AssertionError

    class Plugin:
        pass

    plugin = Plugin()
    plugin.native_reference = NoIndex()
    assert native_reference_of(plugin) is None
    plugin.native_reference = NotAName()
    assert native_reference_of(plugin) is None


# -- the three-way correspondence -------------------------------------------


@pytest.mark.parametrize("format_id, source", TREE_TEMP_FORMATS)
def test_every_identifier_a_tree_temp_node_carries_names_that_same_node(format_id, source):
    document = facade.loads(source, format_id=format_id)
    entries = facade.identifier_map(document).entries()
    assert entries, "a parsed document must index at least one node"
    assert any(entry.ref is not None for entry in entries)
    for entry in entries:
        assert isinstance(entry.node_id, UUID) and entry.short_id >= 1
        assert facade.resolve_address(document, entry.short_id) == entry.node_id
        assert facade.resolve_address(document, hex(entry.short_id)) == entry.node_id
        assert facade.resolve_address(document, str(entry.short_id)) == entry.node_id
        assert facade.resolve_address(document, entry.node_id) == entry.node_id
        assert facade.resolve_address(document, str(entry.node_id)) == entry.node_id
        if entry.ref is not None:
            assert entry.notation == NOTATION
            assert facade.resolve_address(document, entry.ref) == entry.node_id


def test_json_pointers_follow_rfc_6901_over_the_real_parsed_tree():
    document = facade.loads(JSON_SOURCE, format_id="json")
    refs = {entry.ref for entry in facade.identifier_map(document).entries()}
    assert {"", "/a", "/a/0", "/a/1", "/b"} <= refs


def test_yaml_and_toml_reach_the_same_pointers_for_the_same_data():
    yaml_refs = {e.ref for e in facade.identifier_map(
        facade.loads(YAML_SOURCE, format_id="yaml")).entries()}
    json_refs = {e.ref for e in facade.identifier_map(
        facade.loads(JSON_SOURCE, format_id="json")).entries()}
    assert {"", "/a", "/a/0", "/a/1", "/b"} <= yaml_refs
    assert {"", "/a", "/a/0", "/a/1", "/b"} <= json_refs


def test_toml_arrays_of_tables_get_one_pointer_per_occurrence():
    document = facade.loads(TOML_SOURCE, format_id="toml")
    refs = {entry.ref for entry in facade.identifier_map(document).entries()}
    assert {"", "/a", "/a/b", "/c/0", "/c/0/d", "/c/1", "/c/1/d"} <= refs


def test_a_toml_quoted_dotted_key_keeps_its_dot_as_content_not_as_a_separator():
    """``[a."b.c"]`` is two segments, not three: the quoted dot is part of the
    key. A ``str.split('.')`` would silently address a table that does not
    exist, so the split has to be quote-aware."""
    document = facade.loads('[a."b.c"]\nd = 1\n', format_id="toml")
    refs = {entry.ref for entry in facade.identifier_map(document).entries()}
    assert "/a/b.c" in refs and "/a/b.c/d" in refs
    assert facade.resolve_address(document, "/a/b.c/d") == \
           facade.identifiers(document, "/a/b.c/d").node_id


def test_a_json_key_containing_pointer_syntax_is_escaped_per_rfc_6901():
    document = facade.loads('{"a/b": 1, "c~d": 2}', format_id="json")
    refs = {entry.ref for entry in facade.identifier_map(document).entries()}
    assert {"/a~1b", "/c~0d"} <= refs
    assert facade.resolve_address(document, "/a~1b") == \
           facade.identifiers(document, "/a~1b").node_id


def test_a_node_the_notation_cannot_express_reports_no_ref_rather_than_a_fake():
    document = facade.loads("# only a comment\nk = 1\n", format_id="toml")
    by_ref = {entry.short_id: entry.ref
              for entry in facade.identifier_map(document).entries()}
    assert None in by_ref.values(), "the comment node must carry no pointer"
    assert "/k" in by_ref.values()


def test_a_pointer_two_nodes_claim_is_withdrawn_from_both_rather_than_guessed():
    """A duplicated mapping key gives two nodes one pointer. That pointer is not
    an identifier any more, so it is removed from both directions of the index
    and refused on resolution -- never resolved to whichever node was walked
    first."""
    document = facade.loads("a: 1\na: 2\n", format_id="yaml")
    index = facade._plugin("yaml").native_reference.index(document.root)
    assert index.ambiguous == ("/a",)
    assert "/a" not in index.by_pointer
    assert "/a" not in index.by_node.values()
    with pytest.raises(NodeNotFound):
        facade.resolve_address(document, "/a")


def test_an_unknown_reference_is_refused_like_any_other_unknown_address():
    document = facade.loads(JSON_SOURCE, format_id="json")
    with pytest.raises(NodeNotFound):
        facade.resolve_address(document, "/nope")


# -- position independence --------------------------------------------------


def test_plain_text_short_id_survives_an_insert_above_it_while_the_line_moves():
    document = facade.loads(TEXT_SOURCE, format_id="plain_text")
    watched = document.root.children[2]
    before = facade.identifiers(document, watched.node_id)
    line_before = document.root.children.index(watched) + 1

    facade.insert(document, "zero\n", position="first_child", parent=document.root.node_id)

    moved = document.nodes_by_id[before.node_id]
    line_after = document.root.children.index(moved) + 1
    after = facade.identifiers(document, before.short_id)
    assert (before.short_id, before.node_id) == (after.short_id, after.node_id)
    assert line_after == line_before + 1
    assert moved.fields["text"] == "charlie\n"


def test_tree_temp_short_id_survives_an_insert_above_it_while_the_pointer_moves():
    document = facade.loads('{"items": ["alpha", "bravo", "charlie"]}', format_id="json")
    array_id = facade.resolve_address(document, "/items")
    before = facade.identifiers(document, "/items/2")

    facade.insert(document, '"zero"', position="first_child", parent=array_id)

    after = facade.identifiers(document, before.short_id)
    assert (before.short_id, before.node_id) == (after.short_id, after.node_id)
    assert (before.ref, after.ref) == ("/items/2", "/items/3")
    assert document.nodes_by_id[before.node_id].fields["value"] == "charlie"


def test_the_reference_index_is_rebuilt_after_an_edit_rather_than_served_stale():
    document = facade.loads('{"items": ["alpha", "bravo"]}', format_id="json")
    mapping = facade.identifier_map(document)
    charlie = mapping.identifiers("/items/1")
    array_id = mapping.resolve("/items")

    facade.insert(document, '"zero"', position="first_child", parent=array_id)

    assert mapping.ref_for(charlie.node_id) == "/items/2"
    assert mapping.resolve("/items/2") == charlie.node_id


# -- storage round trip -----------------------------------------------------


def test_all_three_identifiers_survive_a_real_save_and_reload():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(JSON_SOURCE, encoding="utf-8")
        opened = facade.open_file(path)
        before = facade.identifier_map(opened.document).entries()
        facade.write(opened.document, path)

        reopened = facade.open_file(path)
        assert reopened.identity_preserved is True
        after = facade.identifier_map(reopened.document).entries()

        assert [(e.short_id, e.node_id, e.ref) for e in before] == \
               [(e.short_id, e.node_id, e.ref) for e in after]
        for entry in after:
            assert facade.resolve_address(reopened.document, entry.short_id) == entry.node_id
            if entry.ref is not None:
                assert facade.resolve_address(reopened.document, entry.ref) == entry.node_id


# -- the display flag -------------------------------------------------------


def test_the_style_flag_changes_only_what_is_reported():
    document = facade.loads(JSON_SOURCE, format_id="json")
    compact = facade.identifiers(document, "/a/1", style=IdentifierStyle.SHORT_ID)
    canonical = facade.identifiers(document, "/a/1", style=IdentifierStyle.NODE_ID)

    assert compact.reported == compact.short_id
    assert canonical.reported == str(canonical.node_id)
    assert compact.reported != canonical.reported
    assert (compact.node_id, compact.short_id, compact.ref, compact.notation) == \
           (canonical.node_id, canonical.short_id, canonical.ref, canonical.notation)


def test_short_id_is_the_default_style():
    document = facade.loads(JSON_SOURCE, format_id="json")
    assert facade.identifier_map(document).style is IdentifierStyle.SHORT_ID
    assert facade.node_identifier(document, "/a/1") == facade.identifiers(document, "/a/1").short_id


@pytest.mark.parametrize("style", [IdentifierStyle.SHORT_ID, IdentifierStyle.NODE_ID,
                                   "short_id", "node_id"])
def test_every_input_form_is_accepted_under_every_style(style):
    document = facade.loads(JSON_SOURCE, format_id="json")
    mapping = facade.identifier_map(document, style=style)
    target = mapping.identifiers("/a/1")
    resolved = {mapping.resolve(form) for form in (
        target.short_id, hex(target.short_id), str(target.short_id),
        target.node_id, str(target.node_id), target.ref)}
    assert resolved == {target.node_id}


def test_with_style_returns_a_second_view_without_changing_the_first():
    document = facade.loads(JSON_SOURCE, format_id="json")
    compact = facade.identifier_map(document)
    canonical = compact.with_style(IdentifierStyle.NODE_ID)
    assert compact.style is IdentifierStyle.SHORT_ID
    assert canonical.style is IdentifierStyle.NODE_ID
    assert isinstance(compact, IdentifierMap) and isinstance(canonical, IdentifierMap)


def test_node_identifiers_with_style_keeps_the_other_three_fields():
    entry = NodeIdentifiers(node_id=UUID(int=4, version=4), short_id=7, ref="/a",
                            notation=NOTATION)
    switched = entry.with_style(IdentifierStyle.NODE_ID)
    assert switched.reported == str(entry.node_id)
    assert (switched.node_id, switched.short_id, switched.ref, switched.notation) == \
           (entry.node_id, entry.short_id, entry.ref, entry.notation)


def test_node_ref_and_reference_notation_expose_the_third_slot_directly():
    document = facade.loads(JSON_SOURCE, format_id="json")
    assert facade.node_ref(document, "/a/0") == "/a/0"
    assert facade.reference_notation(document) == NOTATION
    assert facade.node_ref(facade.loads(TEXT_SOURCE, format_id="plain_text"), 2) is None
