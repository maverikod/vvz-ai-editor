"""Unit tests for the C-014 export direction of the Python translator
(tree_engine.plugins.python.export_map).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: exercises ``PythonExportMap.export_from_common`` and the
``export_tree`` bridge in isolation, paired with the merged
``PythonImportMap.import_to_common`` to build real common-model trees from
real LibCST parses -- no fabricated trees. The decisive property throughout
is the byte-identical round trip: parse with LibCST, import to the common
model, export back, compare bytes against LibCST's own regenerated output.
"""

from __future__ import annotations

import libcst
import pytest

from tree_engine.core.nodes import Document, make_node
from tree_engine.plugins.contract import FormatPluginContractError, UnsupportedTranslationError
from tree_engine.plugins.python.export_map import PythonExportMap, export_tree
from tree_engine.plugins.python.import_map import PythonImportMap, import_tree


def _roundtrip_module(source: bytes) -> bytes:
    module = libcst.parse_module(source)
    document = PythonImportMap().import_to_common(module)
    output = PythonExportMap().export_from_common(document)
    assert output == module.bytes
    return output


ROUND_TRIP_SOURCES = [
    pytest.param(b"x = 1\n", id="plain_lf"),
    pytest.param(b"x = 1\r\ny = 2\r\n", id="crlf_newlines"),
    pytest.param(b"x = 1", id="no_trailing_newline"),
    pytest.param(b"", id="empty_module"),
    pytest.param(b"# just a header\n", id="header_only_module"),
    pytest.param(
        b"# header comment\n\nx = 1\n\n# footer comment\n",
        id="header_footer_comments_blank",
    ),
    pytest.param(
        b"x: int = 1\ndef f(a: int, b: str = 'x') -> bool:\n    return True\n",
        id="type_annotations",
    ),
    pytest.param(b"a = b = 1\na, b = 1, 2\n", id="assignments"),
    pytest.param(
        b"def outer():\n    def inner():\n        pass\n    return inner\n",
        id="nested_functions",
    ),
    pytest.param(b"\n\n\nx = 1\n\n\n", id="blank_lines_only"),
    pytest.param(
        "# -*- coding: latin-1 -*-\nx = \"caf\u00e9\"\n".encode("latin-1"),
        id="encoding_cookie_latin1",
    ),
]


@pytest.mark.parametrize("source", ROUND_TRIP_SOURCES)
def test_common_model_tree_to_libcst(source: bytes) -> None:
    """Full documents round-trip byte-identically through import -> export,
    across the required variations: LF/CRLF newlines, presence/absence of a
    trailing newline, an empty module, a header-only module, header +
    footer + comments + blank lines, type annotations, assignments, nested
    functions, and a non-default (PEP 263 cookie) encoding."""

    _roundtrip_module(source)


def test_fragment_parse_and_export() -> None:
    """A bare fragment (not a full Module) round-trips through the import
    side's fragment path and the export side's ``str`` rendering path."""

    fragment = libcst.parse_expression("1 + 2 * (3 - 4)")
    node = PythonImportMap().import_to_common(fragment)
    output = PythonExportMap().export_from_common(node)

    expected = libcst.Module(body=[]).code_for_node(fragment)
    assert output == expected
    assert isinstance(output, str)

    statement_fragment = libcst.parse_statement("for x in range(3):\n    print(x)\n")
    statement_node = PythonImportMap().import_to_common(statement_fragment)
    statement_output = PythonExportMap().export_from_common(statement_node)
    assert statement_output == libcst.Module(body=[]).code_for_node(statement_fragment)


def test_encoding_defaults() -> None:
    """Encoding, indent, and newline defaults are applied correctly to the
    export output: a minimal common-model Module (only ``body`` set) relies
    on LibCST's own constructor defaults, and real non-default values
    captured on import (tab indent, CRLF newline, a PEP 263 encoding
    cookie) drive genuinely different output bytes."""

    minimal = make_node("python:Module", fields={"body": ()})
    minimal_output = PythonExportMap().export_from_common(Document(root=minimal, source_format_id="python"))
    assert minimal_output == libcst.Module(body=[]).bytes
    assert minimal_output == b"\n"

    tab_source = b"if True:\n\tpass\n"
    tab_module = libcst.parse_module(tab_source)
    tab_document = PythonImportMap().import_to_common(tab_module)
    assert tab_document.root.fields["default_indent"] == "\t"
    assert PythonExportMap().export_from_common(tab_document) == tab_module.bytes

    crlf_source = b"x = 1\r\ny = 2\r\n"
    crlf_module = libcst.parse_module(crlf_source)
    crlf_document = PythonImportMap().import_to_common(crlf_module)
    assert crlf_document.root.fields["default_newline"] == "\r\n"
    assert PythonExportMap().export_from_common(crlf_document) == crlf_module.bytes

    latin1_source = "# -*- coding: latin-1 -*-\nx = \"caf\u00e9\"\n".encode("latin-1")
    latin1_module = libcst.parse_module(latin1_source)
    latin1_document = PythonImportMap().import_to_common(latin1_module)
    assert latin1_document.root.fields["encoding"] == "iso-8859-1"
    latin1_output = PythonExportMap().export_from_common(latin1_document)
    assert latin1_output == latin1_module.bytes
    assert latin1_output == latin1_source


