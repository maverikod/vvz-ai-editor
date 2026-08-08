"""The Python format plugin object itself (concept C-014, atomic step A-003).

Scope: this module is the join point between the two already-merged pipeline
halves -- ``import_map.PythonImportMap`` (LibCST -> common model) and
``export_map.PythonExportMap`` (common model -> LibCST -> bytes/str) -- and
the two shared plugin interfaces: ``tree_engine.plugins.contract.FormatPluginContract``
and ``tree_engine.core.plugin_boundary.FormatBoundary``. It performs no
conversion of its own: every field/trivia/byte-range mapping stays exactly
where the merged halves put it; this file only wires entry points, parses
source into a temporary LibCST tree (via ``libcst.parse_module`` for a full
document, ``libcst.parse_statement``/``libcst.parse_expression`` for a
fragment) and hands that tree to ``PythonImportMap.import_to_common``, and
publishes the plugin's static identity and semantic-role surface.

Two ABCs, one class: ``FormatPluginContract`` and ``FormatBoundary`` each
declare an abstractmethod literally named ``parse_document`` (and, likewise,
``parse_fragment``) with different call conventions -- ``(source, options)``
positional for the contract, ``(source, *, source_format_id)`` for the core
boundary. ``PythonFormatPlugin`` below satisfies both with one concrete
method per name whose signature is a superset of both call conventions
(``options`` positional-or-omitted, ``source_format_id`` keyword-or-omitted);
Python's ABC machinery tracks abstractness by method *name*, so one concrete
override clears the abstractness of that name on every base that declared it.

LibCST exposure: the standard pipeline (``parse_document``, ``parse_fragment``,
``import_to_common``, ``import_external_tree``, ``export_from_common``,
``generate_output``, ``render_document``, ``render_fragment``) never returns
or accepts a live LibCST object -- only common-model ``Node``/``Document``,
primitives, or generated ``bytes``/``str``. ``import_tree``/``export_tree``
are the one deliberate, documented exception {p048}: they are the bridge for
a caller that already has (or wants back) a real ``libcst.Module``/``CSTNode``,
exactly as the merged ``import_map.import_tree``/``export_map.export_tree``
functions they delegate to already document and implement.

Semantic roles: ``semantic_role_mapping()`` publishes the context-free,
declarative kind -> role table (``FormatPluginContract``'s required shape:
one role per node-type string) for the three kinds that need no structural
context -- ``python:Module`` -> module, ``python:ClassDef`` -> class,
``python:FunctionDef`` -> function. A ``FunctionDef`` nested in a ``ClassDef``
is still, by LibCST's own shape, a ``python:FunctionDef`` node -- the same
kind string as a top-level function -- so no flat kind -> role dict can also
route it to "method" without contradicting itself on the very same key.
:meth:`PythonFormatPlugin.role_for` is the per-instance resolver the query
engine uses instead: given a node and its ancestor chain (nearest parent
first), it promotes a ``FunctionDef`` to method when the nearest enclosing
``ClassDef``/``FunctionDef`` ancestor is a ``ClassDef``.

Source-of-truth requirement labels honored here: {p048}, {p056}, {p057}, {p102}, {p103}.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

import libcst

from tree_engine.core.nodes import Document, Node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import (
    FormatPluginContract,
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRole,
    SemanticRoleMapping,
)
from tree_engine.plugins.detachable import PYTHON_PLUGIN_SPEC
from tree_engine.plugins.python import export_map as _export_map
from tree_engine.plugins.python import import_map as _import_map
from tree_engine.plugins.python.export_map import PythonExportMap
from tree_engine.plugins.python.import_map import FORMAT_ID, PythonImportMap

__all__ = [
    "FORMAT_ID",
    "PythonFormatPlugin",
    "PYTHON_FORMAT_PLUGIN",
]

_MODULE_KIND = f"{FORMAT_ID}:Module"
_CLASSDEF_KIND = f"{FORMAT_ID}:ClassDef"
_FUNCTIONDEF_KIND = f"{FORMAT_ID}:FunctionDef"

_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID,
    aliases=(),
    # From the detachable-plugin manifest, so the table the facade builds for this
    # plugin while it is UNIMPORTABLE and the metadata it declares once present can
    # never drift apart -- see plugins/detachable.py.
    file_extensions=PYTHON_PLUGIN_SPEC.file_extensions,
    plugin_version="1.0.0",
    contract_version="1.0.0",
    capabilities={
        "semantic_role_mapping": True,
        "import_tree": True,
        "export_tree": True,
        "byte_identical_round_trip": True,
    },
)

_ROLE_MAP = SemanticRoleMapping(
    {
        _MODULE_KIND: SemanticRole.MODULE,
        _CLASSDEF_KIND: SemanticRole.CLASS,
        _FUNCTIONDEF_KIND: SemanticRole.FUNCTION,
    }
)


def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, message=message)


def _parse_document_source(source: Union[str, bytes]) -> "libcst.Module":
    """Parse a full document via LibCST's module parser into a temporary
    tree. Raises :class:`FormatPluginContractError` carrying
    ``ErrorCode.FORMAT_CONTENT_PARSE_FAILED`` on a syntax error -- the
    catalog code the core boundary documents for this failure; no typed
    exception subclass for it exists yet ({p023}), so the generic
    contract-error carrier is used, exactly as it is designed to be.
    """

    if not isinstance(source, (str, bytes)):
        # A wrong argument type is the CALLER breaking the contract, not
        # damaged content: without this guard libcst leaks a bare TypeError,
        # which every sibling plugin classifies and this one did not.
        raise FormatPluginContractError(
            plugin_id=FORMAT_ID,
            error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
            message=f"source must be str or bytes, got {type(source).__name__}",
        )
    try:
        return libcst.parse_module(source)
    except libcst.ParserSyntaxError as exc:
        raise FormatPluginContractError(
            plugin_id=FORMAT_ID,
            error_code=ErrorCode.FORMAT_CONTENT_PARSE_FAILED,
            message=f"cannot parse Python document: {exc}",
        ) from exc


def _parse_fragment_source(source: Union[str, bytes]) -> Optional["libcst.CSTNode"]:
    """Parse a fragment via LibCST's expression parser, falling back to the
    statement parser, into a temporary tree. Returns ``None`` (never
    raises) when neither parser recognizes ``source`` as a structure, so
    the caller can apply the contract's documented plain-fallback-string
    behavior instead of treating "no structure" as an error.
    """

    text = source.decode("utf-8") if isinstance(source, bytes) else source
    # Expression first: an expression is also a valid expression-statement,
    # and the statement parser would wrap it in a SimpleStatementLine, adding
    # a newline the source never had and breaking the byte-identical fragment
    # round trip {p106} demands.
    try:
        return libcst.parse_expression(text)
    except libcst.ParserSyntaxError:
        pass
    try:
        return libcst.parse_statement(text)
    except libcst.ParserSyntaxError:
        return None


class PythonFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="python"`` plugin (concept C-014).

    Composes the already-merged :class:`PythonImportMap`/:class:`PythonExportMap`
    behind :class:`~tree_engine.plugins.contract.FormatPluginContract` and
    :class:`~tree_engine.core.plugin_boundary.FormatBoundary`; every field,
    trivia, and byte-range mapping is exactly what those two classes already
    produce/consume -- this class performs no conversion of its own.
    """

    def __init__(self) -> None:
        self._import_map = PythonImportMap()
        self._export_map = PythonExportMap()

    # -- FormatPluginContract -------------------------------------------------

    @property
    def metadata(self) -> FormatPluginMetadata:
        """This plugin's static identity/capability surface."""

        return _METADATA

    def parse_document(
        self,
        source: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Document:
        """Parse full source text/bytes into a common-model ``Document``.

        Input processing: ``source`` goes through ``libcst.parse_module``
        into a temporary ``libcst.Module``, handed directly to
        ``import_to_common`` -- no LibCST object survives this call.
        """

        module = _parse_document_source(source)
        result = self.import_to_common(module, options)
        if not isinstance(result, Document):
            raise _contract_error(
                f"parsing a full document must yield a Document, got {type(result).__name__}"
            )
        return result

    def import_external_tree(
        self, external_tree: Any, options: Optional[Mapping[str, Any]] = None
    ) -> Union[Node, Document]:
        """Translate an already-parsed external LibCST tree into common
        nodes, reusing :meth:`import_to_common` -- the single shared input
        translator ({p056}, {p057})."""

        return self.import_to_common(external_tree, options)

    def parse_fragment(
        self,
        fragment: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Union[Node, str]:
        """Parse a code fragment via LibCST's statement or expression
        parser into a temporary tree, then reuse ``import_to_common``.
        Returns the fragment's own text (never an external tree, never
        ``None``) when neither parser recognizes a structure.
        """

        cst_node = _parse_fragment_source(fragment)
        if cst_node is None:
            return fragment if isinstance(fragment, str) else fragment.decode("utf-8")
        result = self.import_to_common(cst_node, options)
        if not isinstance(result, Node):
            raise _contract_error(
                f"parsing a fragment must yield a Node, got {type(result).__name__}"
            )
        return result

    def import_to_common(
        self, external_representation: Any, options: Optional[Mapping[str, Any]] = None
    ) -> Union[Node, Document]:
        """The single input translator shared by ``parse_document``,
        ``import_external_tree``, and ``parse_fragment`` -- delegates
        entirely to the merged :class:`PythonImportMap`."""

        return self._import_map.import_to_common(external_representation, options)

    def export_from_common(
        self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> Union[bytes, str]:
        """Translate common-model nodes into final Python source output --
        delegates entirely to the merged :class:`PythonExportMap`, whose
        ``export_from_common`` already runs both the rebuild and LibCST's
        own code generation in one call ({p103})."""

        return self._export_map.export_from_common(nodes, options)

    def generate_output(
        self, target: Union[Node, Document, bytes, str], options: Optional[Mapping[str, Any]] = None
    ) -> Union[bytes, str]:
        """Produce final output for ``target``: runs ``export_from_common``
        when given common-model nodes, or passes an already-exported
        ``bytes``/``str`` representation through unchanged."""

        if isinstance(target, (Node, Document)):
            return self.export_from_common(target, options)
        if isinstance(target, (bytes, str)):
            return target
        raise _contract_error(
            f"cannot generate output for {type(target).__name__}; expected a "
            "Node, Document, bytes, or str"
        )

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """The declarative, context-free kind -> role table: module, class,
        and (top-level-shaped) function. See :meth:`role_for` for the
        context-sensitive method promotion this flat table cannot express.
        """

        return _ROLE_MAP

    # -- Context-sensitive semantic-role resolution ----------------------------

    def role_for(
        self, node: Node, ancestors: Sequence[Node] = ()
    ) -> Optional[SemanticRole]:
        """Resolve ``node``'s concrete semantic role for the query engine.

        ``ancestors`` is ``node``'s ancestor chain, nearest parent first (an
        empty sequence for a root/top-level node). A ``python:FunctionDef``
        is promoted from the declarative FUNCTION mapping to METHOD when the
        nearest ancestor that is itself a ``ClassDef`` or ``FunctionDef`` is
        a ``ClassDef`` -- i.e. it is nested directly inside a class body,
        not inside another function. ``python:Module``/``python:ClassDef``
        resolve unconditionally, mirroring :data:`_ROLE_MAP`. Any other kind
        returns ``None`` (this format has no role for it).
        """

        kind = str(node.kind)
        if kind == _MODULE_KIND:
            return SemanticRole.MODULE
        if kind == _CLASSDEF_KIND:
            return SemanticRole.CLASS
        if kind == _FUNCTIONDEF_KIND:
            for ancestor in ancestors:
                ancestor_kind = str(ancestor.kind)
                if ancestor_kind == _CLASSDEF_KIND:
                    return SemanticRole.METHOD
                if ancestor_kind == _FUNCTIONDEF_KIND:
                    return SemanticRole.FUNCTION
            return SemanticRole.FUNCTION
        return None

    # -- import_tree / export_tree external-LibCST bridge {p048} ---------------

    def import_tree(
        self,
        external_tree: Union["libcst.Module", "libcst.CSTNode"],
        *,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Union[Node, Document]:
        """Import side of the bridge: delegates to the merged
        ``import_map.import_tree`` for an externally supplied, already-parsed
        LibCST object -- no second, divergent import path."""

        return _import_map.import_tree(external_tree, options=options)

    def export_tree(
        self,
        common_tree: Union[Node, Document],
        *,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Export side of the bridge: delegates to the merged
        ``export_map.export_tree``, which deliberately hands back the
        rebuilt LibCST object itself -- the one documented exception to
        "no LibCST object crosses the boundary" ({p048})."""

        return _export_map.export_tree(common_tree, options=options)

    # -- FormatBoundary ---------------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        """CORE-facing counterpart of ``parse_document``: renders a full
        ``Document`` back to bytes via ``export_from_common``."""

        result = self.export_from_common(document, {})
        if not isinstance(result, bytes):
            raise _contract_error(
                f"render_document expected bytes, got {type(result).__name__}"
            )
        return result

    def render_fragment(self, node: Node) -> str:
        """CORE-facing counterpart of ``parse_fragment``: renders a single
        fragment ``Node`` back to source text via ``export_from_common``."""

        result = self.export_from_common(node, {})
        if not isinstance(result, str):
            raise _contract_error(
                f"render_fragment expected str, got {type(result).__name__}"
            )
        return result


# Registration data: a ready-made, stateless singleton a sibling registry
# step (out of scope here, per {p055}/{p059}/{p101}) can import and register
# under ``format_id="python"`` without needing to know how to construct one.
PYTHON_FORMAT_PLUGIN = PythonFormatPlugin()
