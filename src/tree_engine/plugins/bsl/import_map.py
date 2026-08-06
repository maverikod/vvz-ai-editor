"""tree-sitter-bsl-to-common-model import pipeline for the BSL translator
(concept C-015).

Scope (narrowed to the IMPORT direction only, per this step's brief): this
module converts an already-parsed tree-sitter-bsl 0.1.6 parse tree node
into a common-model :class:`~tree_engine.core.nodes.Node`
(concept C-002), mapping the constructs {p047}/{p044}/{p043}/{an01}/{iblr}/
{p115} single out for explicit treatment, and preserving everything else
losslessly as an extensible node. The EXPORT direction and the
``FormatPluginContract``/``FormatBoundary`` composition are sibling steps'
concern and are not implemented here.

Mapping rules, per the governing HRS fragments:

* ``var_statement``/``var_definition`` (a tree-sitter-bsl grammar
  distinction between an in-procedure and a module-level declaration,
  collapsed here into one code path) -> :class:`VariableDeclarationNode`
  with ordered :class:`VariableDeclaratorNode` children, one per declared
  identifier, separated by the exact original inter-declarator source
  bytes ({iblr}). A trailing ``EXPORT_KEYWORD`` sets the declaration's
  ``export`` field ({p044}, {p047}); export is not propagated onto
  individual declarators, mirroring the grammar's own placement of the
  keyword at the statement level.
* a ``preprocessor`` node wrapping a nested ``annotation`` node (the
  grammar's own representation of ``&НаСервере``/``&AtServer``-style
  constructs) -> :class:`AnnotationNode`, keyed to its own inner byte
  range, never combined with :class:`PreprocessorDirectiveNode` ({an01}).
  Any other ``preprocessor`` node (``#Если``/``#If`` and friends) ->
  :class:`PreprocessorDirectiveNode`, kept flat (no BSL-specific child
  interpretation), per {p043}.
* a ``parameter`` node whose own children contain the by-value modifier
  token (``Знач``/``Val``, detected via
  :func:`tree_engine.plugins.bsl.dialects.is_by_value_modifier` rather than
  by tree-sitter node-kind name) gets a ``by_value`` field set ``True`` on
  its mapped node; absent otherwise ({p115}).
* everything else that parsed without error -- ``procedure_definition``,
  ``function_definition``, expressions, statements, individual keyword and
  punctuation tokens, and so on -- becomes a plain extensible
  :class:`~tree_engine.core.nodes.Node` of kind ``"bsl:<tree-sitter node
  type>"`` (mirroring the ``"python:<LibCST class name>"`` convention
  already used by the Python translator's import map), carrying its own
  raw byte span and content, with no synthetic wrapper type invented for
  it, so a future plugin revision may interpret or upgrade it ({p047}).
  Its children are converted the same way, recursively, so a mapped
  construct nested at any depth (e.g. a ``var_statement`` inside a
  procedure body) is still recognized by the same dispatch.

Both keyword dialects are handled by this single code path: tree-sitter-
bsl's own grammar already unifies ``Процедура``/``Procedure``,
``Перем``/``Var``, ``Экспорт``/``Export`` and so on under one node type per
construct, so no dialect branch is needed for the constructs above; the
one dialect-sensitive decision left to this module -- the by-value
modifier and the annotation-prefix canonical label -- is delegated to
``dialects.py`` rather than re-encoded here. The original written keyword
form is preserved verbatim in every mapped node's ``content`` field (never
canonicalized), so round-trip generation later restores the document's own
dialect exactly.

Per {p104}, detecting ``has_error``/``ERROR``/missing nodes and choosing
between ``FORMAT_CONTENT_PARSE_FAILED`` and ``FORMAT_FRAGMENT_PARSE_FAILED``
is primarily the responsibility of the calling ``parse_document``/
``parse_fragment`` logic (not yet merged); this module's own walk only maps
already-valid trees. As a defense-in-depth backstop against ever
synthesizing a partial common-model tree from damaged input, ``import_to_
common`` still refuses upfront -- via a loud
:class:`~tree_engine.plugins.contract.FormatPluginContractError` carrying
the appropriate one of those two codes -- to walk a tree-sitter node that
itself reports ``has_error`` (tree-sitter propagates this up through every
ancestor of an ``ERROR`` or ``MISSING`` descendant, so a single check on
the node handed to this function is sufficient).

No tree-sitter node kinds leak into the core: every ``Node`` this module
returns carries only an opaque, plugin-namespaced ``NodeKind`` string, a
plain ``fields`` mapping, and a ``children`` tuple of further ``Node``
values -- the shapes ``tree_engine.core.nodes.make_node`` already
validates. No tree-sitter object is retained or returned once
``import_to_common`` returns.

Source-of-truth requirement labels honored here: {p043}, {an01}, {p044},
{p046}, {p047}, {p104}, {iblr}, {p115}.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Mapping, Optional, TYPE_CHECKING, Tuple

from tree_engine.core.node_types import (
    AnnotationNode,
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.nodes import Node, make_node
from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl import dialects
from tree_engine.plugins.contract import FormatPluginContractError

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

__all__ = [
    "FORMAT_ID",
    "BSLImportMap",
    "import_to_common",
]

FORMAT_ID = "bsl"

_KIND_PREFIX = "bsl:"
_VAR_DECLARATION_TYPES = ("var_statement", "var_definition")
_IDENTIFIER_TYPE = "identifier"
_EXPORT_KEYWORD_TYPE = "EXPORT_KEYWORD"
_PREPROCESSOR_TYPE = "preprocessor"
_ANNOTATION_TYPE = "annotation"
_PARAMETER_TYPE = "parameter"


def _contract_error(message: str, *, code: ErrorCode) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, error_code=code, message=message)


def _text(ts_node: "TSNode") -> str:
    """The exact original source text of ``ts_node``, decoded as UTF-8."""

    raw = ts_node.text
    return raw.decode("utf-8") if raw is not None else ""


def _slice(container: "TSNode", start_byte: int, end_byte: int) -> str:
    """The exact original source text spanning ``[start_byte, end_byte)``,
    sliced out of ``container``'s own text via relative byte offsets --
    used for inter-declarator separators, which are not themselves a
    tree-sitter node."""

    raw = container.text
    if raw is None:
        return ""
    base = container.start_byte
    return raw[start_byte - base : end_byte - base].decode("utf-8")


def _convert_generic(ts_node: "TSNode") -> Node:
    """Fallback mapping for any tree-sitter-bsl node with no explicit
    construct-specific treatment: a flat, plugin-namespaced extensible
    ``Node`` (no synthetic wrapper type) carrying its own raw byte span and
    content, with every child converted the same way, recursively, so a
    mapped construct nested at any depth is still recognized."""

    kind = f"{_KIND_PREFIX}{ts_node.type}"
    children = tuple(_convert(child) for child in ts_node.children)
    node = make_node(kind, fields={"content": _text(ts_node)}, children=children)
    return dataclasses.replace(node, buffer_range=(ts_node.start_byte, ts_node.end_byte))


def _convert_parameter(ts_node: "TSNode") -> Node:
    """A procedure/function ``parameter`` node: the generic mapping, plus a
    ``by_value`` field when one of its own children is the by-value
    passing-mode modifier in either dialect, detected purely via
    ``dialects.is_by_value_modifier`` -- never by tree-sitter node-kind
    name -- so the same code path covers ``Знач`` and ``Val`` alike
    ({p115})."""

    base = _convert_generic(ts_node)
    is_by_value = any(dialects.is_by_value_modifier(_text(child)) for child in ts_node.children)
    if not is_by_value:
        return base
    fields = dict(base.fields)
    fields[dialects.BY_VALUE] = True
    rebuilt = make_node(base.kind, fields=fields, children=base.children)
    return dataclasses.replace(rebuilt, buffer_range=base.buffer_range)


def _convert_preprocessor(ts_node: "TSNode") -> Node:
    """A ``preprocessor`` node: either the wrapper around a recognized
    ``annotation`` construct -- mapped to a standalone
    :class:`AnnotationNode`, keyed to the inner node's own byte range, and
    never combined with :class:`PreprocessorDirectiveNode` ({an01}) -- or
    any other preprocessor construct (``#Если``/``#If`` and friends),
    mapped flat to :class:`PreprocessorDirectiveNode` with no BSL-specific
    child interpretation ({p043})."""

    annotation_child = next(
        (child for child in ts_node.children if child.type == _ANNOTATION_TYPE), None
    )
    if annotation_child is not None:
        content = _text(annotation_child)
        canonical = dialects.is_annotation_prefix(content)
        extra: Dict[str, Any] = {"annotation_kind": canonical} if canonical is not None else {}
        wrapped = AnnotationNode(
            start_byte=annotation_child.start_byte,
            end_byte=annotation_child.end_byte,
            content=content,
            **extra,
        )
        return wrapped.node

    wrapped = PreprocessorDirectiveNode(
        start_byte=ts_node.start_byte, end_byte=ts_node.end_byte, content=_text(ts_node)
    )
    return wrapped.node


def _convert_var_declaration(ts_node: "TSNode") -> Node:
    """A ``var_statement`` (in-procedure) or ``var_definition``
    (module-level) node -- the same tree-sitter-bsl grammar distinction
    collapsed here into one code path -- mapped to one
    :class:`VariableDeclarationNode` whose ordered children are one
    :class:`VariableDeclaratorNode` per declared identifier, with the
    exact original inter-declarator source bytes preserved as separators,
    per {iblr}. A trailing ``EXPORT_KEYWORD`` child sets the declaration's
    ``export`` field ({p044}, {p047}); it is not propagated onto
    individual declarators, since the grammar itself attaches the keyword
    once, at the statement level."""

    identifiers: List["TSNode"] = [
        child for child in ts_node.children if child.type == _IDENTIFIER_TYPE
    ]
    has_export = any(child.type == _EXPORT_KEYWORD_TYPE for child in ts_node.children)

    declarators = [
        VariableDeclaratorNode(
            start_byte=ident.start_byte,
            end_byte=ident.end_byte,
            content=_text(ident),
            name=_text(ident),
        )
        for ident in identifiers
    ]
    separators = [
        _slice(ts_node, prev.end_byte, nxt.start_byte)
        for prev, nxt in zip(identifiers, identifiers[1:])
    ]

    wrapped = VariableDeclarationNode(
        start_byte=ts_node.start_byte,
        end_byte=ts_node.end_byte,
        content=_text(ts_node),
        declarators=declarators,
        separators=separators,
        export=has_export,
    )
    return wrapped.node


def _convert(ts_node: "TSNode") -> Node:
    """Dispatch one tree-sitter-bsl node to its mapped common-model
    ``Node``, per this module's mapping rules. Every branch ultimately
    returns a plain, already-validated ``Node`` -- wrapper types
    (:class:`AnnotationNode` and friends) are unwrapped to their own
    ``.node`` immediately, so a parent's ``children`` tuple never holds
    anything but base ``Node`` instances, satisfying
    ``tree_engine.core.nodes.make_node``'s own shape contract."""

    node_type = ts_node.type
    if node_type in _VAR_DECLARATION_TYPES:
        return _convert_var_declaration(ts_node)
    if node_type == _PREPROCESSOR_TYPE:
        return _convert_preprocessor(ts_node)
    if node_type == _PARAMETER_TYPE:
        return _convert_parameter(ts_node)
    return _convert_generic(ts_node)


def import_to_common(
    external_representation: "TSNode",
    options: Optional[Mapping[str, Any]] = None,
    *,
    fragment: bool = False,
) -> Node:
    """Translate an already-parsed tree-sitter-bsl ``Node`` (a document's
    root, or a subtree for fragment use) into a common-model ``Node``,
    walking the tree per this module's mapping rules.

    ``options`` is accepted for contract-signature compatibility and
    currently unused. Pass ``fragment=True`` when ``external_representation``
    is a local fragment rather than a whole document's root, so a rejected
    damaged tree is reported under ``FORMAT_FRAGMENT_PARSE_FAILED`` instead
    of ``FORMAT_CONTENT_PARSE_FAILED`` ({p104}).

    Raises :class:`~tree_engine.plugins.contract.FormatPluginContractError`
    -- carrying whichever of those two codes applies -- when
    ``external_representation`` itself reports ``has_error`` (tree-sitter
    propagates this up through every ancestor of any ``ERROR`` or
    ``MISSING`` descendant, so this single check catches damage anywhere in
    the subtree being imported): this module maps only already-valid parse
    trees and never synthesizes a partial common-model tree from one that
    is not, even though primary classification for a whole document or
    fragment is the calling ``parse_document``/``parse_fragment`` logic's
    responsibility.
    """

    if getattr(external_representation, "has_error", False):
        code = ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED if fragment else ErrorCode.FORMAT_CONTENT_PARSE_FAILED
        raise _contract_error(
            "tree-sitter-bsl parse tree contains an ERROR or MISSING node; "
            "refusing to map a partial tree",
            code=code,
        )
    return _convert(external_representation)


class BSLImportMap:
    """Import (tree-sitter-bsl -> common model) stage of the BSL
    translator.

    Supplies the ``import_to_common`` stage that
    ``tree_engine.plugins.contract.FormatPluginContract`` requires
    ({p046}, {p056}, {p057}); ``parse_document``/``parse_fragment`` (which
    own the ``has_error`` primary classification, per {p104}), the export
    stage, and the remaining contract surface are delivered by sibling
    steps and composed with this class later.
    """

    def import_to_common(
        self,
        external_representation: "TSNode",
        options: Optional[Mapping[str, Any]] = None,
        *,
        fragment: bool = False,
    ) -> Node:
        """Translate an already-parsed tree-sitter-bsl ``Node`` into a
        common-model ``Node``; see the module-level :func:`import_to_common`
        for the full contract."""

        return import_to_common(external_representation, options, fragment=fragment)
