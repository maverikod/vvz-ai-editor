"""YAML SourceParser pytest coverage for tree_temp plan; Author Vasiliy Zdanovskiy; email vasilyvz@gmail.com."""

from __future__ import annotations

import pytest

from ai_editor.core.tree_temp.tree_node import TreeNode, kind_as_str
from ai_editor.core.tree_temp.yaml_frontend import parse_yaml_source_to_roots
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    _value_to_single_node,
)


def _first_root_must_be_objects_or_array(parsed: list[TreeNode]) -> TreeNode:
    assert len(parsed) == 1
    return parsed[0]


def _find_child(root: TreeNode, key: str) -> TreeNode:
    assert root.children is not None
    for c in root.children:
        if c.key == key:
            return c
    raise AssertionError(key)


def test_yaml_hash_inline_maps_to_scalar_member() -> None:
    source = "top: leaf  # mark\n"
    node = _first_root_must_be_objects_or_array(parse_yaml_source_to_roots(source))
    assert kind_as_str(node) == "object"
    leaf = _find_child(node, "top")
    assert leaf.value == "leaf"
    assert leaf.comment_inline is not None
    assert "mark" in leaf.comment_inline


def test_yaml_above_line_maps_before_next_mapping_pair() -> None:
    source = "# head\naaa: bbb\n"
    roots = parse_yaml_source_to_roots(source)
    root = roots[0]
    assert root.comment_before is not None
    assert "head" in root.comment_before


def test_yaml_sequence_three_elements_under_array_root() -> None:
    source = "- 1\n- 2\n- 3\n"
    roots = parse_yaml_source_to_roots(source)
    assert len(roots) == 3
    assert all(kind_as_str(x) == "number" for x in roots)
    for idx, expected in enumerate((1, 2, 3)):
        assert float(roots[idx].value) == float(expected)


def test_yaml_sequence_single_element_under_array_root() -> None:
    """One-element list payloads must become array TreeNodes, not bare objects."""
    node = _value_to_single_node("yaml", [{"start": 1336, "end": 1353}])
    assert kind_as_str(node) == "array"
    assert node.children is not None
    assert len(node.children) == 1
    child = node.children[0]
    assert kind_as_str(child) == "object"
    assert child.children is not None
    keys = {c.key for c in child.children}
    assert keys == {"start", "end"}


def test_yaml_mapping_order_not_alphabetical() -> None:
    source = "zzz: 0\naaa: 1\n"
    root = _first_root_must_be_objects_or_array(parse_yaml_source_to_roots(source))
    assert root.children is not None
    assert [c.key for c in root.children] == ["zzz", "aaa"]


def test_yaml_nested_mapping_value() -> None:
    source = "wrapper:\n  inner: true\n"
    root = _first_root_must_be_objects_or_array(parse_yaml_source_to_roots(source))
    wrap = _find_child(root, "wrapper")
    assert kind_as_str(wrap) == "object"
    inner = _find_child(wrap, "inner")
    assert inner.value is True


def test_yaml_null_keyword() -> None:
    source = "hole: null\n"
    root = _first_root_must_be_objects_or_array(parse_yaml_source_to_roots(source))
    h = _find_child(root, "hole")
    assert kind_as_str(h) == "null"
    assert h.value is None


def test_yaml_truncated_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_yaml_source_to_roots("[")
