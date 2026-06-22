"""Tests for text search in tree_finder."""

from __future__ import annotations

from ai_editor.core.cst_tree import tree_builder as cst_builder
from ai_editor.core.cst_tree.tree_finder import find_nodes


_SOURCE = '''"""
Sample module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def alpha() -> str:
    """Alpha."""
    return "TERMINALS_DIR_PERMISSION_DENIED"


def beta() -> str:
    """Beta."""
    return "ok"
'''


def test_find_nodes_text_substring_match(tmp_path) -> None:
    source_path = tmp_path / "sample.py"
    source_path.write_text(_SOURCE, encoding="utf-8")
    tree = cst_builder.load_file_to_tree(str(source_path))
    try:
        matches = find_nodes(
            tree.tree_id,
            query="TERMINALS_DIR_PERMISSION_DENIED",
            search_type="text",
        )
        assert matches
        tree_obj = cst_builder.get_tree(tree.tree_id)
        assert tree_obj is not None
        lines = tree_obj.module.code.splitlines()
        for meta in matches:
            chunk = "\n".join(lines[meta.start_line - 1 : meta.end_line])
            assert "TERMINALS_DIR_PERMISSION_DENIED" in chunk
        for outer in matches:
            for inner in matches:
                if outer.node_id == inner.node_id:
                    continue
                outer_span = outer.end_line - outer.start_line
                inner_span = inner.end_line - inner.start_line
                if (
                    outer.start_line <= inner.start_line
                    and outer.end_line >= inner.end_line
                    and outer_span > inner_span
                ):
                    assert False, "ancestor should be deduped"
    finally:
        cst_builder.remove_tree(tree.tree_id)


def test_find_nodes_text_respects_line_range(tmp_path) -> None:
    source_path = tmp_path / "sample.py"
    source_path.write_text(_SOURCE, encoding="utf-8")
    tree = cst_builder.load_file_to_tree(str(source_path))
    try:
        matches = find_nodes(
            tree.tree_id,
            query="TERMINALS_DIR_PERMISSION_DENIED",
            search_type="text",
            start_line=10,
            end_line=14,
        )
        assert matches
        assert all(m.start_line >= 10 for m in matches)
        assert all(m.end_line <= 14 for m in matches)
    finally:
        cst_builder.remove_tree(tree.tree_id)
