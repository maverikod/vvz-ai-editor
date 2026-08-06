"""LibCST-to-common-model import pipeline for the Python translator (C-014).

Scope (concept C-014, narrowed to the IMPORT direction only): this module
converts an already-parsed LibCST ``Module`` or ``CSTNode`` into a
common-model tree (:class:`~tree_engine.core.nodes.Node` /
:class:`~tree_engine.core.nodes.Document`, concept C-002), mapping every
CST field, trivia item, comment, whitespace piece, blank line, byte range,
encoding, default indent, default newline, trailing-newline flag, header,
and footer so nothing needed for a byte-identical regeneration is dropped.
It also exposes ``import_tree``, the import side of the ``import_tree``/
``export_tree`` bridge {p048} used for externally supplied LibCST objects.

The EXPORT direction (common model -> LibCST -> source bytes) and
``UNSUPPORTED_TRANSLATION`` are a sibling step's concern and are not
implemented here ({p048}, {p103}). ``PythonImportMap`` is not itself a
complete :class:`~tree_engine.plugins.contract.FormatPluginContract`
implementation -- it supplies that contract's ``import_to_common`` stage
only; a later step composes it with the export side into the full plugin.

Translation strategy -- generic, not per-node-kind: LibCST is itself a
"full-fidelity" concrete syntax tree, so whitespace, comments, blank lines
(``EmptyLine``), and trailing/leading trivia are *already* first-class
``CSTNode`` values sitting in ordinary dataclass fields (e.g.
``FunctionDef.leading_lines``, ``Module.header``). Recursively walking
every ``dataclasses.fields()`` entry of every ``CSTNode`` therefore already
captures all of it, with no hand-maintained per-node-kind mapping table to
fall out of sync. Each LibCST node becomes one common-model ``Node`` whose
``kind`` is ``"python:<LibCST class name>"`` (mirroring the
``"core:<name>"`` convention already used by
``tree_engine.core.node_types``) and whose ``fields`` mirror the CST
node's own dataclass fields by name, with nested ``CSTNode`` values
converted the same way and stored either as a single ``Node`` field value
or as an ordered tuple of ``Node`` (for ``Sequence[CSTNode]`` fields, e.g.
``header``/``footer``/``body``) -- exactly the shapes
:func:`tree_engine.core.nodes.make_node` already validates.

Two kinds of non-``CSTNode`` values need an explicit, generic encoding so
they still fit the common model's ``FieldValue`` union (primitive, single
``Node``, or tuple of ``Node``) without ever being silently dropped:

* An ``enum.Enum`` member (LibCST's only such field value is
  ``MaybeSentinel.DEFAULT``, the sentinel meaning "no explicit whitespace
  override here, LibCST decides") becomes a marker ``Node`` of kind
  ``"python:$sentinel"`` carrying the enum's fully qualified class name and
  member name -- never approximated as ``None`` or a plain string, which
  would be ambiguous with a real field value.
* A primitive appearing as an element of a ``Sequence``/``tuple`` field
  (the common model requires every tuple entry to be a ``Node``, per
  ``nodes.py``) is wrapped in a marker ``Node`` of kind ``"python:$scalar"``
  carrying the primitive under ``"value"``. No such field exists in this
  LibCST version's node set at the time of writing, but the wrapper keeps
  the converter correct if one is ever added upstream, without special
  casing any specific node kind.

Any other, genuinely unrepresentable value (not ``None``, not a primitive,
not a ``CSTNode``, not an ``enum.Enum`` member, not a sequence of the
above) raises :class:`~tree_engine.plugins.contract.FormatPluginContractError`
loudly -- never a silent drop. Per this step's brief, ``UNSUPPORTED_TRANSLATION``
is reserved for the export side; an import-side failure is a plugin
internal-contract violation instead, which is exactly what
``FormatPluginContractError`` (already defined by the merged
``plugins/contract.py``) models.

Byte ranges ({p102}) are resolved once, up front, via LibCST's own
``ByteSpanPositionProvider`` metadata provider over a ``MetadataWrapper``
-- only when the top-level input is a ``Module`` (a bare fragment
``CSTNode`` has no absolute document position to anchor a byte offset to,
so its nodes keep the base schema's ordinary ``buffer_range=None``
default; nothing is lost, since there is no absolute buffer for it to
range over) -- and attached to each converted node's existing reserved
``buffer_range`` slot on :class:`~tree_engine.core.nodes.Node` (the same
slot ``tree_engine.core.node_types`` already uses for this purpose).
``MetadataWrapper`` and every LibCST object it or this module touches are
local to the single conversion call: the returned common-model tree is
built exclusively from primitives, ``str``, and ``Node`` instances (the
base schema's own ``make_node`` validation rejects anything else at
construction time), so no LibCST object is reachable, retained, or
returned once ``import_to_common``/``import_tree`` returns.

A full document is wrapped as a :class:`~tree_engine.core.nodes.Document`
whose ``root`` is the converted ``"python:Module"`` node; that node's own
``fields`` already carry ``encoding``, ``default_indent``,
``default_newline``, ``has_trailing_newline``, ``header``, and ``footer``
verbatim, because those are simply ``Module``'s own dataclass fields --
this module attaches no side-channel duplicate of them.

Source-of-truth requirement labels honored here: {p008}, {p022}, {p048},
{p102}.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import libcst
from libcst.metadata import ByteSpanPositionProvider, MetadataWrapper

from tree_engine.core.nodes import Document, FieldValue, Node, make_node
from tree_engine.plugins.contract import FormatPluginContractError

__all__ = [
    "FORMAT_ID",
    "PythonImportMap",
    "import_tree",
]

FORMAT_ID = "python"

_KIND_PREFIX = "python:"
_SENTINEL_KIND = f"{_KIND_PREFIX}$sentinel"
_SCALAR_KIND = f"{_KIND_PREFIX}$scalar"

# Byte spans resolved by LibCST's metadata provider: node -> (start, end).
_SpanMap = Mapping[Any, Any]


def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, message=message)


def _marker_node(kind: str, fields: Mapping[str, Any]) -> Node:
    """Build a synthetic, non-CST marker ``Node`` (a sentinel or a scalar
    wrapped for tuple-of-``Node`` homogeneity). Goes through the same
    ``make_node`` validation as every other node -- no shortcut path."""

    return make_node(kind, fields=dict(fields))


def _ensure_node(value: FieldValue) -> Node:
    """Coerce an already-converted field value into a ``Node`` for use as
    a tuple element, wrapping a bare primitive in a ``"$scalar"`` marker
    so every sequence field satisfies the base schema's "tuple entries
    must be Node" rule."""

    if isinstance(value, Node):
        return value
    return _marker_node(_SCALAR_KIND, {"value": value})


