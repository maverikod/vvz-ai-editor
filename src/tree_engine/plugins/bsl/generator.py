"""Common-model-to-BSL export and output generation for the BSL translator
(concept C-015).

Scope (narrowed to the EXPORT/GENERATE direction only, per this step's
brief): tree-sitter-bsl provides no reverse generator, so this module is
where the BSL plugin owns both its own generation-ready representation and
the rules that render it into final bytes ({p105}). It is the sibling and
mirror image of the already-merged ``import_map.py``: every construct that
module singles out for special treatment (variable_declaration, annotation,
the by-value parameter modifier) gets a matching generation rule here,
selected from ``dialects.py`` so no keyword spelling is hard-coded.

Generation strategy:

* A generic node (kind ``"bsl:<tree-sitter node type>"``) carries, in its
  own ``content`` field, the exact original source text of its whole
  subtree ({p047}). A leaf (no children) is rendered by re-emitting
  ``content`` -- reusing unchanged bytes per {p105} with no live buffer
  needed. When ``options["buffer"]``/``options["source"]`` *is* supplied,
  its bytes are preferred over ``content`` for any node still carrying a
  valid ``buffer_range``, per {p105}'s literal wording.
* A generic node *with* children is rendered by gap-stitching: each child
  renders recursively (so a change anywhere below propagates upward,
  however deeply nested), and the byte runs *between* children
  (punctuation, un-mapped keywords, whitespace) are copied from the
  parent's own captured span -- so an edited descendant surfaces correctly
  while the rest of an unchanged document is still reproduced by straight
  byte copying.
* :class:`~tree_engine.core.node_types.VariableDeclarationNode`,
  :class:`~tree_engine.core.node_types.AnnotationNode` (when its
  ``annotation_kind`` was recognized on import) and the by-value parameter
  modifier are rendered from their own stored fields via
  ``dialects.keyword_for_target_dialect``/``dialects.get_annotation_form``,
  so a changed or freshly constructed node still renders correct BSL
  syntax in the document's own dialect ({p105}, {p115}). The written
  keyword forms are single-space-separated, matching tree-sitter-bsl's own
  grammar exactly (verified against real parses), so this same rule also
  reproduces an untouched node's original bytes exactly -- no separate
  "did this change" detection is needed.
* :class:`~tree_engine.core.node_types.PreprocessorDirectiveNode` has no
  BSL-specific child interpretation to invert ({p043}), so it is always
  reproduced from its own captured ``content`` verbatim.
* The document's own dialect is auto-detected by scanning for the first
  recognized keyword token or annotation prefix via ``dialects``' own
  lookup tables, and can be overridden with ``options["dialect"]``; every
  synthesized keyword uses this one resolved dialect, honoured
  consistently throughout the output ({p047}, {p105}).
* A node kind this plugin does not own (not ``"bsl:"``- or
  ``"core:"``-prefixed) raises
  :class:`~tree_engine.plugins.contract.UnsupportedTranslationError`
  (``ErrorCode.UNSUPPORTED_TRANSLATION``), naming the offending kind.

``export_from_common`` returns a small immutable :class:`BSLGenerationTree`
-- the generation-ready representation ({p105}) -- and ``generate_output``
renders it, or (running ``export_from_common`` internally) a bare
common-model ``Node``/``Document`` directly, per
``FormatPluginContract.generate_output``'s own documented allowance.

Source-of-truth requirement labels honored here: {p043}, {p044}, {p047},
{p105}, {p115}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple, Union

from tree_engine.core.buffer import SourceBuffer
from tree_engine.core.node_types import (
    AnnotationNode,
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.nodes import Document, Node, walk
from tree_engine.plugins.bsl import dialects
from tree_engine.plugins.contract import FormatPluginContractError, UnsupportedTranslationError

__all__ = [
    "FORMAT_ID",
    "BSLGenerationTree",
    "BSLGenerator",
    "export_from_common",
    "generate_output",
]

FORMAT_ID = "bsl"

_GENERIC_PREFIX = "bsl:"
_PARAMETER_KIND = f"{_GENERIC_PREFIX}parameter"
_VAR_DECL_KIND = VariableDeclarationNode._KIND
_VAR_DECLARATOR_KIND = VariableDeclaratorNode._KIND
_ANNOTATION_KIND = AnnotationNode._KIND
_PREPROC_KIND = PreprocessorDirectiveNode._KIND


@dataclass(frozen=True)
class BSLGenerationTree:
    """The BSL plugin's own generation-ready representation ({p105}):
    the common-model subtree to render, the single keyword dialect every
    synthesized token in the render must use, and the optional original
    source bytes (from a live piece-table/rope buffer, when supplied) that
    unchanged spans are preferred to be copied from."""

    root: Node
    dialect: str
    source_bytes: Optional[bytes] = None


def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, message=message)


def _unsupported(node_kind: str) -> UnsupportedTranslationError:
    return UnsupportedTranslationError(
        node_type=node_kind, format_id=FORMAT_ID,
        message=f"BSL generator has no rendering rule for node kind {node_kind!r}",
    )


def _resolve_root(common_tree: Union[Node, Document]) -> Node:
    if isinstance(common_tree, Document):
        return common_tree.root
    if isinstance(common_tree, Node):
        return common_tree
    raise _contract_error(f"expected a common-model Node or Document, got {type(common_tree).__name__}")


def _resolve_source_bytes(options: Mapping[str, Any]) -> Optional[bytes]:
    buffer = options.get("buffer")
    if isinstance(buffer, SourceBuffer):
        return buffer.serialize()
    source = options.get("source")
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    return None


def _detect_dialect(root: Node) -> str:
    """Scan ``root``'s subtree for the first recognized keyword token or
    annotation prefix and return the dialect it belongs to, defaulting to
    :data:`dialects.RUSSIAN` when nothing recognizable is found (e.g. an
    empty document)."""

    for node in walk(root):
        content = node.fields.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        token = content.strip()
        kind = str(node.kind)
        if kind.endswith("_KEYWORD"):
            if dialects.get_canonical_keyword(token, dialects.RUSSIAN) is not None:
                return dialects.RUSSIAN
            if dialects.get_canonical_keyword(token, dialects.ENGLISH) is not None:
                return dialects.ENGLISH
        elif kind == _ANNOTATION_KIND:
            if dialects.is_annotation_prefix(token, dialects.RUSSIAN) is not None:
                return dialects.RUSSIAN
            if dialects.is_annotation_prefix(token, dialects.ENGLISH) is not None:
                return dialects.ENGLISH
    return dialects.RUSSIAN


def _resolve_dialect(root: Node, options: Mapping[str, Any]) -> str:
    override = options.get("dialect")
    if override is not None:
        return dialects.normalize_dialect(override)
    return _detect_dialect(root)


def export_from_common(
    common_tree: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
) -> BSLGenerationTree:
    """Translate a common-model ``Document``/``Node`` into this plugin's
    own generation-ready representation ({p105}): resolves which subtree to
    render, the one keyword dialect to honour throughout, and the original
    bytes (if a live buffer/source was supplied via ``options``) unchanged
    spans are preferred to be copied from.

    ``options`` recognizes ``"dialect"`` (an explicit override, normalized
    via :func:`dialects.normalize_dialect`), ``"buffer"`` (a
    :class:`~tree_engine.core.buffer.SourceBuffer`) and ``"source"``
    (raw ``bytes``); all are optional.
    """

    resolved_options = options or {}
    root = _resolve_root(common_tree)
    dialect = _resolve_dialect(root, resolved_options)
    source_bytes = _resolve_source_bytes(resolved_options)
    return BSLGenerationTree(root=root, dialect=dialect, source_bytes=source_bytes)


def _leaf_bytes(node: Node, source_bytes: Optional[bytes]) -> bytes:
    """The exact bytes of one node with no rule-based rendering of its
    own: preferably a slice of a live buffer's bytes at the node's own
    ``buffer_range`` ({p105}), falling back to the node's own captured
    ``content`` field (itself an exact original-text capture at import
    time, per ``import_map.py``)."""

    if source_bytes is not None and node.buffer_range is not None:
        start, end = node.buffer_range
        if 0 <= start <= end <= len(source_bytes):
            return source_bytes[start:end]
    content = node.fields.get("content", "")
    return content if isinstance(content, bytes) else str(content).encode("utf-8")


def _stitch(
    node: Node, children: Tuple[Node, ...], start_abs: int, dialect: str, source_bytes: Optional[bytes]
) -> bytes:
    """Render ``children`` (a node's own children, or a trailing slice of
    them) recursively, filling the byte gaps between consecutive children
    -- punctuation, un-mapped keywords, whitespace -- from ``node``'s own
    captured span, starting at the absolute byte offset ``start_abs``.
    A changed or newly rendered child's bytes are substituted in place of
    whatever the parent's own captured span held there, so a change at any
    depth surfaces correctly in the stitched result."""

    own_bytes = _leaf_bytes(node, source_bytes)
    base = node.buffer_range[0] if node.buffer_range is not None else 0
    cursor = max(0, start_abs - base)
    pieces = []
    for child in children:
        child_bytes = _render(child, dialect, source_bytes)
        child_range = child.buffer_range
        if child_range is not None and node.buffer_range is not None:
            rel_start = child_range[0] - base
            rel_end = child_range[1] - base
            if 0 <= rel_start <= len(own_bytes) and rel_start >= cursor:
                pieces.append(own_bytes[cursor:rel_start])
                pieces.append(child_bytes)
                cursor = max(cursor, min(rel_end, len(own_bytes)))
                continue
        pieces.append(child_bytes)
    pieces.append(own_bytes[cursor:])
    return b"".join(pieces)


def _render_generic(node: Node, dialect: str, source_bytes: Optional[bytes]) -> bytes:
    if not node.children or node.buffer_range is None:
        return _leaf_bytes(node, source_bytes)
    return _stitch(node, node.children, node.buffer_range[0], dialect, source_bytes)


def _render_var_decl(node: Node, dialect: str) -> bytes:
    """Render a :class:`VariableDeclarationNode` from its own
    ``declarators``/``separators``/``export`` fields ({iblr}/{p044}): exact
    original inter-declarator separators reused verbatim, keywords chosen
    for ``dialect`` via ``dialects``."""

    wrapper = VariableDeclarationNode.from_node(node)
    parts = [dialects.keyword_for_target_dialect(dialects.VAR, dialect), " "]
    declarators = wrapper.declarators
    separators = wrapper.separators
    for index, declarator in enumerate(declarators):
        if index > 0 and index - 1 < len(separators):
            parts.append(separators[index - 1])
        parts.append(declarator.name)
    if wrapper.export:
        parts.append(" ")
        parts.append(dialects.keyword_for_target_dialect(dialects.EXPORT, dialect))
    parts.append(";")
    return "".join(parts).encode("utf-8")


def _render_annotation(node: Node, dialect: str) -> bytes:
    """Render an :class:`AnnotationNode`: when its ``annotation_kind`` was
    recognized on import, the canonical prefix is rendered for ``dialect``
    via :func:`dialects.get_annotation_form` ({an01}, {p047}), followed by a
    parenthesized, separator-joined argument list when arguments are
    present. An unrecognized annotation (no ``annotation_kind``) has no
    rule to invert and is reproduced from its own captured ``content``."""

    kind = node.fields.get("annotation_kind")
    if kind is None:
        return str(node.fields.get("content", "")).encode("utf-8")
    prefix = dialects.get_annotation_form(kind, dialect).encode("utf-8")
    wrapper = AnnotationNode.from_node(node)
    arguments = wrapper.arguments
    if not arguments:
        return prefix
    separators = wrapper.argument_separators
    rendered = [_render(argument, dialect, None) for argument in arguments]
    body = [rendered[0]]
    for index in range(1, len(rendered)):
        sep = separators[index - 1].encode("utf-8") if index - 1 < len(separators) else b""
        body.append(sep)
        body.append(rendered[index])
    return prefix + b"(" + b"".join(body) + b")"


def _strip_leading_modifier(text: str) -> str:
    """When ``text`` opens with the by-value modifier token (either
    dialect, per {p115}), return the remainder with that token and its
    following run of spaces/tabs removed; otherwise return ``text``
    unchanged. Used to avoid double-emitting the modifier when a
    ``by_value`` parameter's own captured text already carries it."""

    left = text.lstrip(" \t")
    for sep in (" ", "\t"):
        token, found, remainder = left.partition(sep)
        if found and dialects.is_by_value_modifier(token):
            return remainder.lstrip(" \t")
    return text


