"""Tests for the CORE-side plugin boundary contract (concept C-002, {p045}).

Verifies that ``tree_engine.core.plugin_boundary.FormatBoundary`` actually
enforces the isolation invariant it documents: the abstract contract cannot
be instantiated, a conformant stub can, every method signature carries only
common-model types (``Node``/``Document``) or primitives (``bytes``/
``str``), and a stub that lets an external-library-shaped object cross the
boundary is detectable rather than silently accepted.

All stub plugins and stub "external tree" classes below are local,
throwaway stand-ins for a parser/codegen library's own node type; no real
parser/codegen library is imported here.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import get_type_hints

import pytest

from tree_engine.core.nodes import Document, Node, make_node, walk
from tree_engine.core.plugin_boundary import FormatBoundary, implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import FormatPluginContractError


class _StubExternalNodeA:
    """Stand-in for plugin A's own parser-library tree node type."""

    def __init__(self, tag: str, text: str = "", children=()) -> None:
        self.tag = tag
        self.text = text
        self.children = tuple(children)


class _StubExternalNodeB:
    """Stand-in for plugin B's own parser-library tree node type.

    Deliberately a distinct class from :class:`_StubExternalNodeA` so tests
    can confirm the two stub plugins never accept each other's external
    representation.
    """

    def __init__(self, tag: str, text: str = "", children=()) -> None:
        self.tag = tag
        self.text = text
        self.children = tuple(children)


def _make_conformant_plugin(format_id: str, external_cls: type):
    """Build a minimal, fully-conformant ``FormatBoundary`` implementation.

    All translation to/from ``external_cls`` happens strictly inside this
    plugin's own methods; nothing outside this factory ever sees the
    external type.
    """

    class _ConformantStubPlugin(FormatBoundary):
        def __init__(self) -> None:
            self.format_id = format_id
            self._external_cls = external_cls

        def _build_external_tree(self, source: str):
            tokens = source.split() or [""]
            return self._external_cls(
                tag="root",
                children=[self._external_cls(tag="token", text=tok) for tok in tokens],
            )

        def _external_to_node(self, ext) -> Node:
            if not isinstance(ext, self._external_cls):
                raise TypeError(
                    f"{self.format_id}: expected {self._external_cls.__name__}, "
                    f"got {type(ext).__name__}"
                )
            return make_node(
                f"{self.format_id}:{ext.tag}",
                fields={"text": ext.text},
                children=tuple(self._external_to_node(c) for c in ext.children),
            )

        def _node_to_external(self, node: Node):
            if not isinstance(node, Node):
                raise TypeError(f"{self.format_id}: expected Node, got {type(node).__name__}")
            return self._external_cls(
                tag=str(node.kind),
                text=str(node.fields.get("text", "")),
                children=tuple(self._node_to_external(c) for c in node.children),
            )

        def _render_external(self, ext) -> str:
            parts = [ext.text] if ext.text else []
            parts.extend(self._render_external(c) for c in ext.children)
            return " ".join(p for p in parts if p)

        def parse_document(self, source: bytes, *, source_format_id: str) -> Document:
            ext = self._build_external_tree(source.decode("utf-8"))
            return Document(root=self._external_to_node(ext), source_format_id=source_format_id)

        def parse_fragment(self, source: str, *, source_format_id: str) -> Node:
            return self._external_to_node(self._build_external_tree(source))

        def render_document(self, document: Document) -> bytes:
            return self._render_external(self._node_to_external(document.root)).encode("utf-8")

        def render_fragment(self, node: Node) -> str:
            return self._render_external(self._node_to_external(node))

    return _ConformantStubPlugin()


class _LeakyStubPlugin(FormatBoundary):
    """Conformant in shape only: ``parse_fragment`` lets an external type escape."""

    format_id = "stub-leaky"

    def parse_document(self, source: bytes, *, source_format_id: str) -> Document:
        raise NotImplementedError

    def parse_fragment(self, source: str, *, source_format_id: str) -> Node:
        # Bug under test: returns the raw external-tree-shaped object
        # instead of translating it into a common-model Node.
        return _StubExternalNodeA(tag="leak", text=source)

    def render_document(self, document: Document) -> bytes:
        raise NotImplementedError

    def render_fragment(self, node: Node) -> str:
        raise NotImplementedError


def _assert_boundary_result_is_common_model(value, *, plugin_id: str, expected_type: type):
    """Caller-side boundary guard: reject a result of a non-common-model type.

    Mirrors the module's own documented division of responsibility: runtime
    detection of an external object crossing the boundary is "a concern for
    the plugin's own defensive checks and for the caller that invokes it"
    (``plugin_boundary`` module docstring), signaled via
    ``ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR``.
    """

    if not isinstance(value, expected_type):
        raise FormatPluginContractError(
            plugin_id=plugin_id,
            error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
            message=f"{plugin_id}: expected {expected_type.__name__}, got {type(value).__name__}",
        )
    return value


@pytest.fixture
def conformant_plugin():
    return _make_conformant_plugin("stub-a", _StubExternalNodeA)


