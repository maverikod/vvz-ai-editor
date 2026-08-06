"""Contract-conformance tests for the format-plugin interface (concept C-010,
step G-020/T-001/A-003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.contract.FormatPluginContract`` and
``tree_engine.core.plugin_boundary.FormatBoundary`` through a minimal,
self-contained ``FakePlugin`` -- no registry, no entry-point discovery, no
concrete Python/BSL plugin; registry uniqueness/replace and extension
selection are sibling steps' concern, deliberately untouched here.

Covered: (1) metadata surface completeness; (2) import stage isolation --
``parse_document``/``import_external_tree`` return only common-model nodes,
never the fake external-tree type, checked recursively through ``children``
and every ``fields`` value; (3) ``parse_fragment`` reuse of the same
``import_to_common`` translator ``parse_document`` uses, with the plain-text
sentinel (never ``None``, never an external tree) for an unrecognized
fragment; (4) ``export_from_common``/``generate_output`` as distinct,
independently and jointly testable stages; (5) ``UnsupportedTranslationError``
carrying both ``node_type`` and ``format_id``; (6) semantic-role mapping
returning declared kinds for modeled roles and ``()`` for unmodeled ones.

A second group exercises ``plugin_boundary`` directly: a plugin implementing
both ABCs structurally satisfies ``implements_format_boundary``, while a
``FormatBoundary`` subclass missing one method is rejected by both plain
``abc`` instantiation and the helper -- inheritance alone is not conformance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple, Union

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.core.plugin_boundary import FormatBoundary, implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import (
    FormatPluginContract,
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRole,
    SemanticRoleMapping,
    UnsupportedTranslationError,
)

_FORMAT_ID = "fake"
_MODULE_KIND = "fake:module"
_FUNCTION_KIND = "fake:function"
_UNSUPPORTED_TOKEN = "unsupported"
_RECOGNIZED_FRAGMENT_KINDS = {"function"}


# -- A fake "external library" tree, standing in for a real parser's own
# AST/CST object; never a common-model type -- exactly what the contract
# forbids from ever reaching a caller.


@dataclass(frozen=True)
class ExternalNode:
    """A fake external parser-library node. Must never leak past the
    contract boundary into a caller-visible common-model result."""

    kind: str
    text: str
    children: Tuple["ExternalNode", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BackendTree:
    """FakePlugin's own backend representation: the ``export_from_common``
    return type, consumed only by this same plugin's ``generate_output``."""

    text: str


def _assert_no_external_leakage(value: Any) -> None:
    """Recursively assert no :class:`ExternalNode` anywhere in ``value`` --
    ``children``, any ``fields`` entry, or nested arbitrarily deep."""

    assert not isinstance(value, ExternalNode), f"external tree object leaked into result: {value!r}"
    if isinstance(value, Node):
        for field_value in value.fields.values():
            _assert_no_external_leakage(field_value)
        for child in value.children:
            _assert_no_external_leakage(child)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _assert_no_external_leakage(item)


# -- FakePlugin: a minimal, self-contained implementation of both ABCs


