"""Tree-temp insert: before_json_pointer / after_json_pointer sibling anchors."""

from __future__ import annotations

import uuid

from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    _apply_insert,
    _stable_index,
)
from ai_editor.core.tree_temp.tree_node import TreeNode


def _array_item(value: str, key: str | None = None) -> TreeNode:
    return TreeNode(
        stable_id=str(uuid.uuid4()),
        type="string",
        key=key,
        value=value,
        children=None,
    )


def test_insert_before_json_pointer_orders_array() -> None:
    a = _array_item("a")
    b = _array_item("b")
    c = _array_item("c")
    parent = TreeNode(
        stable_id=str(uuid.uuid4()),
        type="array",
        key="items",
        value=None,
        children=[a, b, c],
    )
    root = TreeNode(
        stable_id=str(uuid.uuid4()),
        type="object",
        key=None,
        value=None,
        children=[parent],
    )
    roots = [root]
    idx_map = _stable_index(roots)
    _apply_insert(
        roots,
        "json",
        {
            "parent_json_pointer": "/items",
            "value": "x",
            "before_json_pointer": "/items/1",
        },
        idx_map,
    )
    values = [ch.value for ch in parent.children or []]
    assert values == ["a", "x", "b", "c"]


def test_insert_position_before_colon_json_pointer() -> None:
    a = _array_item("a")
    b = _array_item("b")
    parent = TreeNode(
        stable_id=str(uuid.uuid4()),
        type="array",
        key="items",
        value=None,
        children=[a, b],
    )
    root = TreeNode(
        stable_id=str(uuid.uuid4()),
        type="object",
        key=None,
        value=None,
        children=[parent],
    )
    roots = [root]
    _apply_insert(
        roots,
        "json",
        {
            "parent_json_pointer": "/items",
            "value": "z",
            "position": "before:/items/1",
        },
        _stable_index(roots),
    )
    assert [ch.value for ch in parent.children or []] == ["a", "z", "b"]


def test_insert_position_after_colon_key() -> None:
    first = _array_item("1", key="first")
    third = _array_item("3", key="third")
    parent = TreeNode(
        stable_id=str(uuid.uuid4()),
        type="object",
        key=None,
        value=None,
        children=[first, third],
    )
    roots = [parent]
    _apply_insert(
        roots,
        "json",
        {
            "parent_json_pointer": "",
            "key": "second",
            "value": 2,
            "position": "after:first",
        },
        _stable_index(roots),
    )
    keys = [ch.key for ch in parent.children or []]
    assert keys == ["first", "second", "third"]
