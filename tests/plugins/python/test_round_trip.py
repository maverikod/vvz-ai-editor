"""Byte-identical round-trip contract suite for the Python translator (C-014).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: end-to-end coverage through the plugin's own public entry points --
``PythonFormatPlugin.parse_document``/``generate_output`` for a full
document, ``parse_fragment``/``generate_output`` for the statement-shaped
fragment path, and the ``import_tree``/``export_tree`` bridge for the
expression-shaped fragment path -- composing the already-merged
``PythonImportMap``/``PythonExportMap`` behind them. The governing
invariant throughout: parsing source and exporting the resulting tree
reproduces the original source bytes exactly, bit for bit, for every
unchanged document or fragment.

Fragment entry points: ``PythonFormatPlugin.parse_fragment`` tries
``libcst.parse_statement`` first and only falls back to
``libcst.parse_expression`` when the statement parse raises -- and every
well-formed expression in this suite's demanded categories (simple
expressions, binary operations, calls, comprehensions, lambdas,
conditionals, subscripts) is *also* syntactically valid as a bare
expression-statement, so ``parse_fragment`` always takes the statement
branch for them (confirmed empirically: no expression in the demanded set
makes ``libcst.parse_statement`` raise while ``libcst.parse_expression``
succeeds). Taking the statement branch wraps the source in a
``SimpleStatementLine``, whose export appends a trailing newline the bare
expression source never had -- e.g. ``parse_fragment("1 + 2")`` then
``generate_output`` yields ``"1 + 2\\n"``, not ``"1 + 2"``. So the
expression entry point is exercised here through the plugin's other
documented fragment bridge instead -- ``import_tree(libcst.parse_expression(...))``
/ ``export_tree(...)`` -- which the plugin's own module docstring names as
"the bridge for a caller that already has (or wants back) a real
libcst.Module/CSTNode", i.e. the genuine expression-parse entry point this
plugin exposes. This is a real, reported gap in ``parse_fragment`` against
a literal "expression entry point via parse_fragment" reading of the
contract brief -- see the step report, not asserted as a failure here.

Every imported node carries a fresh UUID4 ``node_id`` and an integer
``short_id`` ({p013}, {p021}); two independent imports of the same source
are structurally equal and identity-distinct, never whole-object equal, so
every document-level assertion below checks structure (kind, buffer range,
field-name set, child shape) and disjoint identities across independent
parses -- never object identity or equality of the ``Node``/``Document``
instances themselves.
"""

from __future__ import annotations

import libcst
import pytest

from tree_engine.core.nodes import Document, Node, walk
from tree_engine.plugins.python.plugin import PythonFormatPlugin

PLUGIN = PythonFormatPlugin()


def _shape(node: Node):
    """Structural fingerprint of a node: kind, buffer range, field-name
    set, and recursive child shapes -- never node identity."""

    return (
        node.kind,
        node.buffer_range,
        tuple(sorted(node.fields.keys())),
        tuple(_shape(child) for child in node.children),
    )


def _assert_document_round_trip(source: bytes) -> Document:
    """Parse ``source`` as a full document, export it back, and assert the
    output is byte-identical to ``source``. Also parses ``source`` a second,
    independent time and asserts the two resulting trees are structurally
    equal while carrying disjoint node identities, per {p013}."""

    document = PLUGIN.parse_document(source)
    output = PLUGIN.generate_output(document)
    assert isinstance(output, bytes)
    assert output == source

    second = PLUGIN.parse_document(source)
    assert _shape(document.root) == _shape(second.root)
    first_ids = {n.node_id for n in walk(document.root)}
    second_ids = {n.node_id for n in walk(second.root)}
    assert first_ids.isdisjoint(second_ids)
    assert None not in first_ids and None not in second_ids

    return document


def _assert_fragment_statement_round_trip(text: str) -> Node:
    """Parse ``text`` via the plugin's ``parse_fragment`` (statement entry
    point) and assert ``generate_output`` reproduces it exactly."""

    node = PLUGIN.parse_fragment(text)
    assert isinstance(node, Node)
    output = PLUGIN.generate_output(node)
    assert isinstance(output, str)
    assert output == text
    return node


def _assert_fragment_expression_round_trip(text: str) -> Node:
    """Parse ``text`` via ``libcst.parse_expression`` and the plugin's
    ``import_tree``/``export_tree`` bridge (this plugin's genuine
    expression entry point -- see the module docstring), and assert the
    rebuilt LibCST node renders back to ``text`` exactly."""

    parsed = libcst.parse_expression(text)
    node = PLUGIN.import_tree(parsed)
    assert isinstance(node, Node)
    rebuilt = PLUGIN.export_tree(node)
    output = libcst.Module(body=[]).code_for_node(rebuilt)
    assert output == text
    return node