def test_export_trailing_newline_flag() -> None:
    """The ``has_trailing_newline`` flag alone controls whether the final
    newline is present in the exported bytes, both for the value LibCST
    itself parsed and for a value flipped directly on the common model
    (proving the exporter, not just the round trip, honors the flag)."""

    with_newline = PythonImportMap().import_to_common(libcst.parse_module(b"x = 1\n"))
    assert with_newline.root.fields["has_trailing_newline"] is True
    assert PythonExportMap().export_from_common(with_newline) == b"x = 1\n"

    without_newline = PythonImportMap().import_to_common(libcst.parse_module(b"x = 1"))
    assert without_newline.root.fields["has_trailing_newline"] is False
    assert PythonExportMap().export_from_common(without_newline) == b"x = 1"

    flipped_off_fields = dict(with_newline.root.fields)
    flipped_off_fields["has_trailing_newline"] = False
    flipped_off_root = make_node(
        with_newline.root.kind, fields=flipped_off_fields, children=with_newline.root.children
    )
    flipped_off = Document(root=flipped_off_root, source_format_id="python")
    assert PythonExportMap().export_from_common(flipped_off) == b"x = 1"

    flipped_on_fields = dict(without_newline.root.fields)
    flipped_on_fields["has_trailing_newline"] = True
    flipped_on_root = make_node(
        without_newline.root.kind, fields=flipped_on_fields, children=without_newline.root.children
    )
    flipped_on = Document(root=flipped_on_root, source_format_id="python")
    assert PythonExportMap().export_from_common(flipped_on) == b"x = 1\n"


def test_header_footer_restoration() -> None:
    """Module-level header and footer content (comments plus blank lines)
    is restored verbatim in the exported bytes, both for a full document
    and for a header-only module with an empty body."""

    source = (
        b"# file header comment\n"
        b"\n"
        b"x = 1\n"
        b"\n"
        b"# trailing footer comment\n"
    )
    module = libcst.parse_module(source)
    document = PythonImportMap().import_to_common(module)
    output = PythonExportMap().export_from_common(document)

    assert output == module.bytes
    assert output.startswith(b"# file header comment\n")
    assert output.endswith(b"# trailing footer comment\n")

    header_only_source = b"# just a header\n"
    header_only_module = libcst.parse_module(header_only_source)
    header_only_document = PythonImportMap().import_to_common(header_only_module)
    header_only_output = PythonExportMap().export_from_common(header_only_document)
    assert header_only_output == header_only_source


def test_unmapped_node_raises_unsupported() -> None:
    """A common-model node with no LibCST mapping raises
    UNSUPPORTED_TRANSLATION with the offending node identified, on the
    main ``export_from_common`` path -- both for a kind that is not even a
    Python plugin kind, and for a ``"python:"`` kind naming no libcst
    class, never silently dropped."""

    foreign_kind = make_node("bsl:Procedure", fields={})
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PythonExportMap().export_from_common(foreign_kind)
    assert excinfo.value.node_type == "bsl:Procedure"
    assert excinfo.value.format_id == "python"

    no_such_class = make_node("python:NotARealLibcstClass", fields={})
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PythonExportMap().export_from_common(no_such_class)
    assert excinfo.value.node_type == "python:NotARealLibcstClass"
    assert excinfo.value.format_id == "python"

    # "python:parse_module" names a real libcst attribute that is not a
    # CSTNode subclass at all (a function) -- still UNSUPPORTED_TRANSLATION.
    non_cst_attribute = make_node("python:parse_module", fields={})
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        PythonExportMap().export_from_common(non_cst_attribute)
    assert excinfo.value.node_type == "python:parse_module"


