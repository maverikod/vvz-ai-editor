"""Unit tests for the C-014 import direction of the Python translator
(tree_engine.plugins.python.import_map).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``PythonImportMap.import_to_common`` and the ``import_tree``
bridge in isolation, against real sources parsed by LibCST -- no fake trees.
Covers field-by-field conversion, trivia/comment/blank-line capture, byte
ranges, encoding/indent/newline defaults, the trailing-newline flag, header
and footer preservation, and the ``import_tree`` bridge for externally
constructed LibCST objects. Byte-identical round-trips are explicitly out of
scope here; they belong to the separate round-trip contract suite.
"""

from __future__ import annotations

import dataclasses

import libcst
import pytest

from tree_engine.core.nodes import Document, Node, walk
from tree_engine.plugins.contract import FormatPluginContractError
from tree_engine.plugins.python.import_map import PythonImportMap, import_tree


def _first(root: Node, kind: str) -> Node:
    return next(n for n in walk(root) if n.kind == kind)


def test_field_by_field_conversion() -> None:
    source = "def greet(name):\n    return name\n"
    module = libcst.parse_module(source)

    document = PythonImportMap().import_to_common(module)

    assert isinstance(document, Document)
    assert document.source_format_id == "python"
    root = document.root
    assert root.kind == "python:Module"

    # The root's fields mirror libcst.Module's own dataclass fields, by name,
    # exactly -- no hand-maintained subset and nothing extra.
    assert set(root.fields.keys()) == {f.name for f in dataclasses.fields(module)}

    func_node = _first(root, "python:FunctionDef")
    cst_func = module.body[0]
    assert isinstance(cst_func, libcst.FunctionDef)
    assert set(func_node.fields.keys()) == {f.name for f in dataclasses.fields(cst_func)}

    name_field = func_node.fields["name"]
    assert isinstance(name_field, Node)
    assert name_field.kind == "python:Name"
    assert name_field.fields["value"] == "greet"
    assert set(name_field.fields.keys()) == {f.name for f in dataclasses.fields(cst_func.name)}

    # A Sequence[CSTNode] field (Parameters.params) becomes an ordered tuple
    # of Node, one per source field entry.
    params_node = func_node.fields["params"]
    assert isinstance(params_node, Node)
    assert params_node.kind == "python:Parameters"
    params_tuple = params_node.fields["params"]
    assert isinstance(params_tuple, tuple)
    assert len(params_tuple) == 1
    assert all(isinstance(item, Node) for item in params_tuple)
    param_node = params_tuple[0]
    assert param_node.kind == "python:Param"
    assert param_node.fields["name"].fields["value"] == "name"

    # LibCST's only Enum-valued field, MaybeSentinel.DEFAULT, becomes a
    # "$sentinel" marker node -- never a bare None or plain string.
    equal_field = param_node.fields["equal"]
    assert isinstance(equal_field, Node)
    assert equal_field.kind == "python:$sentinel"
    enum_cls = type(libcst.MaybeSentinel.DEFAULT)
    assert equal_field.fields["enum_class"] == f"{enum_cls.__module__}.{enum_cls.__qualname__}"
    assert equal_field.fields["member"] == "DEFAULT"

    # Every Node-valued or tuple-of-Node field value is also reachable
    # through the generic `children` traversal slot.
    assert name_field in func_node.children
    assert params_node in func_node.children


def test_trivia_and_comment_capture() -> None:
    source = (
        "import os\n"
        "\n"
        "\n"
        "# describes greet\n"
        "def greet(name):  # inline comment\n"
        "    return name\n"
    )
    module = libcst.parse_module(source)

    root = PythonImportMap().import_to_common(module).root
    func_node = _first(root, "python:FunctionDef")

    # Two purely blank leading lines, then a full-line comment, all captured
    # as EmptyLine nodes in source order -- nothing collapsed or dropped.
    leading_lines = func_node.fields["leading_lines"]
    assert isinstance(leading_lines, tuple)
    assert [n.kind for n in leading_lines] == ["python:EmptyLine"] * 3
    assert leading_lines[0].fields["comment"] is None
    assert leading_lines[1].fields["comment"] is None
    comment_node = leading_lines[2].fields["comment"]
    assert isinstance(comment_node, Node)
    assert comment_node.kind == "python:Comment"
    assert comment_node.fields["value"] == "# describes greet"

    # An inline trailing comment on the `def` line lands on the indented
    # block's header (TrailingWhitespace), not on the FunctionDef itself.
    body_node = func_node.fields["body"]
    assert body_node.kind == "python:IndentedBlock"
    header_node = body_node.fields["header"]
    assert header_node.kind == "python:TrailingWhitespace"
    inline_comment = header_node.fields["comment"]
    assert inline_comment.kind == "python:Comment"
    assert inline_comment.fields["value"] == "# inline comment"