def _convert_value(value: Any, spans: _SpanMap) -> FieldValue:
    """Convert one LibCST dataclass-field value into a common-model
    ``FieldValue``: ``None``/primitives pass through unchanged, a
    ``CSTNode`` recurses into :func:`_convert_cst_node`, an ``enum.Enum``
    member (LibCST's ``MaybeSentinel.DEFAULT``) becomes a ``"$sentinel"``
    marker, and a sequence becomes a tuple of ``Node`` (via
    :func:`_ensure_node` for any non-``Node`` element). Anything else is
    genuinely unrepresentable and raises loudly."""

    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, libcst.CSTNode):
        return _convert_cst_node(value, spans)
    if isinstance(value, enum.Enum):
        enum_cls = type(value)
        return _marker_node(
            _SENTINEL_KIND,
            {
                "enum_class": f"{enum_cls.__module__}.{enum_cls.__qualname__}",
                "member": value.name,
            },
        )
    if isinstance(value, (tuple, list)):
        return tuple(_ensure_node(_convert_value(item, spans)) for item in value)
    raise _contract_error(
        f"cannot represent LibCST field value of type {type(value).__name__} "
        "in the common model (not None, a primitive, a CSTNode, an Enum "
        "member, or a sequence of the above)"
    )


def _convert_cst_node(cst_node: "libcst.CSTNode", spans: _SpanMap) -> Node:
    """Convert one LibCST ``CSTNode`` into one common-model ``Node``,
    mapping every one of its own ``dataclasses.fields()`` entries by name
    (this is what makes trivia/whitespace/comment/blank-line nodes fall
    out for free: in LibCST they are just more ``CSTNode`` fields) and
    attaching the byte range resolved for it, if any."""

    kind = f"{_KIND_PREFIX}{type(cst_node).__name__}"
    fields: Dict[str, FieldValue] = {}
    children: List[Node] = []
    for cst_field in dataclasses.fields(cst_node):
        raw_value = getattr(cst_node, cst_field.name)
        converted = _convert_value(raw_value, spans)
        fields[cst_field.name] = converted
        if isinstance(converted, Node):
            children.append(converted)
        elif isinstance(converted, tuple):
            children.extend(converted)

    node = make_node(kind, fields=fields, children=tuple(children))
    span = spans.get(cst_node)
    if span is not None:
        node = dataclasses.replace(node, buffer_range=(span.start, span.start + span.length))
    return node


