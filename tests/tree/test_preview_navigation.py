"""Preview navigation parent_short_id coherence (G-004 T-002)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, cast

from ai_editor.tree.contracts import NodeId
from ai_editor.tree.handlers.json_handler import JsonHandler
from ai_editor.tree.handlers.python_handler import PythonHandler
from ai_editor.tree.preview_navigation import (
    _build_indexes,
    _effective_focus_node,
    _expand_indented_blocks,
)
from ai_editor.tree.tree_node import TreeNode


@dataclass
class _NodeListTree:
    nodes: List[TreeNode]

    def all_nodes(self) -> List[TreeNode]:
        return self.nodes


def _enumerate_children(tree: _NodeListTree, focus_short_id: NodeId) -> List[TreeNode]:
    _, by_short_id, children_by_parent = _build_indexes(tree)
    focus = by_short_id.get(focus_short_id)
    assert focus is not None
    effective = _effective_focus_node(focus, by_short_id)
    direct = list(children_by_parent.get(effective.short_id, []))
    return cast(List[TreeNode], _expand_indented_blocks(direct, children_by_parent))


def test_python_function_focus_enumerates_body_statements() -> None:
    source = "def foo():\n" "    x = 1\n" "    return x\n"
    nodes = PythonHandler().parse_content(Path("sample.py"), source)
    func = next(n for n in nodes if n.attributes.get("node_type") == "FunctionDef")
    body_nodes = [n for n in nodes if n.parent_short_id == func.short_id]
    assert len(body_nodes) >= 2
    assert all(n.parent_short_id == func.short_id for n in body_nodes)

    tree = _NodeListTree(nodes)
    children = _enumerate_children(tree, func.short_id)
    child_ids = {c.short_id for c in children}
    assert body_nodes[0].short_id in child_ids
    assert body_nodes[1].short_id in child_ids


def test_json_scalar_focus_walks_up_via_parent_short_id() -> None:
    content = '{"a": 1, "b": {"c": 2}}'
    nodes = JsonHandler().parse_content(Path("sample.json"), content)
    by_pointer = {n.attributes["json_pointer"]: n for n in nodes}
    root = by_pointer["/"]
    scalar_a = by_pointer["/a"]
    nested_obj = by_pointer["/b"]
    nested_scalar = by_pointer["/b/c"]

    assert scalar_a.parent_short_id == root.short_id
    assert nested_obj.parent_short_id == root.short_id
    assert nested_scalar.parent_short_id == nested_obj.short_id

    tree = _NodeListTree(nodes)
    _, by_short_id, _ = _build_indexes(tree)
    effective = _effective_focus_node(scalar_a, by_short_id)
    assert effective.short_id == root.short_id

    children = _enumerate_children(tree, scalar_a.short_id)
    assert {c.short_id for c in children} == {nested_obj.short_id, scalar_a.short_id}


def test_json_object_focus_lists_direct_children() -> None:
    content = '{"a": 1, "b": 2}'
    nodes = JsonHandler().parse_content(Path("sample.json"), content)
    root = next(n for n in nodes if n.attributes["json_pointer"] == "/")
    children = _enumerate_children(_NodeListTree(nodes), root.short_id)
    assert len(children) == 2
    assert {c.attributes["json_pointer"] for c in children} == {"/a", "/b"}
