"""Unit tests for JSON SourceParser tolerant grammar and CommentOwnershipRule (tree-temp plan).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from ai_editor.core.tree_temp.json_frontend import parse_json_source_to_roots
from ai_editor.core.tree_temp.tree_node import TreeNode, kind_as_str


def _find_member(root_list: list[TreeNode], key: str) -> TreeNode:
    assert len(root_list) == 1
    root = root_list[0]
    assert root.children is not None
    for ch in root.children:
        if ch.key == key:
            return ch
    raise AssertionError(f"missing key {key!r}")


def test_top_level_above_comment_maps_to_before_on_first_root_object() -> None:
    src = "// file head\n{\n}\n"
    roots = parse_json_source_to_roots(src)
    assert len(roots) == 1
    r = roots[0]
    assert kind_as_str(r) == "object"
    assert r.comment_before is not None
    assert "// file head" in r.comment_before


def test_inline_comment_maps_to_scalar_member() -> None:
    roots = parse_json_source_to_roots('{"a": 1}// tail')
    m = _find_member(roots, "a")
    assert m.value in (1, 1.0)

    def _walk(n: TreeNode) -> bool:
        if "tail" in (n.comment_inline or ""):
            return True
        return any(_walk(c) for c in (n.children or []))

    assert _walk(roots[0])


def test_above_line_comment_before_next_member() -> None:
    src = '{"x":true,\n// between\n"y":false}\n'
    roots = parse_json_source_to_roots(src)
    y = _find_member(roots, "y")
    assert y.comment_before is not None
    assert "between" in y.comment_before


def test_array_root_order_three_elements() -> None:
    roots = parse_json_source_to_roots('[{"k":9},false,null]')
    assert len(roots) == 3
    assert [kind_as_str(x) for x in roots] == ["object", "boolean", "null"]
    k = _find_member([roots[0]], "k")
    assert k.value in (9, 9.0)


def test_object_member_order_not_sorted() -> None:
    roots = parse_json_source_to_roots('{"z":0,"y":1,"x":2}')
    root = roots[0]
    assert root.children is not None
    assert [c.key for c in root.children] == ["z", "y", "x"]


def test_scalar_types_number_bool_null_string() -> None:
    roots = parse_json_source_to_roots('{"n":42,"t":false,"u":null,"s":"hi"}')
    root = roots[0]
    assert root.children is not None
    by_key = {c.key: c for c in root.children}
    assert by_key["n"].value in (42, 42.0)
    assert by_key["t"].value is False
    assert by_key["u"].value is None
    assert by_key["s"].value == "hi"


def test_block_comment_before_key_maps_inline_on_member_same_line() -> None:
    roots = parse_json_source_to_roots('{/*solo*/ "b": 2}')
    m = _find_member(roots, "b")
    blob = (m.comment_inline or "") + (m.comment_before or "")
    assert "solo" in blob


def test_truncated_document_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_json_source_to_roots("{")
