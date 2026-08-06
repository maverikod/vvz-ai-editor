"""Contract tests for the ported tree-query traversal adapter.

Covers concept C-009, atomic step G-018/T-001/A-005:
``tree_engine.query.adapter`` (``TreeTraversalAdapter``,
``iter_matching_nodes``, ``resolve_semantic_role``). Every fixture tree and
every fake format plugin used below is declared inline in this file; nothing
is imported from a sibling test module or from ``ai_editor``.

Out of scope, per the atomic step's own prompt: predicate evaluation and
full query orchestration (both covered by sibling test files under this
same tactical step).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, Optional, Sequence, Tuple

import pytest

from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.query.adapter import TreeTraversalAdapter, resolve_semantic_role


# ---------------------------------------------------------------------------
# Fixture support: a monotonic node_id/short_id allocator and a minimal,
# duck-typed fake format plugin. Both are private to this file.
# ---------------------------------------------------------------------------


class _IdAllocator:
    """Assigns a fresh UUID4 ``node_id`` and a monotonic int ``short_id``.

    A new instance is used per test so ``short_id`` values (and therefore
    ``short_id_hex`` assertions) are predictable and independent of test
    execution order.
    """

    def __init__(self) -> None:
        self._next_short_id = 1

    def __call__(self) -> Tuple[uuid.UUID, int]:
        node_id = uuid.uuid4()
        short_id = self._next_short_id
        self._next_short_id += 1
        return node_id, short_id


def _node(
    allocator: _IdAllocator,
    kind: str,
    fields: Optional[Dict[str, Any]] = None,
    children: Sequence[Node] = (),
) -> Node:
    """Build one already-identified ``Node`` via the real ``make_node`` schema."""

    built = make_node(kind, fields=fields or {}, children=tuple(children))
    node_id, short_id = allocator()
    return dataclasses.replace(built, node_id=node_id, short_id=short_id)


class FakeFormatPlugin:
    """Minimal duck-typed format plugin satisfying the adapter's contract.

    ``role_map`` declares exactly the kind -> role entries this fake plugin
    supports (mirroring ``FormatPluginContract.semantic_role_mapping``); a
    node kind with no entry resolves to no role. ``parse_calls`` counts any
    invocation of :meth:`parse_document`, this fixture's stand-in for "the
    fixture's own source-parsing routine" -- the traversal adapter must
    never call it.
    """

    def __init__(self, role_map: Dict[str, str]) -> None:
        self._role_map = dict(role_map)
        self.parse_calls = 0

    def semantic_role_mapping(self) -> Dict[str, str]:
        return self._role_map

    def parse_document(self, *args: Any, **kwargs: Any) -> None:
        self.parse_calls += 1
        raise AssertionError("traversal must never call into source parsing")


# ---------------------------------------------------------------------------
# 1. Each of the four standard semantic roles resolves correctly.
# ---------------------------------------------------------------------------


def test_standard_role_resolution() -> None:
    allocator = _IdAllocator()
    plugin = FakeFormatPlugin(
        {
            "fmt:Module": "module",
            "fmt:Class": "class",
            "fmt:Func": "function",
            "fmt:Method": "method",
        }
    )
    method_node = _node(allocator, "fmt:Method", {"name": "on_click"})
    func_node = _node(allocator, "fmt:Func", {"name": "helper"})
    class_node = _node(allocator, "fmt:Class", {"name": "Widget"}, (method_node,))
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (class_node, func_node))
    document = Document(root=module_node, source_format_id="fmt")
    adapter = TreeTraversalAdapter(document, plugin)

    assert resolve_semantic_role(plugin, module_node) == "module"
    assert resolve_semantic_role(plugin, class_node) == "class"
    assert resolve_semantic_role(plugin, func_node) == "function"
    assert resolve_semantic_role(plugin, method_node) == "method"

    for role, expected_node in (
        ("module", module_node),
        ("class", class_node),
        ("function", func_node),
        ("method", method_node),
    ):
        matches = list(adapter.iter_matching_nodes(role))
        assert len(matches) == 1, f"role {role!r} expected exactly one match"
        assert matches[0].node_id == expected_node.node_id


# ---------------------------------------------------------------------------
# 2. A role the fake plugin does not support yields no matches, not an error.
# ---------------------------------------------------------------------------


def test_inapplicable_role_yields_no_matches() -> None:
    allocator = _IdAllocator()
    # This plugin never maps anything to "method"; the format is not
    # modeled as having one.
    plugin = FakeFormatPlugin({"fmt:Module": "module", "fmt:Class": "class"})
    class_node = _node(allocator, "fmt:Class", {"name": "Widget"})
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (class_node,))
    document = Document(root=module_node, source_format_id="fmt")
    adapter = TreeTraversalAdapter(document, plugin)

    assert resolve_semantic_role(plugin, class_node) == "class"
    matches = list(adapter.iter_matching_nodes("method"))
    assert matches == []


# ---------------------------------------------------------------------------
# 3. A format-specific extension type stays reachable by its own literal
#    kind, independent of the four standard roles.
# ---------------------------------------------------------------------------


def test_extension_type_reachable_by_own_name() -> None:
    allocator = _IdAllocator()
    plugin = FakeFormatPlugin({"fmt:Module": "module"})
    extension_node = _node(allocator, "fmt:PreprocessorDirective", {"name": "include"})
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (extension_node,))
    document = Document(root=module_node, source_format_id="fmt")
    adapter = TreeTraversalAdapter(document, plugin)

    # No role applies to this kind at all.
    assert resolve_semantic_role(plugin, extension_node) == ""

    matches = list(adapter.iter_matching_nodes("fmt:PreprocessorDirective"))
    assert len(matches) == 1
    assert matches[0].node_id == extension_node.node_id
    assert matches[0].kind == ""  # no standard role, but still reachable

    # A standard-role query must not accidentally also pick it up.
    module_matches = list(adapter.iter_matching_nodes("module"))
    assert len(module_matches) == 1
    assert module_matches[0].node_id == module_node.node_id


# ---------------------------------------------------------------------------
# 4. Every match carries a correctly ordered root-to-parent ancestor path,
#    with node_id and short_id_hex present on every ancestor entry.
# ---------------------------------------------------------------------------


def test_parent_path_ordering_and_addressing() -> None:
    allocator = _IdAllocator()
    plugin = FakeFormatPlugin(
        {"fmt:Module": "module", "fmt:Class": "class", "fmt:Method": "method"}
    )
    method_node = _node(allocator, "fmt:Method", {"name": "on_click"})
    class_node = _node(allocator, "fmt:Class", {"name": "Widget"}, (method_node,))
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (class_node,))
    document = Document(root=module_node, source_format_id="fmt")
    adapter = TreeTraversalAdapter(document, plugin)

    matches = list(adapter.iter_matching_nodes("method"))
    assert len(matches) == 1
    parent_path = matches[0].parent_path
    assert len(parent_path) == 2

    # Root-first, immediate-parent-last ordering.
    assert parent_path[0].node_id == str(module_node.node_id)
    assert parent_path[1].node_id == str(class_node.node_id)

    for ancestor_view in parent_path:
        assert ancestor_view.node_id
        uuid.UUID(ancestor_view.node_id)  # must be a syntactically valid UUID
        assert ancestor_view.short_id_hex.startswith("0x")
        assert len(ancestor_view.short_id_hex) > 2


# ---------------------------------------------------------------------------
# 5. Traversal never triggers the fixture's own source-parsing routine.
# ---------------------------------------------------------------------------


def test_traversal_never_reparses_source() -> None:
    allocator = _IdAllocator()
    plugin = FakeFormatPlugin({"fmt:Module": "module", "fmt:Class": "class"})
    class_node = _node(allocator, "fmt:Class", {"name": "Widget"})
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (class_node,))
    document = Document(root=module_node, source_format_id="fmt")
    adapter = TreeTraversalAdapter(document, plugin)

    list(adapter.iter_nodes())
    list(adapter.iter_matching_nodes())
    list(adapter.iter_matching_nodes("class"))

    assert plugin.parse_calls == 0


# ---------------------------------------------------------------------------
# 6. Traversal never mutates the fixture tree, the document, or any index.
# ---------------------------------------------------------------------------


def test_traversal_never_mutates_tree() -> None:
    allocator = _IdAllocator()
    plugin = FakeFormatPlugin({"fmt:Module": "module", "fmt:Class": "class"})
    class_node = _node(allocator, "fmt:Class", {"name": "Widget"})
    module_node = _node(allocator, "fmt:Module", {"name": "mod"}, (class_node,))
    document = Document(root=module_node, source_format_id="fmt")
    # Attach extension-point state the module docstring says may live on
    # Document/Node without disturbing this file, to prove it survives
    # traversal untouched (Document/Node declare no __slots__).
    document.document_id = uuid.uuid4()  # type: ignore[assignment]
    marker_index = {"marker": True}
    document.index = marker_index  # type: ignore[attr-defined]

    original_root = document.root
    original_children = document.root.children
    original_version = document.document_id
    original_representation = document.representation_format_id

    adapter = TreeTraversalAdapter(document, plugin)
    list(adapter.iter_nodes())
    list(adapter.iter_matching_nodes())
    list(adapter.iter_matching_nodes("class"))

    assert document.root is original_root
    assert document.root.children is original_children
    assert document.document_id == original_version
    assert document.representation_format_id == original_representation
    assert document.index is marker_index
    assert document.index == {"marker": True}
    assert document.root == module_node
    assert class_node.fields == {"name": "Widget"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