def test_export_tree_bridge_unmapped() -> None:
    """The ``export_tree`` bridge raises the identical UNSUPPORTED_TRANSLATION
    for the same unmapped-node cases as the main export path, node
    identification included."""

    foreign_kind = make_node("javascript:Program", fields={})
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        export_tree(foreign_kind)
    assert excinfo.value.node_type == "javascript:Program"
    assert excinfo.value.format_id == "python"

    no_such_class = make_node("python:TotallyUnknownKind", fields={})
    with pytest.raises(UnsupportedTranslationError) as excinfo:
        export_tree(no_such_class)
    assert excinfo.value.node_type == "python:TotallyUnknownKind"

    # A wrapped Document is covered too, via a root that is itself unmapped.
    bad_document = Document(root=make_node("python:NoSuchModuleClass", fields={}), source_format_id="python")
    with pytest.raises(UnsupportedTranslationError):
        export_tree(bad_document)


def test_export_tree_shape_libcst_compatible() -> None:
    """``export_tree`` returns the rebuilt LibCST object itself, restricted
    to the LibCST-compatible subset: a full ``Document`` must reconstruct
    into a ``libcst.Module`` (never anything else), a fragment ``Node``
    reconstructs into whatever ``CSTNode`` its kind names, and a
    ``Document`` whose root does not reconstruct into a ``Module`` is
    rejected as a contract violation rather than handed back mis-shaped."""

    source = b"def greet(name):\n    return name\n"
    module = libcst.parse_module(source)
    document = PythonImportMap().import_to_common(module)

    rebuilt_module = export_tree(document)
    assert isinstance(rebuilt_module, libcst.Module)
    assert rebuilt_module.bytes == module.bytes

    fragment = libcst.parse_expression("1 + 2")
    fragment_node = PythonImportMap().import_to_common(fragment)
    rebuilt_fragment = export_tree(fragment_node)
    assert isinstance(rebuilt_fragment, libcst.CSTNode)
    assert not isinstance(rebuilt_fragment, libcst.Module)
    assert libcst.Module(body=[]).code_for_node(rebuilt_fragment) == libcst.Module(body=[]).code_for_node(fragment)

    # A Document whose root reconstructs into a non-Module CSTNode (a bare
    # Name, not a Module) is not LibCST-compatible at the document level.
    non_module_root = make_node("python:Name", fields={"value": "x"})
    bad_document = Document(root=non_module_root, source_format_id="python")
    with pytest.raises(FormatPluginContractError):
        export_tree(bad_document)
    with pytest.raises(FormatPluginContractError):
        PythonExportMap().export_from_common(bad_document)

    # export_tree also rejects input that is neither Node nor Document.
    with pytest.raises(FormatPluginContractError):
        export_tree("not a common-model tree")

    # The bridge accepts the same keyword-only options as import_tree, for
    # contract-signature symmetry, unused by the export path itself.
    assert export_tree(document, options={"any": "value"}).bytes == module.bytes


def test_export_map_comprehensive() -> None:
    """A comprehensive end-to-end source spanning imports, a class with a
    docstring, a typed attribute, a constructor with an inline comment, a
    static method, augmented assignment, a for/if/else with continue, and
    an f-string-free join call -- all through import -> export, byte
    identical to LibCST's own regeneration."""

    source = (
        b"import os\n"
        b"from typing import List\n"
        b"\n"
        b"\n"
        b"class Greeter:\n"
        b'    """Docstring."""\n'
        b"\n"
        b"    count: int = 0\n"
        b"\n"
        b"    def __init__(self, name: str) -> None:\n"
        b"        self.name = name  # store it\n"
        b"        Greeter.count += 1\n"
        b"\n"
        b"    @staticmethod\n"
        b"    def greet(names: List[str]) -> str:\n"
        b"        result = []\n"
        b"        for n in names:\n"
        b"            if n:\n"
        b"                result.append(n)\n"
        b"            else:\n"
        b"                continue\n"
        b'        return ", ".join(result)\n'
    )

    module = libcst.parse_module(source)
    document = PythonImportMap().import_to_common(module)
    output = PythonExportMap().export_from_common(document)

    assert output == module.bytes
    assert output == source

    # Same source through the import_tree/export_tree bridge must agree.
    bridged_document = import_tree(libcst.parse_module(source))
    bridged_module = export_tree(bridged_document)
    assert bridged_module.bytes == source
