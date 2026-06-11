"""Unit tests for text-format unified-tree routing helpers."""

from __future__ import annotations

from ai_editor.core.edit_session.edit_operations_adapter import (
    text_ops_use_unified_tree,
)


def test_text_ops_use_unified_tree_accepts_target_node_id_insert() -> None:
    ops = [
        {
            "type": "insert",
            "target_node_id": "91",
            "position": "before",
            "content": "x",
        }
    ]
    assert text_ops_use_unified_tree(ops) is True


def test_text_ops_use_unified_tree_rejects_line_only_insert() -> None:
    ops = [{"type": "insert", "start_line": 3, "content": "x"}]
    assert text_ops_use_unified_tree(ops) is False


def test_text_ops_use_unified_tree_accepts_after_node_id() -> None:
    ops = [{"type": "insert", "after_node_id": "5", "content": "x"}]
    assert text_ops_use_unified_tree(ops) is True
