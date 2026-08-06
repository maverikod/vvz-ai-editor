"""Unit tests for the C-015 import direction of the BSL translator
(tree_engine.plugins.bsl.import_map).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``BSLImportMap.import_to_common``/``import_to_common``
against real tree-sitter-bsl 0.1.6 parses -- no fabricated trees. Every
sample uses a fresh ``tree_sitter.Parser`` (reusing one instance across
parses has been observed to silently corrupt byte offsets with this
tree-sitter/grammar combination). Covers: variable_declaration/
variable_declarator (single/multi-declarator, both dialects), the export
boolean field, preprocessor_directive vs. annotation (never merged), the
by-value (Знач/Val) parameter modifier, exact byte ranges/order for every
mapped node kind, the extensible fallback for unmapped constructs, one
translator handling both dialects (plus a mixed-dialect document), the
has_error parse-failure backstop for both classifications, and an
end-to-end round trip through the already-merged BSL generator.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from tree_sitter import Language, Parser
import tree_sitter_bsl

from tree_engine.core.node_types import (
    AnnotationNode,
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.nodes import Node, walk
from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl import dialects
from tree_engine.plugins.bsl import generator as bsl_generator
from tree_engine.plugins.bsl.import_map import BSLImportMap, import_to_common
from tree_engine.plugins.contract import FormatPluginContractError

# Node kinds whose own ``.children`` deliberately restructures the
# tree-sitter subtree (declarators, annotation arguments) rather than
# mirroring ``ts_node.children`` 1:1 -- see ``_assert_matches_source``.
_RESTRUCTURED_KINDS = {
    VariableDeclarationNode._KIND,
    AnnotationNode._KIND,
    PreprocessorDirectiveNode._KIND,
}


def _fresh_parser() -> Parser:
    """A brand-new ``Parser`` per call -- reuse corrupts byte offsets."""

    return Parser(Language(tree_sitter_bsl.language()))


def _parse(source: str):
    """Parse ``source`` with a fresh parser; return ``(root_node, bytes)``."""

    data = source.encode("utf-8")
    return _fresh_parser().parse(data).root_node, data


def _find_ts(ts_node, node_type: str):
    """First descendant (pre-order, self included) of ``node_type``."""

    if ts_node.type == node_type:
        return ts_node
    for child in ts_node.children:
        found = _find_ts(child, node_type)
        if found is not None:
            return found
    return None


def _first_common(root: Node, kind: str) -> Node:
    return next(n for n in walk(root) if n.kind == kind)


def _all_common(root: Node, kind: str):
    return [n for n in walk(root) if n.kind == kind]


def _assert_matches_source(ts_node, node: Node, source: bytes) -> None:
    """Recursively assert ``node``'s byte range mirrors ``ts_node``'s
    exactly, and that -- for every kind but the three restructured ones --
    ``content`` is the exact source slice and children are a 1:1,
    order-preserving mirror of ``ts_node.children``, all the way down."""

    assert node.buffer_range == (ts_node.start_byte, ts_node.end_byte)
    if node.kind in _RESTRUCTURED_KINDS:
        return
    assert node.fields.get("content") == source[ts_node.start_byte : ts_node.end_byte].decode("utf-8")
    assert len(node.children) == len(ts_node.children)
    for ts_child, child in zip(ts_node.children, node.children):
        _assert_matches_source(ts_child, child, source)


def test_variable_declaration_mapping() -> None:
    """Module-level (var_definition) and in-procedure (var_statement)
    declarations, single/multi-declarator, both dialects: one
    core:variable_declaration node with ordered core:variable_declarator
    children -- never an assignment node."""

    for source, names, _dialect in [
        ("Перем А, Б;\n", ["А", "Б"], dialects.RUSSIAN),
        ("Var A, B;\n", ["A", "B"], dialects.ENGLISH),
    ]:
        root, data = _parse(source)
        ts_var = _find_ts(root, "var_definition")
        node = BSLImportMap().import_to_common(root)
        var_node = _first_common(node, VariableDeclarationNode._KIND)

        assert var_node.buffer_range == (ts_var.start_byte, ts_var.end_byte)
        assert isinstance(var_node.node_id, UUID)
        assert isinstance(var_node.short_id, int) and var_node.short_id > 0

        wrapped = VariableDeclarationNode.from_node(var_node)
        assert [d.name for d in wrapped.declarators] == names
        assert len(wrapped.separators) == 1
        # Exact original inter-declarator bytes (", "), not a synthesized default.
        assert wrapped.separators[0] == data[ts_var.children[1].end_byte : ts_var.children[3].start_byte].decode("utf-8")
        for declarator in wrapped.declarators:
            assert isinstance(declarator.node_id, UUID)
            assert declarator.export is False  # never propagated from the parent

    # In-procedure, single-declarator: no separators, and the declaration is
    # a direct child of the enclosing (generic) procedure -- scope membership.
    root, _data = _parse("Процедура П()\n\tПерем В;\nКонецПроцедуры\n")
    node = import_to_common(root)
    proc_node = _first_common(node, "bsl:procedure_definition")
    var_node = _first_common(node, VariableDeclarationNode._KIND)
    assert var_node in proc_node.children
    wrapped = VariableDeclarationNode.from_node(var_node)
    assert wrapped.declarators[0].name == "В"
    assert wrapped.separators == []


def test_export_boolean_field() -> None:
    """Экспорт/Export maps to the export boolean field, present or absent,
    both dialects; readable via get_attribute, mutable via set_attribute,
    visible to matches() search predicates, and surviving a copy()."""

    for with_export, without_export, _dialect in [
        ("Перем А Экспорт;\n", "Перем А;\n", dialects.RUSSIAN),
        ("Var A Export;\n", "Var A;\n", dialects.ENGLISH),
    ]:
        root_yes, _ = _parse(with_export)
        root_no, _ = _parse(without_export)
        node_yes = _first_common(import_to_common(root_yes), VariableDeclarationNode._KIND)
        node_no = _first_common(import_to_common(root_no), VariableDeclarationNode._KIND)

        wrapped_yes = VariableDeclarationNode.from_node(node_yes)
        wrapped_no = VariableDeclarationNode.from_node(node_no)
        assert wrapped_yes.export is True and wrapped_no.export is False
        assert wrapped_yes.get_attribute("export") is True
        assert wrapped_no.get_attribute("export") is False
        assert wrapped_yes.matches(export=True) is True
        assert wrapped_no.matches(export=True) is False

        wrapped_no.set_attribute("export", True)
        assert wrapped_no.export is True
        wrapped_no.set_attribute("export", False)
        assert wrapped_no.export is False

        copied = wrapped_yes.copy()  # persistence across a subsequent operation
        assert copied.export is True
        assert copied.node_id != wrapped_yes.node_id


def test_preprocessor_directive_mapping() -> None:
    """A preprocessor node with no nested annotation child (#Если/#If ..
    #КонецЕсли/#EndIf) maps flat to core:preprocessor_directive, in source
    order, both dialects, with exact byte ranges, UUID4/short_id identity,
    and no directive-specific interpretation by the core."""

    for source, _dialect in [
        ("#Если Сервер Тогда\nПроцедура П()\nКонецПроцедуры\n#КонецЕсли\n", dialects.RUSSIAN),
        ("#If Server Then\nProcedure P()\nEndProcedure\n#EndIf\n", dialects.ENGLISH),
    ]:
        root, data = _parse(source)
        root_node = import_to_common(root)
        directives = _all_common(root_node, PreprocessorDirectiveNode._KIND)
        ts_directives = [c for c in root.children if c.type == "preprocessor"]
        assert len(directives) == len(ts_directives) == 2

        for ts_node, node in zip(ts_directives, directives):
            assert node.buffer_range == (ts_node.start_byte, ts_node.end_byte)
            assert node.fields.get("content") == data[ts_node.start_byte : ts_node.end_byte].decode("utf-8")
            wrapped = PreprocessorDirectiveNode.from_node(node)
            assert isinstance(wrapped.node_id, UUID)
            assert isinstance(wrapped.short_id, int) and wrapped.short_id > 0
            assert wrapped.export is False  # inapplicable (rejecting form)

        # Order preserved among the root's own direct children (identity,
        # not equality, since two directives could otherwise be equal-but-
        # distinct nodes).
        positions = [next(i for i, c in enumerate(root_node.children) if c is d) for d in directives]
        assert positions == sorted(positions)


def test_annotation_node_mapping() -> None:
    """A preprocessor node wrapping a nested annotation child (&НаСервере/
    &AtServer) maps to a standalone core:annotation node keyed to the
    *inner* node's own byte range -- distinct from preprocessor_directive --
    with UUID4, short_id, recognized annotation_kind, optional (here absent)
    child arguments, and normal participation in tree walking."""

    for source, _dialect in [
        ("&НаСервере\nПроцедура П()\nКонецПроцедуры\n", dialects.RUSSIAN),
        ("&AtServer\nProcedure P()\nEndProcedure\n", dialects.ENGLISH),
    ]:
        root, data = _parse(source)
        ts_outer = _find_ts(root, "preprocessor")
        ts_inner = _find_ts(ts_outer, "annotation")
        node = import_to_common(root)

        annotations = _all_common(node, AnnotationNode._KIND)
        assert len(annotations) == 1
        assert _all_common(node, PreprocessorDirectiveNode._KIND) == []

        annotation = annotations[0]
        # Keyed to the inner node's own range, not the outer wrapper's.
        assert annotation.buffer_range == (ts_inner.start_byte, ts_inner.end_byte)
        assert annotation.fields.get("content") == data[ts_inner.start_byte : ts_inner.end_byte].decode("utf-8")
        assert annotation.fields.get("annotation_kind") == dialects.AT_SERVER

        wrapped = AnnotationNode.from_node(annotation)
        assert isinstance(wrapped.node_id, UUID)
        assert isinstance(wrapped.short_id, int) and wrapped.short_id > 0
        assert wrapped.arguments == ()
        assert wrapped.export is False

        # The AnnotationNode substitutes for the whole preprocessor subtree
        # at that tree position -- no "bsl:preprocessor" wrapper survives.
        assert not any(n.kind == "bsl:preprocessor" for n in walk(node))
        assert annotation in walk(node)
        assert annotation in node.children


def test_parameter_by_value_modifier() -> None:
    """Знач/Val on a procedure parameter is recognized in both dialects
    (by token text, never tree-sitter node-kind), sets by_value=True
    readable via get_attribute, and is absent (no key) without it."""

    for source, _dialect in [
        ("Процедура П(Знач А, Б)\nКонецПроцедуры\n", dialects.RUSSIAN),
        ("Procedure P(Val A, B)\nEndProcedure\n", dialects.ENGLISH),
    ]:
        root, _data = _parse(source)
        params = _all_common(import_to_common(root), "bsl:parameter")
        assert len(params) == 2

        with_modifier, without_modifier = params
        assert with_modifier.fields.get(dialects.BY_VALUE) is True
        assert dialects.BY_VALUE not in without_modifier.fields
        # Original written form kept verbatim (never stripped/canonicalized).
        assert with_modifier.fields["content"].split()[0] in ("Знач", "Val")


def test_byte_range_and_order_preservation() -> None:
    """Across a document combining an annotation, a leading comment, an
    exported procedure with a by-value parameter, and an in-procedure
    variable declaration: every generic/parameter node's byte range,
    content and child order mirror tree-sitter's own parse exactly, in
    both dialects; comments survive as ordinary generic nodes."""

    for source, _dialect in [
        (
            "&НаСервере\n// leading comment\nПроцедура П(Знач А, Б) Экспорт\n"
            "\tПерем В, Г;\nКонецПроцедуры\n",
            dialects.RUSSIAN,
        ),
        (
            "&AtServer\n// leading comment\nProcedure P(Val A, B) Export\n"
            "\tVar C, D;\nEndProcedure\n",
            dialects.ENGLISH,
        ),
    ]:
        root, data = _parse(source)
        node = import_to_common(root)
        assert node.buffer_range == (0, len(data))
        _assert_matches_source(root, node, data)

        comments = _all_common(node, "bsl:line_comment")
        assert len(comments) == 1
        assert comments[0].fields["content"] == "// leading comment"


def test_extensible_node_mapping() -> None:
    """A tree-sitter-bsl kind with no explicit rule (procedure_definition,
    function_definition, return_statement, identifier, ...) becomes a
    plain bsl:<node type> node with its own raw byte span and exact
    content, no synthetic wrapper -- recursively, so a mapped construct
    nested inside one is still recognized by the same dispatch."""

    root, data = _parse("Функция Ф() Экспорт\n\tВозврат 1;\nКонецФункции\n")
    node = import_to_common(root)

    assert node.kind == "bsl:source_file"
    func_node = _first_common(node, "bsl:function_definition")
    assert func_node.fields["content"] == data.decode("utf-8").rstrip("\n")
    # A generic node still carries UUID4 identity {p013} and short_id {p097}.
    assert isinstance(func_node.node_id, UUID) and func_node.short_id > 0

    return_node = _first_common(node, "bsl:return_statement")
    assert return_node.fields["content"] == "Возврат 1;"

    # export at function level maps via EXPORT_KEYWORD detection even though
    # function_definition itself is generic -- no variable_declaration exists
    # here, so none is invented.
    assert not _all_common(node, VariableDeclarationNode._KIND)


def test_dialect_parity() -> None:
    """Russian and English sources of matching structure produce
    structurally identical trees (kinds, child counts, field keys,
    ignoring literal spelling) through the single dialect-agnostic
    import_to_common path; a document mixing both dialects across two
    constructs is accepted by that same single translator in one call."""

    def shape(n: Node):
        return (
            str(n.kind),
            tuple(sorted(k for k in n.fields if k != "content")),
            tuple(shape(c) for c in n.children),
        )

    ru_root, _ = _parse("Процедура П(Знач А)\n\tПерем Б;\nКонецПроцедуры\n")
    en_root, _ = _parse("Procedure P(Val A)\n\tVar B;\nEndProcedure\n")
    assert shape(import_to_common(ru_root)) == shape(import_to_common(en_root))

    # One translator call, one document, both dialects at once.
    mixed_root, _ = _parse("Перем А;\nProcedure P(Val B)\nEndProcedure\n")
    mixed = import_to_common(mixed_root)
    var_node = _first_common(mixed, VariableDeclarationNode._KIND)
    assert VariableDeclarationNode.from_node(var_node).declarators[0].name == "А"
    params = _all_common(mixed, "bsl:parameter")
    assert params[0].fields.get(dialects.BY_VALUE) is True


def test_error_classification() -> None:
    """Damaged source (unterminated parameter list -> ERROR/MISSING
    descendants, has_error root) makes import_to_common refuse to
    synthesize a partial tree: FormatPluginContractError with
    FORMAT_CONTENT_PARSE_FAILED for a document and
    FORMAT_FRAGMENT_PARSE_FAILED for fragment=True -- module function and
    class method alike, never a partial Node."""

    root, _data = _parse("Процедура П(\nКонецПроцедуры\n")
    assert root.has_error is True

    with pytest.raises(FormatPluginContractError) as excinfo:
        import_to_common(root)
    assert excinfo.value.plugin_id == "bsl"
    assert excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED

    with pytest.raises(FormatPluginContractError) as excinfo_fragment:
        import_to_common(root, fragment=True)
    assert excinfo_fragment.value.error_code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED

    with pytest.raises(FormatPluginContractError):
        BSLImportMap().import_to_common(root)

    good_root, _ = _parse("Процедура П()\nКонецПроцедуры\n")  # sanity: valid input still imports
    assert isinstance(import_to_common(good_root), Node)


def test_round_trip_verification() -> None:
    """For every construct this module singles out (module/procedure-level
    variable declaration, export, annotation, preprocessor directive,
    by-value parameter), both dialects: import -> export_from_common ->
    generate_output reproduces the original bytes exactly, and reparsing
    that output with a fresh parser yields zero errors."""

    samples = [
        ("Перем А, Б Экспорт;\n", dialects.RUSSIAN),
        ("Var A, B Export;\n", dialects.ENGLISH),
        ("Процедура П()\n\tПерем А, Б;\nКонецПроцедуры\n", dialects.RUSSIAN),
        ("Procedure P()\n\tVar A, B;\nEndProcedure\n", dialects.ENGLISH),
        ("&НаСервере\nПроцедура П()\nКонецПроцедуры\n", dialects.RUSSIAN),
        ("&AtServer\nProcedure P()\nEndProcedure\n", dialects.ENGLISH),
        ("#Если Сервер Тогда\nПроцедура П()\nКонецПроцедуры\n#КонецЕсли\n", dialects.RUSSIAN),
        ("#If Server Then\nProcedure P()\nEndProcedure\n#EndIf\n", dialects.ENGLISH),
        ("Процедура П(Знач А, Б)\nКонецПроцедуры\n", dialects.RUSSIAN),
        ("Procedure P(Val A, B)\nEndProcedure\n", dialects.ENGLISH),
        ("Функция Ф() Экспорт\n\tВозврат 1;\nКонецФункции\n", dialects.RUSSIAN),
    ]
    for source, dialect in samples:
        root, data = _parse(source)
        node = import_to_common(root)

        generation_tree = bsl_generator.export_from_common(node, options={"dialect": dialect})
        output = bsl_generator.generate_output(generation_tree)
        assert output == data

        reparsed = _fresh_parser().parse(output).root_node
        assert reparsed.has_error is False
