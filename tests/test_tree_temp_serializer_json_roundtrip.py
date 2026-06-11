"""Round-trip tests for tolerant JSON SourceSerializer (tree-temp plan).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.json_emit import emit_json_source_from_roots
from ai_editor.core.tree_temp.json_frontend import parse_json_source_to_roots
from ai_editor.core.tree_temp.tree_node import TreeNode


def _norm_comment(s: str | None) -> str:
    return (s or "").strip()


def _struct_tuple(node: TreeNode, depth: int) -> tuple[object, ...]:
    key = node.key
    vref: object
    if node.type in ("object", "array"):
        vref = len(node.children or ())
    else:
        vref = node.value
    return (
        node.type,
        key,
        vref,
        depth,
        _norm_comment(node.comment_before),
        _norm_comment(node.comment_inline),
    )


def _flatten(doc: str) -> list[tuple[object, ...]]:
    roots = parse_json_source_to_roots(doc)
    out: list[tuple[object, ...]] = []

    def visit(n: TreeNode, d: int) -> None:
        out.append(_struct_tuple(n, d))
        if n.children:
            for ch in n.children:
                visit(ch, d + 1)

    for r in roots:
        visit(r, 0)
    return out


def assert_roundtrip_stable_comments(document: str) -> None:
    r1 = parse_json_source_to_roots(document)
    mid = emit_json_source_from_roots(r1)
    r2 = parse_json_source_to_roots(mid)
    a = _flatten(document)
    b = _flatten(mid)
    if a != b:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                raise AssertionError(f"diverge at flat index {i}: {x!r} vs {y!r}")
        raise AssertionError(f"length mismatch {len(a)} vs {len(b)}")
    c = _flatten(
        emit_json_source_from_roots(parse_json_source_to_roots(mid)),
    )
    if b != c:
        raise AssertionError("second parse/emit cycle diverged")


def test_json_roundtrip_minimal_inline_and_above_comments() -> None:
    assert_roundtrip_stable_comments('//head\n{"a":1}//trail\n')


def test_json_roundtrip_nested_object_order() -> None:
    assert_roundtrip_stable_comments('{"outer":{"z":9,"y":8}}')


def test_json_roundtrip_array_root_numbers() -> None:
    assert_roundtrip_stable_comments("[10,11,12]")


def test_json_emit_parse_idempotent_twice_loop() -> None:
    doc = '{"x":1}'
    assert_roundtrip_stable_comments(doc)
    once = emit_json_source_from_roots(parse_json_source_to_roots(doc))
    twice = emit_json_source_from_roots(parse_json_source_to_roots(once))
    assert _flatten(once) == _flatten(twice)


def test_json_comment_only_line_between_members() -> None:
    assert_roundtrip_stable_comments('{"first":true,\n//mid\n"second":false}\n')