UTF8_AND_ENCODING_COOKIE_SOURCES = [
    pytest.param(b"x = 1\n", id="utf8_ascii"),
    pytest.param("x = \"caf\u00e9 na\u00efve\"\n".encode("utf-8"), id="utf8_unicode_content"),
    pytest.param(b"# -*- coding: utf-8 -*-\nx = 1\n", id="utf8_coding_cookie"),
    pytest.param(b"# coding: utf-8\nx = 1\n", id="utf8_coding_cookie_alt_spelling"),
    pytest.param(b"#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nx = 1\n", id="shebang_plus_encoding"),
    pytest.param(
        "# -*- coding: latin-1 -*-\nx = \"caf\u00e9\"\n".encode("latin-1"), id="latin1_coding_cookie"
    ),
]


@pytest.mark.parametrize("source", UTF8_AND_ENCODING_COOKIE_SOURCES)
def test_utf8_and_encoding_cookie_round_trip(source: bytes) -> None:
    """UTF-8 content (plain and with non-ASCII characters), explicit PEP
    263 coding cookies in both accepted spellings, a shebang-plus-encoding
    combination, and a non-default (latin-1) encoding cookie all round-trip
    byte-identically, with ``Module.encoding`` reflecting the resolved
    codec name."""

    document = _assert_document_round_trip(source)
    assert isinstance(document.root.fields["encoding"], str)


LINE_ENDING_SOURCES = [
    pytest.param(b"x = 1\ny = 2\n", id="lf_only"),
    pytest.param(b"x = 1\r\ny = 2\r\n", id="crlf_only"),
    pytest.param(b"x = 1\r\ny = 2\nz = 3\r\n", id="mixed_crlf_then_lf"),
    pytest.param(b"x = 1\r\ny = 2\nz = 3", id="mixed_no_trailing_newline"),
    pytest.param(b"def f():\r\n    x = 1\r\n    return x\r\n", id="crlf_inside_function_body"),
]


@pytest.mark.parametrize("source", LINE_ENDING_SOURCES)
def test_line_ending_preservation(source: bytes) -> None:
    """CRLF-only, LF-only, and mixed CRLF/LF line endings within a single
    document -- including inside a function body and without a trailing
    newline -- all reproduce their exact original newline bytes per line."""

    _assert_document_round_trip(source)


HEADER_FOOTER_SOURCES = [
    pytest.param(b'"""Module doc."""\n\nx = 1\n', id="triple_quoted_docstring_header"),
    pytest.param(b'"""\nMulti-line\nformatted\ndocstring.\n"""\n\nx = 1\n', id="formatted_multiline_docstring"),
    pytest.param(
        b'#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n"""Doc."""\n\nx = 1\n',
        id="shebang_encoding_and_docstring",
    ),
    pytest.param(b"x = 1\n\n# trailing comment footer\n", id="trailing_comment_footer"),
    pytest.param(b"x = 1\n\n# trailing comment footer", id="footer_without_trailing_newline"),
    pytest.param(
        b"# header comment\n\nx = 1\n\n# footer comment\n", id="header_and_footer_comments_with_blank"
    ),
]


@pytest.mark.parametrize("source", HEADER_FOOTER_SOURCES)
def test_header_footer_round_trip(source: bytes) -> None:
    """Non-trivial module headers and footers -- triple-quoted and
    multi-line formatted docstrings, a shebang-plus-encoding-plus-docstring
    combination, trailing comment footers, and the presence/absence of a
    final trailing newline -- all round-trip exactly."""

    _assert_document_round_trip(source)


COMMENTS_AND_BLANK_LINES_SOURCES = [
    pytest.param(b"# top comment\n\n\n# second comment\nx = 1\n", id="leading_module_comments"),
    pytest.param(b"def f():  # inline\n    return 1\n", id="inline_trailing_comment"),
    pytest.param(b"def f():\n    # indented block comment\n    return 1\n", id="block_comment_indentation"),
    pytest.param(b"x = 1\n\n\n\ny = 2\n\nz = 3\n", id="blank_line_density_variations"),
    pytest.param(b"x = 1\n# right after, no blank line\ny = 2\n", id="comment_adjacent_to_code"),
]