@pytest.fixture
def plugin_pair():
    plugin_a = _make_conformant_plugin("stub-a", _StubExternalNodeA)
    plugin_b = _make_conformant_plugin("stub-b", _StubExternalNodeB)
    return plugin_a, plugin_b


def test_stub_plugin_translates_to_common_model(conformant_plugin) -> None:
    assert isinstance(conformant_plugin, FormatBoundary)
    assert implements_format_boundary(conformant_plugin)

    node = conformant_plugin.parse_fragment("alpha beta gamma", source_format_id="stub-a")

    visited = list(walk(node))
    assert visited, "expected at least one node from a non-empty fragment"
    assert all(isinstance(n, Node) for n in visited)
    assert not any(isinstance(n, _StubExternalNodeA) for n in visited)


def test_stub_plugin_translates_from_common_model(conformant_plugin) -> None:
    node = make_node(
        "stub-a:token",
        fields={"text": "hello"},
        children=(make_node("stub-a:token", fields={"text": "world"}),),
    )

    external = conformant_plugin._node_to_external(node)
    stack = [external]
    seen_external = []
    while stack:
        current = stack.pop()
        seen_external.append(current)
        stack.extend(current.children)

    assert all(isinstance(e, _StubExternalNodeA) for e in seen_external)
    assert not any(isinstance(e, Node) for e in seen_external)

    rendered = conformant_plugin.render_fragment(node)
    assert isinstance(rendered, str)
    assert rendered.split() == ["hello", "world"]


def test_boundary_rejects_missing_translation_method() -> None:
    with pytest.raises(TypeError):
        FormatBoundary()  # the abstract contract itself is never instantiable

    class _IncompletePlugin(FormatBoundary):
        def parse_document(self, source: bytes, *, source_format_id: str) -> Document:
            raise NotImplementedError

        def parse_fragment(self, source: str, *, source_format_id: str) -> Node:
            raise NotImplementedError

        def render_document(self, document: Document) -> bytes:
            raise NotImplementedError

        # render_fragment intentionally omitted.

    with pytest.raises(TypeError):
        _IncompletePlugin()  # missing abstract method: never becomes usable

    for method_name in (
        "parse_document",
        "parse_fragment",
        "render_document",
        "render_fragment",
    ):
        hints = get_type_hints(getattr(FormatBoundary, method_name))
        allowed = {bytes, str, Node, Document}
        assert set(hints.values()) <= allowed, (
            f"{method_name} signature carries a type outside "
            f"{sorted(t.__name__ for t in allowed)}: {hints}"
        )


def test_boundary_rejects_external_type_crossing() -> None:
    plugin = _LeakyStubPlugin()
    assert implements_format_boundary(plugin)

    leaked = plugin.parse_fragment("x", source_format_id=plugin.format_id)
    assert isinstance(leaked, _StubExternalNodeA)  # confirms the bug is real, not hypothetical

    with pytest.raises(FormatPluginContractError) as excinfo:
        _assert_boundary_result_is_common_model(
            leaked, plugin_id=plugin.format_id, expected_type=Node
        )
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert excinfo.value.plugin_id == plugin.format_id


def test_core_side_never_receives_external_type(conformant_plugin) -> None:
    source = "one two three"

    node = conformant_plugin.parse_fragment(source, source_format_id="stub-a")
    core_side_objects = list(walk(node))
    assert all(isinstance(obj, Node) for obj in core_side_objects)
    assert not any(isinstance(obj, _StubExternalNodeA) for obj in core_side_objects)

    rendered = conformant_plugin.render_fragment(node)
    assert isinstance(rendered, str)
    assert rendered.split() == source.split()

    document = conformant_plugin.parse_document(source.encode("utf-8"), source_format_id="stub-a")
    assert isinstance(document, Document)
    doc_side_objects = list(walk(document.root))
    assert all(isinstance(obj, Node) for obj in doc_side_objects)
    assert not any(isinstance(obj, _StubExternalNodeA) for obj in doc_side_objects)

    rendered_bytes = conformant_plugin.render_document(document)
    assert isinstance(rendered_bytes, bytes)
    assert rendered_bytes.decode("utf-8").split() == source.split()


def test_two_independent_stub_plugins_do_not_leak_types_across_boundary(plugin_pair) -> None:
    plugin_a, plugin_b = plugin_pair

    ext_a = plugin_a._build_external_tree("hello")
    ext_b = plugin_b._build_external_tree("world")
    assert isinstance(ext_a, _StubExternalNodeA)
    assert isinstance(ext_b, _StubExternalNodeB)

    # Each plugin handles its own external type without incident.
    node_from_a = plugin_a._external_to_node(ext_a)
    node_from_b = plugin_b._external_to_node(ext_b)
    assert isinstance(node_from_a, Node)
    assert isinstance(node_from_b, Node)

    # Neither plugin accepts the other's external type.
    with pytest.raises(TypeError):
        plugin_b._external_to_node(ext_a)
    with pytest.raises(TypeError):
        plugin_a._external_to_node(ext_b)
