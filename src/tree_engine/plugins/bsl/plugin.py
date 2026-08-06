"""The BSL format plugin object itself (concept C-015, atomic step A-004).

Scope: this module is the join point between the two already-merged pipeline
halves -- ``import_map.BSLImportMap`` (tree-sitter-bsl -> common model) and
``generator.BSLGenerator`` (common model -> ``BSLGenerationTree`` -> bytes)
-- and the two shared plugin interfaces:
``tree_engine.plugins.contract.FormatPluginContract`` and
``tree_engine.core.plugin_boundary.FormatBoundary``. It performs no mapping
or rendering of its own: every field/byte-range/dialect decision stays
exactly where the merged halves put it; this file only wires entry points --
runs source bytes through the pinned tree-sitter-bsl 0.1.6 backend into a
temporary parse tree and hands the tree's root node to
``BSLImportMap.import_to_common`` -- and publishes the plugin's static
identity and semantic-role surface ({p046}, {p056}).

Parser lifetime gotcha: a fresh ``tree_sitter.Parser`` is constructed for
every single parse (:func:`_parse_bytes`). Reusing one ``Parser`` instance
across multiple ``parse()`` calls has been observed, in this environment
(tree-sitter 0.25.x + tree_sitter_bsl 0.1.6), to silently corrupt byte
offsets on the second and later parses -- a real, reproduced gotcha, not a
theoretical one. Never cache or share a ``Parser`` across calls in this
module.

Failure classification ({p104}): ``import_to_common`` already contains the
one ``has_error`` check this translator needs -- tree-sitter propagates
``has_error`` up through every ancestor of any ``ERROR``/``MISSING``
descendant, so a single check on the tree's root (or, for a fragment, on the
node handed in with ``fragment=True``) is sufficient, and is exactly what
:mod:`tree_engine.plugins.bsl.import_map` already implements. This module
does not duplicate that check: :meth:`BSLFormatPlugin.parse_document` calls
``import_to_common`` with ``fragment=False`` (raising
``FORMAT_CONTENT_PARSE_FAILED`` on a damaged tree) and
:meth:`BSLFormatPlugin.parse_fragment` calls it with ``fragment=True``
(raising ``FORMAT_FRAGMENT_PARSE_FAILED`` instead) -- the single point of
truth for that decision stays in the import map, per {p104}. Raising either
error, rather than returning a partial tree, is what lets a caller apply the
permitted plain-text fallback when a document fails to open cleanly; that
fallback itself is a later stage's concern, not implemented here.

Two ABCs, one class: exactly as ``PythonFormatPlugin`` already does for the
Python translator, ``FormatPluginContract`` and ``FormatBoundary`` each
declare an abstractmethod literally named ``parse_document`` (and,
likewise, ``parse_fragment``) with different call conventions --
``(source, options)`` positional for the contract, ``(source, *,
source_format_id)`` for the core boundary. ``BSLFormatPlugin`` below
satisfies both with one concrete method per name whose signature is a
superset of both call conventions; Python's ABC machinery tracks
abstractness by method *name*, so one concrete override clears the
abstractness of that name on every base that declared it.

tree-sitter exposure: no ``tree_sitter``/``tree_sitter_bsl`` type appears in
any method signature in this file (only inside method bodies), and the
standard pipeline (``parse_document``, ``parse_fragment``,
``import_to_common``, ``export_from_common``, ``generate_output``,
``render_document``, ``render_fragment``) never returns or accepts a live
tree-sitter object -- only common-model ``Node``/``Document`` or
``bytes``/``str``, matching ``core/plugin_boundary.py``'s isolation
invariant ({p045}, {p046}).

Semantic roles: :func:`bsl_semantic_role_map` publishes the declarative,
context-free kind -> role table for the plugin-contract's
semantic-role-mapping capability: ``bsl:procedure_definition`` and
``bsl:function_definition`` (the generic-node kinds
``import_map._convert_generic`` already produces for these tree-sitter-bsl
node types, since neither gets construct-specific treatment) both map to
the ``function`` role, and ``bsl:source_file`` (the root node's own generic
kind) maps to ``module``. BSL has no method or class construct, so neither
role gets an entry; per ``SemanticRoleMapping.roles_for``'s own documented
behavior this is observed as an empty tuple, never an error.

Source-of-truth requirement labels honored here: {p046}, {p047}, {p104}.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from tree_engine.core.nodes import Document, Node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl.generator import BSLGenerationTree, BSLGenerator
from tree_engine.plugins.bsl.import_map import FORMAT_ID, BSLImportMap
from tree_engine.plugins.contract import (
    FormatPluginContract,
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRole,
    SemanticRoleMapping,
)

__all__ = [
    "FORMAT_ID",
    "BSLFormatPlugin",
    "BSL_FORMAT_PLUGIN",
    "bsl_semantic_role_map",
]

_MODULE_KIND = f"{FORMAT_ID}:source_file"
_PROCEDURE_KIND = f"{FORMAT_ID}:procedure_definition"
_FUNCTION_KIND = f"{FORMAT_ID}:function_definition"

_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID,
    aliases=(),
    file_extensions=("bsl",),
    plugin_version="1.0.0",
    contract_version="1.0.0",
    capabilities={
        "semantic_role_mapping": True,
        "byte_identical_round_trip": True,
    },
)


def bsl_semantic_role_map() -> SemanticRoleMapping:
    """The BSL plugin's declarative kind -> role table: procedures and
    functions map to the function role, the module (root ``source_file``)
    node maps to the module role, and the method and class roles -- which
    do not apply to BSL -- get no entry, so ``roles_for`` yields an empty
    result for them rather than raising."""

    return SemanticRoleMapping(
        {
            _PROCEDURE_KIND: SemanticRole.FUNCTION,
            _FUNCTION_KIND: SemanticRole.FUNCTION,
            _MODULE_KIND: SemanticRole.MODULE,
        }
    )


_ROLE_MAP = bsl_semantic_role_map()


def _contract_error(
    message: str, *, code: ErrorCode = ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, error_code=code, message=message)


def _coerce_source_bytes(source: Union[str, bytes]) -> bytes:
    """Normalize ``source`` to the ``bytes`` a tree-sitter ``Parser``
    requires, encoding a ``str`` as UTF-8."""

    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return source.encode("utf-8")
    raise _contract_error(
        f"BSL source must be str or bytes, got {type(source).__name__}"
    )


def _parse_bytes(source_bytes: bytes) -> Any:
    """Parse ``source_bytes`` with the pinned tree-sitter-bsl 0.1.6 backend
    into a temporary parse tree and return its root node.

    A brand-new ``Parser`` (and ``Language``) is built for this one call and
    discarded immediately after -- never cached, never reused across calls.
    Reusing a single ``Parser`` instance across parses has been observed, in
    this environment, to silently corrupt byte offsets on later parses; a
    fresh instance per parse is the only safe pattern here ({p046}).
    """

    import tree_sitter_bsl
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_bsl.language()))
    tree = parser.parse(source_bytes)
    return tree.root_node


class BSLFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="bsl"`` plugin (concept C-015).

    Composes the already-merged :class:`BSLImportMap`/:class:`BSLGenerator`
    behind :class:`~tree_engine.plugins.contract.FormatPluginContract` and
    :class:`~tree_engine.core.plugin_boundary.FormatBoundary`; every
    mapping/rendering decision is exactly what those two classes already
    make -- this class performs none of its own beyond running the pinned
    tree-sitter-bsl parser and dispatching to them.
    """

    def __init__(self) -> None:
        self._import_map = BSLImportMap()
        self._generator = BSLGenerator()

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
        """Parse full BSL source text/bytes into a common-model ``Document``.

        Input processing: ``source`` goes through the pinned tree-sitter-bsl
        backend into a temporary parse tree, whose root node is handed
        directly to ``import_to_common`` with ``fragment=False`` -- no
        tree-sitter object survives this call. A damaged tree (any
        ``ERROR``/``MISSING`` node) surfaces as
        ``FormatPluginContractError(error_code=FORMAT_CONTENT_PARSE_FAILED)``,
        raised by the import map itself ({p104}); a partial tree is never
        returned.
        """

        source_bytes = _coerce_source_bytes(source)
        root = _parse_bytes(source_bytes)
        result = self.import_to_common(root, options, fragment=False)
        if not isinstance(result, Node):
            raise _contract_error(
                f"parsing a full BSL document must yield a Node, got {type(result).__name__}"
            )
        return Document(root=result, source_format_id=FORMAT_ID)

    def import_external_tree(
        self, external_tree: Any, options: Optional[Mapping[str, Any]] = None
    ) -> Union[Node, Document]:
        """Translate an already-parsed external tree-sitter-bsl tree into
        common nodes, reusing :meth:`import_to_common` -- the single shared
        input translator ({p056}, {p057})."""

        return self.import_to_common(external_tree, options, fragment=False)

    def parse_fragment(
        self,
        fragment: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Node:
        """Parse a local BSL fragment through the same pinned tree-sitter-bsl
        backend and reuse ``import_to_common``, this time with
        ``fragment=True`` so a damaged tree is classified as
        ``FORMAT_FRAGMENT_PARSE_FAILED`` rather than
        ``FORMAT_CONTENT_PARSE_FAILED`` ({p104}). tree-sitter-bsl has no
        separate statement/expression entry point the way LibCST does, so a
        fragment is parsed exactly like a document and only the error-code
        classification differs; a valid fragment always yields a ``Node``,
        never the plain-fallback-string case the contract otherwise permits.
        """

        source_bytes = _coerce_source_bytes(fragment)
        root = _parse_bytes(source_bytes)
        result = self.import_to_common(root, options, fragment=True)
        if not isinstance(result, Node):
            raise _contract_error(
                f"parsing a BSL fragment must yield a Node, got {type(result).__name__}"
            )
        return result

    def import_to_common(
        self,
        external_representation: Any,
        options: Optional[Mapping[str, Any]] = None,
        *,
        fragment: bool = False,
    ) -> Node:
        """The single input translator shared by ``parse_document``,
        ``import_external_tree``, and ``parse_fragment`` -- delegates
        entirely to the merged :class:`BSLImportMap`, including its own
        ``has_error`` -> ``FORMAT_CONTENT_PARSE_FAILED``/
        ``FORMAT_FRAGMENT_PARSE_FAILED`` classification ({p104}). The extra
        keyword-only ``fragment`` flag is this plugin's own pass-through of
        that same parameter on ``BSLImportMap.import_to_common``; the
        abstract ``FormatPluginContract.import_to_common`` this satisfies by
        name does not itself declare it, exactly as ``parse_document`` above
        adds ``source_format_id`` beyond its abstract signature."""

        return self._import_map.import_to_common(
            external_representation, options, fragment=fragment
        )

    def export_from_common(
        self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> BSLGenerationTree:
        """Translate common-model nodes into this plugin's own
        generation-ready representation -- delegates entirely to the merged
        :class:`BSLGenerator` ({p105})."""

        return self._generator.export_from_common(nodes, options)

    def generate_output(
        self,
        target: Union[Node, Document, BSLGenerationTree],
        options: Optional[Mapping[str, Any]] = None,
    ) -> bytes:
        """Produce final BSL output bytes for ``target`` -- delegates
        entirely to the merged :class:`BSLGenerator`, whose
        ``generate_output`` already runs ``export_from_common`` internally
        when given a bare ``Node``/``Document`` ({p105})."""

        return self._generator.generate_output(target, options)

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """The declarative, context-free kind -> role table: procedures and
        functions map to function, the module node maps to module; method
        and class have no BSL construct and so yield no entry. See
        :func:`bsl_semantic_role_map`, the module-level function this
        delegates to."""

        return _ROLE_MAP

    # -- FormatBoundary ---------------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        """CORE-facing counterpart of ``parse_document``: renders a full
        ``Document`` back to BSL bytes via ``generate_output``."""

        result = self.generate_output(document, {})
        if not isinstance(result, bytes):
            raise _contract_error(
                f"render_document expected bytes, got {type(result).__name__}"
            )
        return result

    def render_fragment(self, node: Node) -> str:
        """CORE-facing counterpart of ``parse_fragment``: renders a single
        fragment ``Node`` back to BSL source text via ``generate_output``,
        decoding the generator's bytes as UTF-8."""

        result = self.generate_output(node, {})
        if not isinstance(result, bytes):
            raise _contract_error(
                f"render_fragment expected bytes, got {type(result).__name__}"
            )
        return result.decode("utf-8")


# Registration data: a ready-made, stateless singleton a sibling registry
# step (out of scope here, per {p055}/{p059}/{p101}) can import and register
# under ``format_id="bsl"`` without needing to know how to construct one.
BSL_FORMAT_PLUGIN = BSLFormatPlugin()