class FakePlugin(FormatPluginContract, FormatBoundary):
    """Minimal fake format plugin exercising the entire contract surface.

    ``parse_document`` accepts a tiny DSL: a comma-separated list of child
    node kinds (e.g. ``"function,function"``), wrapped in one ``"module"``
    root. ``parse_fragment`` recognizes a lone ``"function"`` token as a
    structure and falls back to the plain-string sentinel otherwise.
    """

    def __init__(self) -> None:
        self._metadata = FormatPluginMetadata(
            format_id=_FORMAT_ID,
            aliases=("fk",),
            file_extensions=("fake",),
            plugin_version="0.1.0",
            contract_version="1.0.0",
            capabilities={"semantic_role_mapping": True},
        )
        self._role_map = SemanticRoleMapping(
            {_MODULE_KIND: SemanticRole.MODULE, _FUNCTION_KIND: SemanticRole.FUNCTION}
        )

    # -- FormatPluginContract ------------------------------------------------

    @property
    def metadata(self) -> FormatPluginMetadata:
        return self._metadata

    def parse_document(
        self,
        source: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Document:
        text = source.decode("utf-8") if isinstance(source, bytes) else source
        external = self._tokenize(text)
        root = self.import_to_common(external, options)
        if not isinstance(root, Node):
            raise FormatPluginContractError(
                plugin_id=_FORMAT_ID,
                message=f"parsing a document must yield a Node, got {type(root).__name__}",
            )
        return Document(root=root, source_format_id=_FORMAT_ID)

    def import_external_tree(
        self, external_tree: Any, options: Optional[Mapping[str, Any]] = None
    ) -> Node:
        return self.import_to_common(external_tree, options)

    def parse_fragment(
        self,
        fragment: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Union[Node, str]:
        text = fragment.decode("utf-8") if isinstance(fragment, bytes) else fragment
        token = text.strip()
        if token not in _RECOGNIZED_FRAGMENT_KINDS:
            return text
        external = ExternalNode(kind=token, text=token)
        return self.import_to_common(external, options)

    def import_to_common(
        self, external_representation: ExternalNode, options: Optional[Mapping[str, Any]] = None
    ) -> Node:
        if external_representation.kind == _UNSUPPORTED_TOKEN:
            raise UnsupportedTranslationError(
                node_type=external_representation.kind, format_id=_FORMAT_ID
            )
        kind = f"{_FORMAT_ID}:{external_representation.kind}"
        children = tuple(self.import_to_common(child, options) for child in external_representation.children)
        return make_node(kind, fields={"content": external_representation.text}, children=children)

    def export_from_common(
        self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> BackendTree:
        root = nodes.root if isinstance(nodes, Document) else nodes
        return BackendTree(text=self._render(root))

    def generate_output(
        self, target: Union[Node, Document, BackendTree], options: Optional[Mapping[str, Any]] = None
    ) -> str:
        if isinstance(target, BackendTree):
            return f"OUT:{target.text}"
        if isinstance(target, (Node, Document)):
            return self.generate_output(self.export_from_common(target, options), options)
        raise FormatPluginContractError(
            plugin_id=_FORMAT_ID,
            message=f"cannot generate output for {type(target).__name__}",
        )

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        return self._role_map

    # -- FormatBoundary --------------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        result = self.generate_output(document, {})
        return result.encode("utf-8")

    def render_fragment(self, node: Node) -> str:
        return self.generate_output(node, {})

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _tokenize(source: str) -> ExternalNode:
        tokens = [t.strip() for t in source.split(",") if t.strip()]
        children = tuple(ExternalNode(kind=t, text=t) for t in tokens)
        return ExternalNode(kind="module", text=source, children=children)

    def _render(self, node: Node) -> str:
        if not node.children:
            return str(node.fields.get("content", ""))
        return "(" + ",".join(self._render(child) for child in node.children) + ")"


# -- 1. Metadata surface completeness


def test_metadata_completeness() -> None:
    plugin = FakePlugin()
    metadata = plugin.metadata

    assert isinstance(metadata, FormatPluginMetadata)
    assert metadata.format_id == "fake"
    assert metadata.aliases == ("fk",)
    assert metadata.file_extensions == ("fake",)
    assert metadata.plugin_version == "0.1.0"
    assert metadata.contract_version == "1.0.0"
    assert metadata.capabilities.get("semantic_role_mapping") is True
    # The capability entry is declarative; the live mapping is still the
    # method call's own responsibility to actually provide.
    assert isinstance(plugin.semantic_role_mapping(), SemanticRoleMapping)


# -- 2. Import stage isolation


def test_import_stage_isolation() -> None:
    plugin = FakePlugin()

    document = plugin.parse_document("function,function")
    assert isinstance(document, Document)
    for node in walk(document.root):
        assert isinstance(node, Node)
    _assert_no_external_leakage(document.root)

    # import_external_tree on an explicitly nested external tree, several
    # levels deep, must also isolate every level -- not just the top one.
    nested = ExternalNode(
        kind="module",
        text="module",
        children=(
            ExternalNode(
                kind="function", text="function", children=(ExternalNode(kind="function", text="function"),)
            ),
        ),
    )
    result = plugin.import_external_tree(nested)
    assert isinstance(result, Node)
    _assert_no_external_leakage(result)


# -- 3. Parse fragment reuse


def test_parse_fragment_reuse() -> None:
    plugin = FakePlugin()

    recognized = plugin.parse_fragment("function")
    direct = plugin.import_to_common(ExternalNode(kind="function", text="function"))
    assert isinstance(recognized, Node)
    # Structural equality with a direct import_to_common call demonstrates
    # parse_fragment routes through the same translator, not a parallel one.
    assert recognized == direct
    _assert_no_external_leakage(recognized)

    unrecognized = plugin.parse_fragment("not_a_known_kind")
    assert unrecognized == "not_a_known_kind"
    assert isinstance(unrecognized, str)
    assert not isinstance(unrecognized, Node)

    # bytes input (the FormatBoundary call convention) reuses the identical path.
    from_bytes = plugin.parse_fragment(b"function")
    assert from_bytes == direct


# -- 4. Bidirectional stage traceability


def test_export_generate_traceability() -> None:
    plugin = FakePlugin()
    document = plugin.parse_document("function,function")

    exported = plugin.export_from_common(document)
    assert isinstance(exported, BackendTree)
    assert exported.text == "(function,function)"

    staged_output = plugin.generate_output(exported)
    combined_output = plugin.generate_output(document)

    assert staged_output == "OUT:(function,function)"
    assert staged_output == combined_output
    # Each stage is independently testable and yields its own distinct type.
    assert isinstance(exported, BackendTree)
    assert isinstance(staged_output, str)


# -- 5. Error handling


def test_unsupported_translation_error() -> None:
    plugin = FakePlugin()

    with pytest.raises(UnsupportedTranslationError) as excinfo:
        plugin.import_to_common(ExternalNode(kind=_UNSUPPORTED_TOKEN, text=_UNSUPPORTED_TOKEN))
    assert excinfo.value.node_type == _UNSUPPORTED_TOKEN
    assert excinfo.value.format_id == _FORMAT_ID
    assert excinfo.value.error_code == ErrorCode.UNSUPPORTED_TRANSLATION
    assert _UNSUPPORTED_TOKEN in str(excinfo.value)
    assert _FORMAT_ID in str(excinfo.value)

    # The same error surfaces, with the same identifying fields, when the
    # unsupported construct is nested inside an otherwise-valid document --
    # never silently dropped.
    with pytest.raises(UnsupportedTranslationError) as nested_excinfo:
        plugin.parse_document("function,unsupported")
    assert nested_excinfo.value.node_type == _UNSUPPORTED_TOKEN
    assert nested_excinfo.value.format_id == _FORMAT_ID


# -- 6. Semantic-role mapping


def test_semantic_role_mapping() -> None:
    plugin = FakePlugin()
    mapping = plugin.semantic_role_mapping()

    assert isinstance(mapping, SemanticRoleMapping)
    assert mapping.roles_for(SemanticRole.FUNCTION) == (_FUNCTION_KIND,)
    assert mapping.roles_for(SemanticRole.MODULE) == (_MODULE_KIND,)
    # Inapplicable roles yield the empty tuple, never an error.
    assert mapping.roles_for(SemanticRole.METHOD) == ()
    assert mapping.roles_for(SemanticRole.CLASS) == ()
    assert set(mapping.node_type_to_role) == {_FUNCTION_KIND, _MODULE_KIND}


# -- FormatBoundary conformance: complete satisfies it, incomplete is rejected --


def test_conformant_plugin_satisfies_contract_and_boundary() -> None:
    plugin = FakePlugin()

    assert isinstance(plugin, FormatPluginContract)
    assert isinstance(plugin, FormatBoundary)
    assert implements_format_boundary(FakePlugin) is True
    assert implements_format_boundary(plugin) is True

    document = plugin.parse_document("function")
    rendered_document = plugin.render_document(document)
    assert isinstance(rendered_document, bytes)

    fragment_node = plugin.parse_fragment("function")
    rendered_fragment = plugin.render_fragment(fragment_node)
    assert isinstance(rendered_fragment, str)


def test_incomplete_plugin_is_rejected() -> None:
    """A ``FormatBoundary`` subclass missing ``render_fragment`` is not
    conformant despite inheriting the ABC: plain ``abc`` refuses to
    instantiate it, and ``implements_format_boundary`` independently
    rejects the class -- "methods actually implemented, not merely
    inherited"."""

    class IncompleteBoundaryPlugin(FormatBoundary):
        def parse_document(self, source: bytes, *, source_format_id: str) -> Document:
            raise NotImplementedError

        def parse_fragment(self, source: str, *, source_format_id: str) -> Node:
            raise NotImplementedError

        def render_document(self, document: Document) -> bytes:
            raise NotImplementedError

        # render_fragment deliberately left unimplemented.

    assert implements_format_boundary(IncompleteBoundaryPlugin) is False
    with pytest.raises(TypeError):
        IncompleteBoundaryPlugin()  # type: ignore[abstract]