def _render_parameter(node: Node, dialect: str, source_bytes: Optional[bytes]) -> bytes:
    """Render a ``bsl:parameter`` node: reconstruct its full text
    generically (so a nested change still surfaces), then add or remove the
    by-value modifier at the front to match ``by_value`` exactly, in
    ``dialect``'s written form ({p115}). No attribute means no modifier."""

    rendered = _render_generic(node, dialect, source_bytes)
    text = rendered.decode("utf-8")
    rest = _strip_leading_modifier(text)
    if bool(node.fields.get(dialects.BY_VALUE, False)):
        keyword = dialects.keyword_for_target_dialect(dialects.BY_VALUE, dialect)
        return f"{keyword} {rest}".encode("utf-8")
    return rest.encode("utf-8")


def _render(node: Node, dialect: str, source_bytes: Optional[bytes]) -> bytes:
    """Dispatch one common-model node to its rendering rule and return its
    exact BSL bytes, in ``dialect``."""

    kind = node.kind
    if kind == _VAR_DECL_KIND:
        return _render_var_decl(node, dialect)
    if kind == _VAR_DECLARATOR_KIND:
        return str(node.fields.get("name", "")).encode("utf-8")
    if kind == _ANNOTATION_KIND:
        return _render_annotation(node, dialect)
    if kind == _PREPROC_KIND:
        return _leaf_bytes(node, source_bytes)
    if kind == _PARAMETER_KIND:
        return _render_parameter(node, dialect, source_bytes)
    if not str(kind).startswith(_GENERIC_PREFIX):
        raise _unsupported(str(kind))
    return _render_generic(node, dialect, source_bytes)


