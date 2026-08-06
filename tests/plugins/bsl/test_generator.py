"""Unit tests for the C-015 export/generate direction of the BSL translator
(tree_engine.plugins.bsl.generator), paired with the merged
tree_engine.plugins.bsl.import_map to build real common-model trees from
real tree-sitter-bsl parses -- no fabricated trees.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Covered here:

* byte-identical round trip (parse -> import -> export -> generate) for a
  document containing a module-level exported variable declaration, an
  annotation, a procedure with a by-value and a plain parameter plus its
  own Export keyword, an in-procedure multi-name variable declaration, and
  an unrecognized preprocessor directive -- in both keyword dialects;
* every synthesized keyword in the regenerated output belonging to the
  document's own dialect, never the other one;
* a field change deep in the tree (the by-value modifier flag on one
  parameter, several levels below the document root) surfacing exactly at
  its own position in the regenerated output while every other byte stays
  identical to the original source;
* a node kind this plugin does not own raising
  ``UnsupportedTranslationError`` (``UNSUPPORTED_TRANSLATION``) only when
  the generation tree is rendered by ``generate_output`` -- never earlier,
  when ``export_from_common`` merely builds the ``BSLGenerationTree``.

A fresh ``tree_sitter.Parser`` is built for every parse: reusing one
instance across parses has been observed to silently corrupt byte offsets.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

import pytest
import tree_sitter_bsl
from tree_sitter import Language, Parser

from tree_engine.core.nodes import Node, make_node, walk
from tree_engine.plugins.bsl import dialects
from tree_engine.plugins.bsl.generator import BSLGenerationTree, BSLGenerator
from tree_engine.plugins.bsl.import_map import import_to_common
from tree_engine.plugins.contract import UnsupportedTranslationError

# ---------------------------------------------------------------------------
# Fixtures: one document per dialect, each exercising every construct this
# plugin gives special generation treatment to.
# ---------------------------------------------------------------------------

RUSSIAN_SOURCE = (
    "Перем МодульнаяПеременная Экспорт;\n"
    "\n"
    "&НаСервере\n"
    "Процедура Тест(Знач Парам1, Парам2) Экспорт\n"
    "\tПерем А, Б, В;\n"
    "\t#Если Сервер Тогда\n"
    "\t#КонецЕсли\n"
    "КонецПроцедуры\n"
).encode("utf-8")

ENGLISH_SOURCE = (
    "Var ModuleVariable Export;\n"
    "\n"
    "&AtServer\n"
    "Procedure Test(Val Param1, Param2) Export\n"
    "\tVar A, B, C;\n"
    "\t#If Server Then\n"
    "\t#EndIf\n"
    "EndProcedure\n"
).encode("utf-8")

RUSSIAN_ONLY_TOKENS = (
    "Знач".encode("utf-8"),
    "Перем".encode("utf-8"),
    "Экспорт".encode("utf-8"),
    "&НаСервере".encode("utf-8"),
)
ENGLISH_ONLY_TOKENS = (b"Val", b"Var", b"Export", b"&AtServer")


def _parse(source: bytes):
    """Parse ``source`` with a FRESH ``Parser`` per call (see module
    docstring) and return the root ``tree_sitter`` node. Fails loudly if
    tree-sitter-bsl could not parse it cleanly -- these fixtures must be
    valid BSL in both dialects."""

    language = Language(tree_sitter_bsl.language())
    parser = Parser(language)
    tree = parser.parse(source)
    assert not tree.root_node.has_error, "fixture source failed to parse cleanly"
    return tree.root_node


def _import(source: bytes) -> Node:
    return import_to_common(_parse(source))


def _find(root: Node, predicate: Callable[[Node], bool]) -> Node:
    for node in walk(root):
        if predicate(node):
            return node
    raise AssertionError("no node in the tree matched the given predicate")


def _replace_by_identity(node: Node, target: Node, replacement: Node) -> Node:
    """Rebuild ``node``'s subtree, substituting ``replacement`` for
    ``target`` wherever found by object identity (``Node`` carries no
    stable id here), leaving every other node exactly as it was.

    Generic BSL nodes render by walking their own ``.children`` tuple
    recursively and gap-stitching around each rendered child (see
    generator._render_generic/_stitch); only the ``children`` chain from
    the root down to the changed node needs rebuilding for that recursion
    to pick up the change -- field values are not consulted by the generic
    path, only by kind-specific rules that read straight from the node
    handed to them.
    """

    if node is target:
        return replacement
    if not node.children:
        return node
    new_children = tuple(_replace_by_identity(c, target, replacement) for c in node.children)
    if new_children == node.children:
        return node
    return dataclasses.replace(node, children=new_children)


# ---------------------------------------------------------------------------
# Byte-identical round trip, in both dialects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", [RUSSIAN_SOURCE, ENGLISH_SOURCE], ids=["russian", "english"])
def test_round_trip_byte_identical(source: bytes) -> None:
    root = _import(source)
    generation_tree = BSLGenerator().export_from_common(root, {"source": source})
    assert isinstance(generation_tree, BSLGenerationTree)
    output = BSLGenerator().generate_output(generation_tree)
    assert output == source


@pytest.mark.parametrize("source", [RUSSIAN_SOURCE, ENGLISH_SOURCE], ids=["russian", "english"])
def test_round_trip_byte_identical_via_generate_output_alone(source: bytes) -> None:
    """``generate_output`` documents an allowance to run
    ``export_from_common`` internally and accept a bare common-model
    ``Node`` directly; that combined path must be exercised too, not only
    the two-step ``BSLGenerationTree`` path."""

    root = _import(source)
    output = BSLGenerator().generate_output(root, {"source": source})
    assert output == source


# ---------------------------------------------------------------------------
# Each dialect renders back in its own keywords, never the other
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, dialect, own_tokens, foreign_tokens",
    [
        (RUSSIAN_SOURCE, dialects.RUSSIAN, RUSSIAN_ONLY_TOKENS, ENGLISH_ONLY_TOKENS),
        (ENGLISH_SOURCE, dialects.ENGLISH, ENGLISH_ONLY_TOKENS, RUSSIAN_ONLY_TOKENS),
    ],
    ids=["russian", "english"],
)
def test_dialect_detected_and_rendered_in_its_own_keywords(
    source: bytes, dialect: str, own_tokens: tuple, foreign_tokens: tuple
) -> None:
    root = _import(source)
    generation_tree = BSLGenerator().export_from_common(root, {"source": source})
    assert generation_tree.dialect == dialect

    output = BSLGenerator().generate_output(generation_tree)
    for token in own_tokens:
        assert token in output, f"{token!r} missing from own-dialect output"
    for token in foreign_tokens:
        assert token not in output, f"foreign-dialect token {token!r} leaked into output"


# ---------------------------------------------------------------------------
# A field change deep in the tree surfaces exactly at its own position,
# with everything else byte-identical to the original
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, by_value_keyword",
    [(RUSSIAN_SOURCE, "Знач"), (ENGLISH_SOURCE, "Val")],
    ids=["russian", "english"],
)
def test_deep_by_value_field_change_surfaces_with_rest_byte_identical(
    source: bytes, by_value_keyword: str
) -> None:
    """``Парам2``/``Param2`` (the second procedure parameter, several
    levels below the document root: source_file -> procedure_definition ->
    parameters -> parameter) has no by-value modifier on import. Flipping
    its ``by_value`` field -- with nothing else touched anywhere in the
    tree -- must surface the modifier at exactly this parameter's own
    start position on regeneration, and nowhere else: every byte before
    and after that single insertion point must still match the original
    source exactly.
    """

    root = _import(source)
    plain_parameter = _find(
        root, lambda n: n.kind == "bsl:parameter" and not n.fields.get(dialects.BY_VALUE, False)
    )
    assert plain_parameter.buffer_range is not None

    modified_fields = dict(plain_parameter.fields)
    modified_fields[dialects.BY_VALUE] = True
    modified_parameter = make_node(
        plain_parameter.kind, fields=modified_fields, children=plain_parameter.children
    )
    modified_parameter = dataclasses.replace(modified_parameter, buffer_range=plain_parameter.buffer_range)

    changed_root = _replace_by_identity(root, plain_parameter, modified_parameter)
    assert changed_root is not root  # the substitution actually happened

    output = BSLGenerator().generate_output(changed_root, {"source": source})

    insertion_point = plain_parameter.buffer_range[0]
    inserted = f"{by_value_keyword} ".encode("utf-8")
    expected = source[:insertion_point] + inserted + source[insertion_point:]
    assert output == expected
    # Everything up to the insertion point, and everything from the
    # original parameter's own start onward, is untouched byte-for-byte.
    assert output[:insertion_point] == source[:insertion_point]
    assert output[insertion_point + len(inserted) :] == source[insertion_point:]


# ---------------------------------------------------------------------------
# UNSUPPORTED_TRANSLATION: raised only when the generation tree is
# rendered, never when it is built
# ---------------------------------------------------------------------------


def test_unsupported_node_kind_raises_only_at_render_not_at_export() -> None:
    foreign_node = make_node("other:whatever", fields={"content": "x"}, children=())

    generator = BSLGenerator()
    # export_from_common merely resolves the root/dialect/source triple; it
    # must not inspect or validate node kinds, so an unowned kind is
    # accepted here without error.
    generation_tree = generator.export_from_common(foreign_node)
    assert isinstance(generation_tree, BSLGenerationTree)
    assert generation_tree.root is foreign_node

    # The same unowned kind raises only once rendering is attempted.
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        generator.generate_output(generation_tree)
    assert excinfo.value.node_type == "other:whatever"
    assert excinfo.value.format_id == "bsl"


def test_unsupported_node_kind_nested_inside_a_supported_tree_raises_at_render() -> None:
    """The same rule applies when the unowned kind is buried inside an
    otherwise-normal, plugin-owned tree: export succeeds, and only the
    later render call fails, naming the offending nested kind."""

    root = _import(RUSSIAN_SOURCE)
    foreign_child = make_node("other:unowned", fields={"content": "z"}, children=())
    procedure = _find(root, lambda n: n.kind == "bsl:procedure_definition")
    grafted_procedure = dataclasses.replace(procedure, children=procedure.children + (foreign_child,))
    changed_root = _replace_by_identity(root, procedure, grafted_procedure)

    generator = BSLGenerator()
    generation_tree = generator.export_from_common(changed_root, {"source": RUSSIAN_SOURCE})

    with pytest.raises(UnsupportedTranslationError) as excinfo:
        generator.generate_output(generation_tree)
    assert excinfo.value.node_type == "other:unowned"