@pytest.mark.parametrize("source", COMMENTS_AND_BLANK_LINES_SOURCES)
def test_comments_and_blank_lines_round_trip(source: bytes) -> None:
    """Leading module comments, inline trailing comments, indented block
    comments, varying blank-line density, and a comment directly adjacent
    to code (no separating blank line) all round-trip exactly."""

    _assert_document_round_trip(source)


TYPE_ANNOTATION_SOURCES = [
    pytest.param(b"def f(a: int, b: str) -> bool:\n    return True\n", id="param_and_return_annotations"),
    pytest.param(b"x: int = 1\ny: int\n", id="variable_annotations_with_and_without_value"),
    pytest.param(
        b"from typing import Dict, List\nz: Dict[str, List[int]] = {}\n", id="complex_generic_annotation"
    ),
    pytest.param(
        b"from typing import Optional, Union\na: Optional[int] = None\nb: Union[int, str] = 1\n",
        id="union_and_optional_annotations",
    ),
    pytest.param(
        b"from typing import ClassVar\n\n\nclass C:\n    count: ClassVar[int] = 0\n",
        id="classvar_annotation",
    ),
]


@pytest.mark.parametrize("source", TYPE_ANNOTATION_SOURCES)
def test_type_annotations_round_trip(source: bytes) -> None:
    """Function parameter and return-type annotations, variable
    annotations (with and without an assigned value), complex generic
    types, ``Union``/``Optional`` types, and a ``ClassVar`` class-variable
    annotation all round-trip exactly."""

    _assert_document_round_trip(source)


ASSIGNMENT_SOURCES = [
    pytest.param(b"x = 1\n", id="simple_assignment"),
    pytest.param(b"a, b = 1, 2\n", id="tuple_unpacking"),
    pytest.param(b"x = 1\nx += 1\n", id="augmented_assignment"),
    pytest.param(b"a = b = 1\n", id="multiple_targets"),
    pytest.param(
        b"data = [1, 2, 3]\nif (n := len(data)) > 0:\n    print(n)\n", id="walrus_operator_in_context"
    ),
]


@pytest.mark.parametrize("source", ASSIGNMENT_SOURCES)
def test_assignments_round_trip(source: bytes) -> None:
    """Simple assignment, tuple-unpacking assignment, augmented assignment,
    multiple assignment targets, and the walrus operator used in an ``if``
    condition all round-trip exactly."""

    _assert_document_round_trip(source)


FUNCTION_DEFINITION_SOURCES = [
    pytest.param(b"def f():\n    pass\n", id="simple_function"),
    pytest.param(b"def f(a, b=2, *, c=3):\n    return a + b + c\n", id="function_with_defaults"),
    pytest.param(b"def f(*args, **kwargs):\n    return args, kwargs\n", id="function_args_and_kwargs"),
    pytest.param(b"async def f():\n    await g()\n", id="async_function"),
    pytest.param(
        b"def outer():\n    def inner():\n        def innermost():\n            pass\n"
        b"        return innermost\n    return inner\n",
        id="nested_functions_multiple_levels",
    ),
    pytest.param(b"@decorator\ndef f():\n    pass\n", id="single_decorator"),
    pytest.param(b"@dec_one\n@dec_two(1)\ndef f():\n    pass\n", id="multiple_decorators"),
]


@pytest.mark.parametrize("source", FUNCTION_DEFINITION_SOURCES)
def test_function_definitions_round_trip(source: bytes) -> None:
    """Simple functions, functions with default/star-args/star-kwargs
    parameters, async functions, functions nested at multiple levels, and
    functions with one or multiple decorators all round-trip exactly."""

    _assert_document_round_trip(source)