def test_byte_range_accuracy() -> None:
    source = "x = 1\ndef greet(name):\n    return name\n"
    module = libcst.parse_module(source)
    encoded = source.encode(module.encoding)

    root = PythonImportMap().import_to_common(module).root

    assert root.buffer_range == (0, len(encoded))

    func_node = _first(root, "python:FunctionDef")
    start, end = func_node.buffer_range
    assert encoded[start:end] == b"def greet(name):\n    return name"

    name_node = func_node.fields["name"]
    n_start, n_end = name_node.buffer_range
    assert encoded[n_start:n_end] == b"greet"

    # A bare fragment CSTNode (no absolute document buffer to range over)
    # keeps the base schema's ordinary buffer_range=None throughout.
    fragment = libcst.parse_expression("1 + 2")
    fragment_node = PythonImportMap().import_to_common(fragment)
    assert isinstance(fragment_node, Node)
    assert fragment_node.buffer_range is None
    for descendant in walk(fragment_node):
        assert descendant.buffer_range is None


def test_encoding_indent_newline_defaults() -> None:
    tab_indented = libcst.parse_module("if True:\n\tpass\n")
    root = PythonImportMap().import_to_common(tab_indented).root
    assert root.fields["encoding"] == "utf-8"
    assert root.fields["default_indent"] == "\t"
    assert root.fields["default_newline"] == "\n"

    crlf_source = libcst.parse_module("x = 1\r\ny = 2\r\n")
    crlf_root = PythonImportMap().import_to_common(crlf_source).root
    assert crlf_root.fields["default_newline"] == "\r\n"

    space_indented = libcst.parse_module("if True:\n  pass\n")
    space_root = PythonImportMap().import_to_common(space_indented).root
    assert space_root.fields["default_indent"] == "  "


def test_trailing_newline_flag() -> None:
    with_newline = libcst.parse_module("x = 1\n")
    root_with = PythonImportMap().import_to_common(with_newline).root
    assert root_with.fields["has_trailing_newline"] is True

    without_newline = libcst.parse_module("x = 1")
    root_without = PythonImportMap().import_to_common(without_newline).root
    assert root_without.fields["has_trailing_newline"] is False


def test_header_footer_preservation() -> None:
    source = (
        "# file header comment\n"
        "\n"
        "x = 1\n"
        "\n"
        "# trailing footer comment\n"
    )
    module = libcst.parse_module(source)

    root = PythonImportMap().import_to_common(module).root

    header = root.fields["header"]
    assert isinstance(header, tuple)
    assert [n.kind for n in header] == ["python:EmptyLine"] * 2
    assert header[0].fields["comment"].fields["value"] == "# file header comment"
    assert header[1].fields["comment"] is None

    footer = root.fields["footer"]
    assert isinstance(footer, tuple)
    assert [n.kind for n in footer] == ["python:EmptyLine"] * 2
    assert footer[0].fields["comment"] is None
    assert footer[1].fields["comment"].fields["value"] == "# trailing footer comment"

    # Header/footer are read from Module's own fields verbatim -- no
    # side-channel duplicate is attached anywhere else on the root node.
    assert header == root.children[: len(header)] or all(h in root.children for h in header)
    assert all(f in root.children for f in footer)


def test_import_tree_bridge_external_objects() -> None:
    source = "def greet(name):\n    return name\n"

    # Two independently parsed, structurally identical modules stand in for
    # "an externally constructed LibCST object" the caller already has, as
    # opposed to one this plugin parsed itself.
    direct_module = libcst.parse_module(source)
    external_module = libcst.parse_module(source)

    direct_document = PythonImportMap().import_to_common(direct_module)
    bridged_document = import_tree(external_module)

    assert isinstance(bridged_document, Document)

    # Structure must match, but identity must not: every imported node gets a
    # fresh UUID4 per {p013}, so two independent imports of the same source are
    # structurally equal and identity-distinct.
    def shape(node):
        return (
            node.kind,
            node.buffer_range,
            tuple(sorted(k for k in node.fields)),
            tuple(shape(child) for child in node.children),
        )

    assert shape(bridged_document.root) == shape(direct_document.root)
    direct_ids = {n.node_id for n in walk(direct_document.root)}
    bridged_ids = {n.node_id for n in walk(bridged_document.root)}
    assert direct_ids.isdisjoint(bridged_ids)
    assert None not in direct_ids and None not in bridged_ids

    # The bridge also accepts a keyword-only `options` mapping, unused by
    # the import path but required for contract-signature compatibility.
    bridged_with_options = import_tree(libcst.parse_module(source), options={"any": "value"})
    assert shape(bridged_with_options.root) == shape(direct_document.root)

    # A bare externally constructed fragment CSTNode goes through the same
    # path as the main import direction (buffer_range stays None).
    external_fragment = libcst.parse_expression("1 + 2")
    bridged_fragment = import_tree(external_fragment)
    direct_fragment = PythonImportMap().import_to_common(libcst.parse_expression("1 + 2"))
    assert shape(bridged_fragment) == shape(direct_fragment)
    assert bridged_fragment.node_id != direct_fragment.node_id
    assert isinstance(bridged_fragment, Node)
    assert bridged_fragment.buffer_range is None


def test_import_to_common_rejects_non_cst_input() -> None:
    with pytest.raises(FormatPluginContractError) as excinfo:
        PythonImportMap().import_to_common("not a libcst tree")
    assert excinfo.value.plugin_id == "python"

    with pytest.raises(FormatPluginContractError):
        import_tree(42)

    with pytest.raises(FormatPluginContractError):
        PythonImportMap().import_to_common(None)