def _resolve_byte_spans(module: "libcst.Module") -> Tuple["libcst.Module", _SpanMap]:
    """Resolve byte-span metadata for ``module`` via LibCST's own
    ``ByteSpanPositionProvider``. Returns the (possibly internally copied)
    module actually carrying that metadata together with the resolved
    span map, so callers walk the matching object graph. Everything
    returned here is local, LibCST-internal, and never escapes this
    module's public functions."""

    wrapper = MetadataWrapper(module)
    spans = wrapper.resolve(ByteSpanPositionProvider)
    return wrapper.module, spans


def _import(external_representation: Any) -> Union[Node, Document]:
    if not isinstance(external_representation, libcst.CSTNode):
        raise _contract_error(
            "expected an already-parsed libcst.Module or libcst.CSTNode, "
            f"got {type(external_representation).__name__}"
        )

    if isinstance(external_representation, libcst.Module):
        module_for_walk, spans = _resolve_byte_spans(external_representation)
        root = _convert_cst_node(module_for_walk, spans)
        return Document(root=root, source_format_id=FORMAT_ID)

    # A bare fragment CSTNode: no document-level byte-span metadata to
    # resolve (no absolute buffer to range over), so buffer_range stays
    # the base schema's ordinary ``None`` default throughout.
    return _convert_cst_node(external_representation, {})


class PythonImportMap:
    """Import (LibCST -> common model) stage of the Python translator.

    Supplies the ``import_to_common`` stage that
    ``tree_engine.plugins.contract.FormatPluginContract`` requires
    ({p056}, {p057}); the export stage and the remaining contract surface
    (``metadata``, ``parse_document``, ``export_from_common``, ...) are
    delivered by sibling steps and composed with this class later.
    """

    def import_to_common(
        self,
        external_representation: Union["libcst.Module", "libcst.CSTNode"],
        options: Optional[Mapping[str, Any]] = None,
    ) -> Union[Node, Document]:
        """Translate an already-parsed LibCST ``Module``/``CSTNode`` into
        a common-model ``Document`` (for a ``Module``) or ``Node`` (for a
        fragment). ``options`` is accepted for contract-signature
        compatibility and currently unused by the import path itself.

        Raises :class:`~tree_engine.plugins.contract.FormatPluginContractError`
        for a value this module cannot represent, or when
        ``external_representation`` is not a LibCST ``CSTNode`` at all.
        No LibCST object is retained after this call returns.
        """

        return _import(external_representation)


def import_tree(
    external_tree: Union["libcst.Module", "libcst.CSTNode"],
    *,
    options: Optional[Mapping[str, Any]] = None,
) -> Union[Node, Document]:
    """Import side of the ``import_tree``/``export_tree`` bridge {p048}
    for externally supplied LibCST objects: reuses exactly the
    ``PythonImportMap.import_to_common`` path above, so an external
    caller's already-parsed ``libcst.Module``/``CSTNode`` is translated
    through the identical mapping, marker encoding, and byte-range
    resolution -- no second, divergent import path is introduced for the
    external-object case, per {p048}'s "not a separate source format"
    requirement.
    """

    return PythonImportMap().import_to_common(external_tree, options)