def generate_output(
    target: Union[BSLGenerationTree, Node, Document], options: Optional[Mapping[str, Any]] = None
) -> bytes:
    """Render ``target`` into final BSL source bytes.

    ``target`` is either an already-built :class:`BSLGenerationTree` (the
    normal two-step path, via :func:`export_from_common`) or a bare
    common-model ``Node``/``Document``, in which case
    :func:`export_from_common` is run internally first, per
    ``FormatPluginContract.generate_output``'s own documented allowance to
    combine the stages behind one call.

    Raises :class:`~tree_engine.plugins.contract.UnsupportedTranslationError`
    for a node kind this plugin does not own, and
    :class:`~tree_engine.plugins.contract.FormatPluginContractError` for any
    other kind of ``target``.
    """

    resolved_options = options or {}
    if isinstance(target, BSLGenerationTree):
        representation = target
    elif isinstance(target, (Node, Document)):
        representation = export_from_common(target, resolved_options)
    else:
        raise _contract_error(
            f"cannot generate BSL output for {type(target).__name__}; expected a "
            "BSLGenerationTree, Node, or Document"
        )
    return _render(representation.root, representation.dialect, representation.source_bytes)


class BSLGenerator:
    """Export (common model -> generation-ready representation) and
    generate (representation -> bytes) stages of the BSL translator.

    Supplies the export half of the bidirectional translator described by
    ``tree_engine.plugins.contract.FormatPluginContract`` ({p056}, {p057});
    the import stage is delivered by the sibling, already-merged
    ``BSLImportMap``, and the remaining contract surface (``metadata``,
    ``parse_document``, ...) is composed later.
    """

    def export_from_common(
        self, common_tree: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> BSLGenerationTree:
        """Translate a common-model ``Document``/``Node`` into this
        plugin's own generation-ready representation; see the module-level
        :func:`export_from_common` for the full contract."""

        return export_from_common(common_tree, options)

    def generate_output(
        self, target: Union[BSLGenerationTree, Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> bytes:
        """Render ``target`` into final BSL source bytes; see the
        module-level :func:`generate_output` for the full contract."""

        return generate_output(target, options)
