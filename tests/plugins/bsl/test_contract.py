"""Full BSL format-plugin contract test suite (concept C-015, step
G-007/T-001/A-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.bsl.plugin.BSLFormatPlugin`` -- the
registered ``format_id="bsl"`` plugin's actual entry points
(``parse_document``, ``parse_fragment``, ``export_from_common``,
``generate_output``, ``semantic_role_mapping``) -- against real
tree_sitter_bsl 0.1.6 parses of real BSL/1C source, in both keyword
dialects. No fabricated trees, no registry, no selection resolver.

A brand-new ``tree_sitter.Parser`` is built for every single parse (see
:func:`_fresh_root`); reusing one instance across parses has been
observed, with this tree-sitter/grammar combination, to silently corrupt
byte offsets on the second and later parses.

Covered: (1) byte-exact round trips for a Russian-keyword function
(export, annotation, preprocessor directive, ``Знач`` parameters, a
comment, a variable declaration) and an English-keyword procedure
(variable declarations, a comment, ``Val`` parameters, export); (2)
damaged-code classification -- ``FORMAT_CONTENT_PARSE_FAILED`` from
``parse_document``, ``FORMAT_FRAGMENT_PARSE_FAILED`` from
``parse_fragment``, never a partial tree; (3) the plain-text-fallback
precondition (see the test's own docstring: no plain-text-plugin or
document-open orchestration module is merged into this worktree, so the
full fallback flow is out of reach here -- this pins the two facts it
depends on); (4) plugin-generated output, for both a changed and a newly
inserted node, re-parsing with zero errors; (5) the ``Знач``/``Val``
by-value parameter modifier -- recognized on import, readable and
predicate-queryable, exactly restored on generation, including a
from-scratch insertion; (6) a node-kind completeness matrix covering
every construct ``import_map.py`` singles out, both dialects where
dialect-sensitive, each verified import -> generate -> re-parse with zero
errors; (7) semantic-role mapping -- procedure/function to the function
role, the module root to the module role, method/class to ``()``.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

import pytest
import tree_sitter_bsl
from tree_sitter import Language, Parser

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl import dialects
from tree_engine.plugins.bsl.plugin import BSLFormatPlugin
from tree_engine.plugins.contract import FormatPluginContractError, SemanticRole

# -- Parsing helpers -- always a FRESH Parser per call


def _fresh_root(source: bytes):
    """Parse ``source`` with a brand-new ``Parser``/``Language`` pair and
    return the root node. Never share a ``Parser`` across calls: reuse has
    been observed to silently corrupt byte offsets in this environment."""

    parser = Parser(Language(tree_sitter_bsl.language()))
    return parser.parse(source).root_node


def _find(root: Node, predicate: Callable[[Node], bool]) -> Node:
    for node in walk(root):
        if predicate(node):
            return node
    raise AssertionError("no node in the tree matched the given predicate")


def _replace_by_identity(node: Node, target: Node, replacement: Node) -> Node:
    """Rebuild ``node``'s subtree substituting ``replacement`` for
    ``target`` by object identity, leaving every other node untouched."""

    if node is target:
        return replacement
    if not node.children:
        return node
    new_children = tuple(_replace_by_identity(c, target, replacement) for c in node.children)
    if new_children == node.children:
        return node
    return dataclasses.replace(node, children=new_children)


# -- Fixtures

RUSSIAN_FULL = (
    "Перем МодульнаяПеременная Экспорт;\n"
    "\n"
    "&НаСервере\n"
    "// Функция вычисляет сумму двух параметров\n"
    "Функция Тест(Знач Парам1, Парам2) Экспорт\n"
    "\tПерем А, Б;\n"
    "\t#Если Сервер Тогда\n"
    "\t#КонецЕсли\n"
    "\tВозврат Парам1 + Парам2;\n"
    "КонецФункции\n"
).encode("utf-8")

ENGLISH_FULL = (
    "Var ModuleVariable Export;\n"
    "\n"
    "&AtServer\n"
    "// Procedure performs the test\n"
    "Procedure Test(Val Param1, Param2) Export\n"
    "\tVar A, B;\n"
    "\t#If Server Then\n"
    "\t#EndIf\n"
    "EndProcedure\n"
).encode("utf-8")

DAMAGED_DOCUMENT = "Процедура П(\nКонецПроцедуры\n".encode("utf-8")
DAMAGED_FRAGMENT = "Функция Ф(\nКонецФункции".encode("utf-8")

# (label, source, expected node kind) -- the node-kind completeness matrix.
_NODE_KIND_MATRIX = [
    ("procedure_ru", "Процедура П() Экспорт\nКонецПроцедуры\n", "bsl:procedure_definition"),
    ("procedure_en", "Procedure P() Export\nEndProcedure\n", "bsl:procedure_definition"),
    ("function_ru", "Функция Ф()\n\tВозврат 1;\nКонецФункции\n", "bsl:function_definition"),
    ("function_en", "Function F()\n\tReturn 1;\nEndFunction\n", "bsl:function_definition"),
    ("var_module_ru", "Перем А, Б Экспорт;\n", "core:variable_declaration"),
    ("var_module_en", "Var A, B Export;\n", "core:variable_declaration"),
    ("var_in_procedure_ru", "Процедура П()\n\tПерем В;\nКонецПроцедуры\n", "core:variable_declarator"),
    ("var_in_procedure_en", "Procedure P()\n\tVar C;\nEndProcedure\n", "core:variable_declarator"),
    ("annotation_ru", "&НаСервере\nПроцедура П()\nКонецПроцедуры\n", "core:annotation"),
    ("annotation_en", "&AtServer\nProcedure P()\nEndProcedure\n", "core:annotation"),
    (
        "preprocessor_ru",
        "#Если Сервер Тогда\nПроцедура П()\nКонецПроцедуры\n#КонецЕсли\n",
        "core:preprocessor_directive",
    ),
    (
        "preprocessor_en",
        "#If Server Then\nProcedure P()\nEndProcedure\n#EndIf\n",
        "core:preprocessor_directive",
    ),
    ("comment_ru", "// комментарий\nПроцедура П()\nКонецПроцедуры\n", "bsl:line_comment"),
    ("comment_en", "// comment\nProcedure P()\nEndProcedure\n", "bsl:line_comment"),
    ("param_znach", "Процедура П(Знач А, Б)\nКонецПроцедуры\n", "bsl:parameter"),
    ("param_val", "Procedure P(Val A, B)\nEndProcedure\n", "bsl:parameter"),
]


@pytest.fixture()
def plugin() -> BSLFormatPlugin:
    return BSLFormatPlugin()


# -- 1. Byte-exact round trips, Russian and English


@pytest.mark.parametrize("source", [RUSSIAN_FULL, ENGLISH_FULL], ids=["russian", "english"])
def test_byte_exact_round_trip_russian_and_english(plugin: BSLFormatPlugin, source: bytes) -> None:
    document = plugin.parse_document(source)
    assert isinstance(document, Document)
    assert document.source_format_id == "bsl"

    output = plugin.generate_output(document)
    assert isinstance(output, bytes)
    assert output == source  # untouched document: every byte span is unchanged

    reparsed = _fresh_root(output)
    assert reparsed.has_error is False


# -- 2. Damaged-code parse-failure classification


def test_damaged_code_parse_failure_classification(plugin: BSLFormatPlugin) -> None:
    assert _fresh_root(DAMAGED_DOCUMENT).has_error is True
    with pytest.raises(FormatPluginContractError) as doc_excinfo:
        plugin.parse_document(DAMAGED_DOCUMENT)
    assert doc_excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert doc_excinfo.value.plugin_id == "bsl"

    assert _fresh_root(DAMAGED_FRAGMENT).has_error is True
    with pytest.raises(FormatPluginContractError) as frag_excinfo:
        plugin.parse_fragment(DAMAGED_FRAGMENT)
    assert frag_excinfo.value.error_code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED

    # Sanity: valid input of the same shape still succeeds, both dialects,
    # both entry points -- the classification above is damage-specific.
    good_document = plugin.parse_document("Процедура П()\nКонецПроцедуры\n".encode("utf-8"))
    assert isinstance(good_document, Document)
    good_fragment = plugin.parse_fragment("Procedure P()\nEndProcedure\n")
    assert isinstance(good_fragment, Node)


# -- 3. Plain-text fallback precondition


def test_plain_text_fallback_on_open(plugin: BSLFormatPlugin) -> None:
    """No plain-text-plugin or document-open orchestration module is merged
    into this worktree (only the two BSL/Python format plugins and the
    plugin contract/boundary/registry/selection modules are). The full
    "open falls back to plain text" flow is therefore a later, unmerged
    stage and cannot be exercised end-to-end here. What this plugin's own
    contract guarantees -- and what that later stage depends on -- is
    pinned instead:

    * ``FORMAT_CONTENT_PARSE_FAILED`` is the catalog's one code documented
      as carrying a permitted plain-text fallback (see
      ``tree_engine.errors.ErrorCode``'s own docstring).
    * a damaged whole document raises exactly that code from
      ``parse_document`` -- never a different or generic error -- so a
      caller's fallback dispatch can safely switch on it.
    * the same kind of damage in a *fragment* raises the distinct
      ``FORMAT_FRAGMENT_PARSE_FAILED`` code instead, confirming fallback
      eligibility is specific to whole-document open, matching
      ``tree_engine.plugins.selection``'s own documented description of
      fallback as triggered only by a resolved plugin's ``parse_document``.
    * the original bytes that failed to parse are never consumed, mutated,
      or otherwise made unavailable by the failed call -- exactly what
      re-opening those same bytes as plain text requires.
    """

    assert (
        "FORMAT_CONTENT_PARSE_FAILED is the only code with a permitted plain-text fallback"
        in ErrorCode.__doc__
    )

    original_bytes = bytes(DAMAGED_DOCUMENT)
    with pytest.raises(FormatPluginContractError) as excinfo:
        plugin.parse_document(DAMAGED_DOCUMENT)
    assert excinfo.value.error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED

    # The source bytes object itself is left fully intact after the failure.
    assert DAMAGED_DOCUMENT == original_bytes

    with pytest.raises(FormatPluginContractError) as frag_excinfo:
        plugin.parse_fragment(DAMAGED_FRAGMENT)
    assert frag_excinfo.value.error_code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED
    assert frag_excinfo.value.error_code != ErrorCode.FORMAT_CONTENT_PARSE_FAILED


# -- 4. Plugin-generated output re-parses with zero errors


def test_plugin_generated_output_reparse(plugin: BSLFormatPlugin) -> None:
    source = "Процедура П(Знач А, Б)\nКонецПроцедуры\n".encode("utf-8")
    document = plugin.parse_document(source)

    # -- a changed node: flip the plain parameter's by_value modifier --------
    plain_parameter = _find(
        document.root, lambda n: n.kind == "bsl:parameter" and not n.fields.get(dialects.BY_VALUE, False)
    )
    modified_fields = dict(plain_parameter.fields)
    modified_fields[dialects.BY_VALUE] = True
    modified_parameter = make_node(plain_parameter.kind, fields=modified_fields, children=plain_parameter.children)
    modified_parameter = dataclasses.replace(modified_parameter, buffer_range=plain_parameter.buffer_range)
    changed_root = _replace_by_identity(document.root, plain_parameter, modified_parameter)
    assert changed_root is not document.root
    changed_document = dataclasses.replace(document, root=changed_root)

    changed_output = plugin.generate_output(changed_document, {"source": source})
    assert isinstance(changed_output, bytes)
    assert changed_output != source  # the modifier really was inserted
    assert _fresh_root(changed_output).has_error is False

    # -- a newly inserted node: a fresh comment grafted onto the root --------
    new_comment = make_node("bsl:line_comment", fields={"content": "// freshly inserted\n"}, children=())
    new_root = dataclasses.replace(document.root, children=document.root.children + (new_comment,))
    new_document = dataclasses.replace(document, root=new_root)

    new_output = plugin.generate_output(new_document, {"source": source})
    assert isinstance(new_output, bytes)
    assert b"freshly inserted" in new_output
    assert _fresh_root(new_output).has_error is False


# -- 5. Знач/Val by-value parameter modifier round trip


@pytest.mark.parametrize(
    "source, dialect, keyword",
    [
        ("Процедура П(Знач А, Б)\nКонецПроцедуры\n", dialects.RUSSIAN, "Знач"),
        ("Procedure P(Val A, B)\nEndProcedure\n", dialects.ENGLISH, "Val"),
    ],
    ids=["russian", "english"],
)
def test_znach_val_parameter_round_trip(
    plugin: BSLFormatPlugin, source: str, dialect: str, keyword: str
) -> None:
    source_bytes = source.encode("utf-8")
    document = plugin.parse_document(source_bytes)

    # Recognized on import: a plain, first-class fields entry -- readable
    # directly, with no need to inspect raw content text.
    params = [n for n in walk(document.root) if n.kind == "bsl:parameter"]
    assert len(params) == 2
    with_modifier = [p for p in params if p.fields.get(dialects.BY_VALUE) is True]
    without_modifier = [p for p in params if dialects.BY_VALUE not in p.fields]
    assert len(with_modifier) == 1
    assert len(without_modifier) == 1
    assert with_modifier[0].fields["content"].split()[0] == keyword

    # Available as a search predicate over the tree (the same style used to
    # locate any other tagged node), not just a lucky single lookup.
    found_via_predicate = _find(
        document.root, lambda n: n.kind == "bsl:parameter" and n.fields.get(dialects.BY_VALUE) is True
    )
    assert found_via_predicate is with_modifier[0]

    # Exact restoration on generation: unmodified round trip is byte-identical...
    output = plugin.generate_output(document)
    assert output == source_bytes

    # ...and inserting the modifier from scratch on the plain parameter
    # produces exactly the modifier token plus one space, at exactly that
    # parameter's own position, restored in this same dialect.
    plain_parameter = without_modifier[0]
    modified_fields = dict(plain_parameter.fields)
    modified_fields[dialects.BY_VALUE] = True
    modified_parameter = make_node(plain_parameter.kind, fields=modified_fields, children=plain_parameter.children)
    modified_parameter = dataclasses.replace(modified_parameter, buffer_range=plain_parameter.buffer_range)
    changed_root = _replace_by_identity(document.root, plain_parameter, modified_parameter)
    changed_document = dataclasses.replace(document, root=changed_root)

    changed_output = plugin.generate_output(changed_document, {"source": source_bytes, "dialect": dialect})
    insertion_point = plain_parameter.buffer_range[0]
    inserted = f"{keyword} ".encode("utf-8")
    expected = source_bytes[:insertion_point] + inserted + source_bytes[insertion_point:]
    assert changed_output == expected
    assert _fresh_root(changed_output).has_error is False


# -- 6. Node-kind completeness matrix


@pytest.mark.parametrize("label, source_text, expected_kind", _NODE_KIND_MATRIX, ids=[m[0] for m in _NODE_KIND_MATRIX])
def test_node_kind_completeness_matrix(
    plugin: BSLFormatPlugin, label: str, source_text: str, expected_kind: str
) -> None:
    source_bytes = source_text.encode("utf-8")
    document = plugin.parse_document(source_bytes)

    kinds_present = {str(n.kind) for n in walk(document.root)}
    assert expected_kind in kinds_present, f"{label}: {expected_kind!r} missing from imported tree"

    output = plugin.generate_output(document)
    assert output == source_bytes, f"{label}: generated output is not byte-identical to source"

    reparsed = _fresh_root(output)
    assert reparsed.has_error is False, f"{label}: generated output failed to re-parse cleanly"


# -- 7. Semantic-role mapping


def test_bsl_semantic_role_mapping(plugin: BSLFormatPlugin) -> None:
    mapping = plugin.semantic_role_mapping()

    assert set(mapping.roles_for(SemanticRole.FUNCTION)) == {
        "bsl:procedure_definition",
        "bsl:function_definition",
    }
    assert mapping.roles_for(SemanticRole.MODULE) == ("bsl:source_file",)
    # BSL has no method or class construct: both yield the empty tuple,
    # never an error.
    assert mapping.roles_for(SemanticRole.METHOD) == ()
    assert mapping.roles_for(SemanticRole.CLASS) == ()
