"""Unit tests for the C-003 extension node types (tree_engine.core.node_types).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: construction and round-trip behavior of ``PreprocessorDirectiveNode``,
``AnnotationNode``, ``VariableDeclaratorNode`` and ``VariableDeclarationNode``
-- identity/range/content fields at construction, addressing via node_id/
short_id, copy/move semantics, serialize round-trip (via ``to_dict``/
``from_dict``), declarator order and separator preservation, and traversal
of extension nodes through the base ``iter_children``/``walk`` helpers.

Out of scope for this file (covered by a sibling unit): the ``export``
field, ``set_attribute``/``matches`` (search-predicate) behavior, and
index-map propagation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tree_engine.core.node_types import (
    AnnotationNode,
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.nodes import NodeSchemaError, iter_children, make_node, walk


class TestPreprocessorDirectiveNode:
    def test_construction_identity_and_range(self) -> None:
        content = "#If Сервер Then"
        node = PreprocessorDirectiveNode(start_byte=10, end_byte=10 + len(content), content=content)

        assert isinstance(node.node_id, UUID)
        assert node.node_id.version == 4
        assert isinstance(node.short_id, str) and node.short_id
        assert node.parent_id is None
        assert node.byte_range == (10, 10 + len(content))
        assert node.content == content

    def test_parent_id_settable_at_construction(self) -> None:
        parent = uuid4()
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=5, content="#Если", parent_id=parent)
        assert node.parent_id == parent

    def test_no_directive_specific_fields_or_substructure(self) -> None:
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=10, content="#КонецЕсли")
        assert node.node.kind == "core:preprocessor_directive"
        assert set(node.node.fields.keys()) == {"content"}
        assert node.node.children == ()

    def test_copy_preserves_content_and_range(self) -> None:
        original = PreprocessorDirectiveNode(start_byte=3, end_byte=13, content="#Область X")
        copy = original.copy()

        assert copy is not original
        assert copy.content == original.content
        assert copy.byte_range == original.byte_range
        # `copy()` wraps the same immutable base `Node`, so identity travels
        # with it rather than being reassigned: see module note in the
        # final report about this diverging from a new-identity reading.
        assert copy.node_id != original.node_id
        assert copy.short_id != original.short_id
        assert original.copy(preserve_ids=True).node_id == original.node_id

    def test_move_updates_parent_id_only(self) -> None:
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=8, content="#Вставка")
        node_id_before = node.node_id
        content_before = node.content
        new_parent = uuid4()

        moved = node.move_to(new_parent)

        assert moved is node
        assert node.parent_id == new_parent
        assert node.node_id == node_id_before
        assert node.content == content_before

    def test_serialize_round_trip_preserves_content_and_range(self) -> None:
        content = "#Если Не ВебКлиент Тогда"
        node = PreprocessorDirectiveNode(start_byte=100, end_byte=100 + len(content), content=content)

        rebuilt = PreprocessorDirectiveNode.from_dict(node.to_dict())

        assert rebuilt.content == node.content
        assert rebuilt.byte_range == node.byte_range
        assert rebuilt.node_id == node.node_id

    def test_core_neutral_no_directive_semantics_on_operations(self) -> None:
        # store/copy/move/serialize accept arbitrary, even malformed-looking
        # preprocessor text verbatim: no parsing, branch-boundary
        # computation, or semantic interpretation happens anywhere.
        weird_content = "#If garbage ~~~ not valid BSL preprocessor syntax {{{"
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=1, content=weird_content)

        rebuilt = PreprocessorDirectiveNode.from_dict(node.copy().move_to(uuid4()).to_dict())

        assert rebuilt.content == weird_content
        assert set(rebuilt.node.fields.keys()) == {"content"}
        assert rebuilt.node.children == ()

    def test_traversal_via_base_helpers(self) -> None:
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=5, content="#Тест")
        assert list(iter_children(node.node)) == []
        assert list(walk(node.node)) == [node.node]


class TestAnnotationNode:
    def test_construction_identity_range_and_content(self) -> None:
        content = "&НаСервере"
        node = AnnotationNode(start_byte=0, end_byte=len(content), content=content)

        assert isinstance(node.node_id, UUID) and node.node_id.version == 4
        assert node.short_id
        assert node.byte_range == (0, len(content))
        assert node.content == content
        assert node.arguments == ()
        assert node.argument_separators == []

    def test_distinct_type_from_preprocessor_directive(self) -> None:
        annotation = AnnotationNode(start_byte=0, end_byte=1, content="&AtServer")
        directive = PreprocessorDirectiveNode(start_byte=0, end_byte=1, content="#If")

        assert type(annotation) is not type(directive)
        assert annotation.node.kind != directive.node.kind
        assert annotation.node.kind == "core:annotation"

    def test_construction_with_argument_children_and_separators(self) -> None:
        arg1 = make_node("core:value", fields={"content": "Значение1"})
        arg2 = make_node("core:value", fields={"content": "Значение2"})
        node = AnnotationNode(
            start_byte=0, end_byte=36, content='&НаСервере("Значение1", "Значение2")',
            arguments=(arg1, arg2), argument_separators=(", ",),
        )

        assert node.arguments == (arg1, arg2)
        assert node.argument_separators == [", "]
        assert node.node.children == (arg1, arg2)

    def test_parent_id_settable_at_construction(self) -> None:
        parent = uuid4()
        node = AnnotationNode(start_byte=0, end_byte=1, content="&X", parent_id=parent)
        assert node.parent_id == parent

    def test_copy_preserves_arguments_order_and_content(self) -> None:
        arg1 = make_node("core:value", fields={"content": "a"})
        arg2 = make_node("core:value", fields={"content": "b"})
        original = AnnotationNode(
            start_byte=0, end_byte=10, content="&X(a, b)",
            arguments=(arg1, arg2), argument_separators=(", ",),
        )

        copy = original.copy()

        assert copy.arguments == original.arguments
        assert copy.argument_separators == original.argument_separators
        assert copy.content == original.content
        assert copy.byte_range == original.byte_range

    def test_move_updates_parent_id_only(self) -> None:
        node = AnnotationNode(start_byte=0, end_byte=2, content="&Y")
        node_id_before = node.node_id
        content_before = node.content

        moved = node.move_to(uuid4())

        assert moved.node_id == node_id_before
        assert moved.content == content_before

    def test_serialize_round_trip_preserves_content_and_range(self) -> None:
        content = "&НаКлиенте"
        node = AnnotationNode(start_byte=5, end_byte=5 + len(content), content=content)

        rebuilt = AnnotationNode.from_dict(node.to_dict())

        assert rebuilt.content == node.content
        assert rebuilt.byte_range == node.byte_range

    def test_argument_children_round_trip_preserves_order_and_content(self) -> None:
        arg1 = make_node("core:value", fields={"content": "первый"})
        arg2 = make_node("core:value", fields={"content": "второй"})
        arg3 = make_node("core:value", fields={"content": "третий"})
        original = AnnotationNode(
            start_byte=0, end_byte=40, content='&НаСервере("первый", "второй", "третий")',
            arguments=(arg1, arg2, arg3), argument_separators=(", ", ", "),
        )

        rebuilt = AnnotationNode.from_dict(original.to_dict())

        assert rebuilt.arguments == (arg1, arg2, arg3)
        assert [a.fields["content"] for a in rebuilt.arguments] == ["первый", "второй", "третий"]
        assert rebuilt.argument_separators == [", ", ", "]

    def test_traversal_walks_argument_children_in_order(self) -> None:
        arg1 = make_node("core:value", fields={"content": "a"})
        arg2 = make_node("core:value", fields={"content": "b"})
        node = AnnotationNode(
            start_byte=0, end_byte=1, content="&X",
            arguments=(arg1, arg2), argument_separators=(",",),
        )

        assert list(iter_children(node.node)) == [arg1, arg2]
        assert list(walk(node.node)) == [node.node, arg1, arg2]


class TestVariableDeclarationNode:
    def test_construction_with_ordered_declarators_and_separators(self) -> None:
        a = VariableDeclaratorNode(start_byte=6, end_byte=7, content="a", name="a")
        b = VariableDeclaratorNode(start_byte=9, end_byte=10, content="b", name="b")
        c = VariableDeclaratorNode(start_byte=12, end_byte=13, content="c", name="c")

        decl = VariableDeclarationNode(
            start_byte=0, end_byte=13, content="Перем a, b, c",
            declarators=(a, b, c), separators=(", ", ", "),
        )

        assert [d.name for d in decl.declarators] == ["a", "b", "c"]
        assert decl.separators == [", ", ", "]
        assert decl.content == "Перем a, b, c"
        assert decl.byte_range == (0, 13)
        assert isinstance(decl.node_id, UUID) and decl.node_id.version == 4

    def test_declarator_order_and_separators_survive_round_trip(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a")
        b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="b", name="b")
        decl = VariableDeclarationNode(
            start_byte=0, end_byte=4, content="a, b", declarators=(a, b), separators=(", ",),
        )

        rebuilt = VariableDeclarationNode.from_dict(decl.to_dict())

        assert [d.name for d in rebuilt.declarators] == ["a", "b"]
        assert [d.byte_range for d in rebuilt.declarators] == [(0, 1), (3, 4)]
        assert rebuilt.separators == [", "]
        assert rebuilt.content == decl.content

    def test_separator_count_mismatch_raises(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a")
        b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="b", name="b")

        with pytest.raises(NodeSchemaError):
            VariableDeclarationNode(start_byte=0, end_byte=4, content="a, b", declarators=(a, b), separators=())

    def test_single_declarator_needs_no_separators(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a")
        decl = VariableDeclarationNode(start_byte=0, end_byte=1, content="a", declarators=(a,), separators=())

        assert decl.separators == []
        assert [d.name for d in decl.declarators] == ["a"]

    def test_copy_preserves_declarator_order_and_content(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="x", name="x")
        b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="y", name="y")
        original = VariableDeclarationNode(
            start_byte=0, end_byte=4, content="x, y", declarators=(a, b), separators=(", ",),
        )

        copy = original.copy()

        assert [d.name for d in copy.declarators] == ["x", "y"]
        assert copy.separators == original.separators
        assert copy.content == original.content
        assert copy.byte_range == original.byte_range
        assert copy.node_id != original.node_id

    def test_move_updates_parent_id_only_and_preserves_declarator_order(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="p", name="p")
        b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="q", name="q")
        decl = VariableDeclarationNode(
            start_byte=0, end_byte=4, content="p, q", declarators=(a, b), separators=(", ",),
        )
        node_id_before = decl.node_id

        moved = decl.move_to(uuid4())

        assert moved.node_id == node_id_before
        assert [d.name for d in moved.declarators] == ["p", "q"]

    def test_traversal_walks_declarator_children_in_order(self) -> None:
        a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a")
        b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="b", name="b")
        decl = VariableDeclarationNode(
            start_byte=0, end_byte=4, content="a, b", declarators=(a, b), separators=(", ",),
        )

        assert list(iter_children(decl.node)) == [a.node, b.node]
        assert list(walk(decl.node)) == [decl.node, a.node, b.node]


class TestVariableDeclaratorNode:
    def test_construction_identity_range_and_name(self) -> None:
        declarator = VariableDeclaratorNode(start_byte=6, end_byte=7, content="а", name="а")

        assert isinstance(declarator.node_id, UUID) and declarator.node_id.version == 4
        assert declarator.short_id
        assert declarator.byte_range == (6, 7)
        assert declarator.content == "а"
        assert declarator.name == "а"
        assert declarator.node.kind == "core:variable_declarator"

    def test_addressing_by_node_id_and_short_id_after_composition(self) -> None:
        declarator = VariableDeclaratorNode(start_byte=0, end_byte=1, content="v", name="v")
        decl = VariableDeclarationNode(
            start_byte=0, end_byte=1, content="v", declarators=(declarator,), separators=(),
            parent_id=uuid4(),
        )

        child = decl.declarators[0]
        assert child.node_id == declarator.node_id
        assert child.short_id == declarator.short_id

        # The base `Node` contract keeps no parent back-reference (bottom-up
        # immutable construction); `parent_id` is wrapper bookkeeping the
        # caller assigns explicitly after composition, and it resolves back
        # to the owning declaration's node_id.
        child.parent_id = decl.node_id
        assert child.parent_id == decl.node_id

    def test_copy_and_move(self) -> None:
        declarator = VariableDeclaratorNode(start_byte=0, end_byte=1, content="z", name="z")

        copy = declarator.copy()
        assert copy.node_id != declarator.node_id
        assert copy.name == declarator.name

        moved = declarator.move_to(uuid4())
        assert moved.node_id == declarator.node_id
        assert moved.content == declarator.content
