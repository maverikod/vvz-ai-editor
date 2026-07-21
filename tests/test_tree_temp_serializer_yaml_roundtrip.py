"""Round-trip tests for YAML SourceSerializer (tree-temp plan).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.tree_node import TreeNode
from ai_editor.core.tree_temp.yaml_emit import emit_yaml_source_from_roots
from ai_editor.core.tree_temp.yaml_frontend import parse_yaml_source_to_roots


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


def _flatten_roots(roots: list[TreeNode]) -> list[tuple[object, ...]]:
    out: list[tuple[object, ...]] = []

    def visit(n: TreeNode, d: int) -> None:
        out.append(_struct_tuple(n, d))
        if n.children:
            for ch in n.children:
                visit(ch, d + 1)

    for r in roots:
        visit(r, 0)
    return out


def test_yaml_roundtrip_inline_hash_comment() -> None:
    source = "name: alex  #nick\n"
    r1 = parse_yaml_source_to_roots(source)
    mid = emit_yaml_source_from_roots(r1)
    r2 = parse_yaml_source_to_roots(mid)
    root = r2[0]
    name_node = next(c for c in (root.children or []) if c.key == "name")
    assert "nick" in (name_node.comment_inline or "")


def test_yaml_roundtrip_block_mapping_sequence_mix() -> None:
    source = "items:\n  - 1\n  - two  #lbl\n"
    r1 = parse_yaml_source_to_roots(source)
    mid = emit_yaml_source_from_roots(r1)
    r2 = parse_yaml_source_to_roots(mid)
    items = r2[0].children[0]
    assert items.type == "array"
    assert items.children is not None
    second = items.children[1]
    blob = (second.comment_inline or "") + (second.comment_before or "")
    assert "lbl" in blob


def test_yaml_roundtrip_multiline_above_root() -> None:
    source = "#banner\nflat: yes\n"
    r1 = parse_yaml_source_to_roots(source)
    mid = emit_yaml_source_from_roots(r1)
    r2 = parse_yaml_source_to_roots(mid)
    root = r2[0]
    assert root.comment_before is not None
    assert "banner" in root.comment_before


def test_yaml_roundtrip_preserves_scalar_quote_style() -> None:
    """45b27a37 fidelity: double/single/plain scalar quote style survives a
    parse -> emit round trip untouched (no edit occurred)."""
    source = 'dq: "abc-123"\nsq: \'single-quoted\'\nplain: value2\n'
    roots = parse_yaml_source_to_roots(source)
    out = emit_yaml_source_from_roots(roots)
    assert out == source


def test_yaml_double_roundtrip_equals_single() -> None:
    source = "a: 1\nb: 2\n"
    once = parse_yaml_source_to_roots(source)
    mid = emit_yaml_source_from_roots(once)
    second = parse_yaml_source_to_roots(
        emit_yaml_source_from_roots(parse_yaml_source_to_roots(mid))
    )
    assert _flatten_roots(parse_yaml_source_to_roots(mid)) == _flatten_roots(second)