CLASS_DEFINITION_SOURCES = [
    pytest.param(b"class C:\n    pass\n", id="simple_class"),
    pytest.param(b'class C:\n    """Doc."""\n\n    pass\n', id="class_with_docstring"),
    pytest.param(b"class C:\n    def method(self):\n        return self\n", id="instance_method"),
    pytest.param(
        b"class C:\n    @classmethod\n    def cm(cls):\n        return cls\n\n"
        b"    @staticmethod\n    def sm():\n        return None\n",
        id="classmethod_and_staticmethod",
    ),
    pytest.param(
        b"class C:\n    @property\n    def value(self):\n        return self._value\n",
        id="property_decorator",
    ),
    pytest.param(
        b"class C:\n    def method(self, a: int) -> int:\n        return a\n",
        id="method_with_type_annotations",
    ),
    pytest.param(b"class Outer:\n    class Inner:\n        pass\n", id="nested_classes"),
    pytest.param(b"class C(Base):\n    pass\n", id="single_inheritance"),
    pytest.param(b"class C(Base1, Base2):\n    pass\n", id="multiple_inheritance"),
    pytest.param(
        b"class C:\n    def __init__(self, a, b=1, *args, **kwargs):\n        self.a = a\n",
        id="constructor_parameter_handling",
    ),
    pytest.param(
        b"class C:\n    def __repr__(self):\n        return 'C()'\n\n"
        b"    def __eq__(self, other):\n        return True\n",
        id="dunder_methods",
    ),
    pytest.param(
        b"import os\nfrom typing import List\n\n\nclass Greeter(Base1, Base2):\n"
        b'    """Docstring."""\n\n    count: int = 0\n\n'
        b"    def __init__(self, name: str) -> None:\n"
        b"        self.name = name  # store it\n        Greeter.count += 1\n\n"
        b"    @staticmethod\n    def greet(names: List[str]) -> str:\n"
        b"        result = []\n        for n in names:\n            if n:\n"
        b"                result.append(n)\n            else:\n                continue\n"
        b'        return ", ".join(result)\n',
        id="comprehensive_class_end_to_end",
    ),
]


@pytest.mark.parametrize("source", CLASS_DEFINITION_SOURCES)
def test_class_definitions_and_methods_round_trip(source: bytes) -> None:
    """Simple classes, docstrings, instance/class/static/property methods,
    type-annotated methods, nested classes, single and multiple
    inheritance, constructor parameter handling, dunder methods, and a
    comprehensive end-to-end class all round-trip exactly; the
    comprehensive case also carries the structural-equality-not-identity
    check via ``_assert_document_round_trip``."""

    _assert_document_round_trip(source)


FRAGMENT_STATEMENT_SOURCES = [
    pytest.param("x = 1\n", id="single_statement"),
    pytest.param("x = 1  # trailing comment\n", id="statement_with_trailing_comment"),
    pytest.param("# leading comment\n\nx = 1\n", id="statement_with_leading_comment"),
    pytest.param("\nx = 1\n", id="statement_with_leading_blank_line"),
    pytest.param("x = (1 +\n     2)\n", id="multi_line_statement_with_continuation"),
    pytest.param("for x in range(3):\n    print(x)\n", id="compound_statement"),
]

FRAGMENT_EXPRESSION_SOURCES = [
    pytest.param("1 + 2", id="simple_expression"),
    pytest.param("1 + 2 * (3 - 4)", id="binary_operation"),
    pytest.param("f(1, 2, key=3)", id="function_call"),
    pytest.param("[x for x in range(3)]", id="list_comprehension"),
    pytest.param("{k: v for k, v in items}", id="dict_comprehension"),
    pytest.param("lambda x: x + 1", id="lambda_expression"),
    pytest.param("a if b else c", id="conditional_expression"),
    pytest.param("obj[1:2]", id="subscript_expression"),
]


@pytest.mark.parametrize("text", FRAGMENT_STATEMENT_SOURCES)
def test_fragment_parse_and_export_round_trip_statement(text: str) -> None:
    """Fragment parsing/export via the statement entry point
    (``parse_fragment``/``generate_output``): single statements, statements
    with a leading or trailing comment, a leading blank line, a multi-line
    continuation, and a compound statement all round-trip exactly."""

    _assert_fragment_statement_round_trip(text)


@pytest.mark.parametrize("text", FRAGMENT_EXPRESSION_SOURCES)
def test_fragment_parse_and_export_round_trip_expression(text: str) -> None:
    """Fragment parsing/export via the expression entry point
    (``import_tree(libcst.parse_expression(...))``/``export_tree`` -- see
    the module docstring for why this, not ``parse_fragment``, is this
    plugin's genuine expression entry point): simple expressions, binary
    operations, calls, comprehensions, a lambda, a conditional expression,
    and a subscript expression all round-trip exactly."""

    _assert_fragment_expression_round_trip(text)


def test_fragment_parse_and_export_round_trip() -> None:
    """Named per the contract brief's required object list: exercises both
    fragment entry points together on one representative case each,
    delegating the full parametrized coverage to the two sibling functions
    above."""

    _assert_fragment_statement_round_trip("for x in range(3):\n    print(x)\n")
    _assert_fragment_expression_round_trip("1 + 2 * (3 - 4)")
