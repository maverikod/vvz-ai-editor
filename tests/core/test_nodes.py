"""Unit tests for the C-002 common node/document schema (tree_engine.core.nodes).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: format-independent tests only. No I/O, no format plugins, no LibCST
imports -- everything here is built directly from ``tree_engine.core.nodes``.
"""

from __future__ import annotations

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk


def test_node_construction_sets_kind_and_fields() -> None:
    child_a = make_node("python:Name", fields={"value": "a"})
    child_b = make_node("python:Name", fields={"value": "b"})

    node = make_node(
        "python:FunctionDef",
        fields={
            "name": "greet",
            "body": (child_a, child_b),
            "trivia": "    ",
            "comment": "# a greeting function",
        },
    )

    assert node.kind == "python:FunctionDef"
    assert isinstance(node.fields["name"], str)
    assert node.fields["name"] == "greet"
    assert node.fields["body"] == (child_a, child_b)
    assert all(isinstance(item, Node) for item in node.fields["body"])
    assert node.fields["trivia"] == "    "
    assert node.fields["comment"] == "# a greeting function"

    # Fields never explicitly supplied are documented reserved extension
    # slots on Node itself (not entries silently added to `fields`); they
    # carry their documented defaults rather than being coerced or dropped.
    assert node.node_id is None
    assert node.short_id is None
    assert node.extended_type is None
    assert node.buffer_range is None
    assert node.references == ()
    assert "name" not in make_node("python:Pass").fields


def test_node_typed_field_access() -> None:
    detail = make_node("python:TypeAnnotation", fields={"value": "int"})
    node = make_node(
        "python:Param",
        fields={
            "name": "count",  # scalar
            "decorators": (),  # ordered sequence (empty is still a tuple)
            "flags": (
                make_node("python:Flag", fields={"value": "positional"}),
                make_node("python:Flag", fields={"value": "keyword"}),
            ),  # ordered sequence, non-empty
            "annotation": detail,  # format-detail (single Node)
        },
    )

    assert node.fields["name"] == "count"
    assert isinstance(node.fields["name"], str)

    assert node.fields["decorators"] == ()
    assert isinstance(node.fields["decorators"], tuple)

    assert isinstance(node.fields["flags"], tuple)
    assert len(node.fields["flags"]) == 2
    assert all(isinstance(item, Node) for item in node.fields["flags"])

    assert node.fields["annotation"] is detail
    assert isinstance(node.fields["annotation"], Node)

    with pytest.raises(KeyError):
        node.fields["does_not_exist"]


def test_node_child_sequence_ordering_preserved() -> None:
    children = (
        make_node("python:Name", fields={"value": "one"}),
        make_node("python:Num", fields={"value": 2}),
        make_node("python:Str", fields={"value": "three"}),
        make_node("python:Name", fields={"value": "four"}),
    )

    node = make_node("python:Tuple", children=children)

    assert tuple(node.children) == children
    for index, expected in enumerate(children):
        assert node.children[index] is expected

    kinds_in_order = [child.kind for child in node.children]
    assert kinds_in_order == [
        "python:Name",
        "python:Num",
        "python:Str",
        "python:Name",
    ]

    # `children` is a real tuple: any "view" obtained from it is a fresh
    # copy, so mutating that copy cannot alter the node.
    mutable_copy = list(node.children)
    mutable_copy.append(make_node("python:Name", fields={"value": "intruder"}))
    assert len(node.children) == 4
    assert tuple(node.children) == children

    with pytest.raises(TypeError):
        node.children[0] = children[1]  # type: ignore[index]


def test_node_traversal_walks_children_in_order() -> None:
    leaf_1 = make_node("python:Name", fields={"value": "leaf1"})
    leaf_2 = make_node("python:Name", fields={"value": "leaf2"})
    leaf_3 = make_node("python:Name", fields={"value": "leaf3"})

    branch_left = make_node("python:Tuple", children=(leaf_1, leaf_2))
    branch_right = make_node("python:Tuple", children=(leaf_3,))

    root = make_node("python:Module", children=(branch_left, branch_right))

    visited = list(walk(root))

    assert visited == [root, branch_left, leaf_1, leaf_2, branch_right, leaf_3]
    # Every descendant visited exactly once.
    assert len(visited) == len(set(id(n) for n in visited))


def test_document_default_format_id_matches_source() -> None:
    root = make_node("python:Module")

    document = Document(
        root=root,
        source_format_id="python",
        representation_format_id="python",
    )

    assert document.representation_format_id == document.source_format_id
    assert document.format_id == "python"
    assert document.format_id == document.representation_format_id


def test_document_plain_text_fallback_preserves_source_format_id() -> None:
    root = make_node("python:Module")

    document = Document(
        root=root,
        source_format_id="python",
        representation_format_id="python",
    )

    # Simulate the plain-text fallback transition: only the working
    # representation changes, the originally selected format is retained.
    document.representation_format_id = "plain_text"

    assert document.representation_format_id == "plain_text"
    assert document.source_format_id == "python"
    assert document.format_id == "plain_text"


def test_reserved_extension_slots_are_inert_by_default() -> None:
    node = make_node("python:Pass")

    assert node.node_id is None
    assert node.short_id is None
    assert node.extended_type is None
    assert node.buffer_range is None
    assert node.references == ()

    document = Document(
        root=node,
        source_format_id="python",
        representation_format_id="python",
    )
    assert document.document_id is None

    # Reading these slots on a fresh node/document has no side effect: the
    # node/document are unchanged and remain usable afterward.
    assert node.kind == "python:Pass"
    assert document.root is node
