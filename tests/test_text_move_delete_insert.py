"""
Text move via delete+insert and Paragraph/Line node_ref resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_editor.commands.universal_file_edit.text_move_support import (
    expand_text_move_operations,
)
from ai_editor.commands.universal_file_edit.text_node_ref import (
    resolve_text_block_line_range,
    text_uses_paragraph_line_tree,
)
from ai_editor.tree.contracts import NodeId
from ai_editor.tree.handlers.text_handler import TextHandler


def test_text_uses_paragraph_line_tree_modes() -> None:
    assert (
        text_uses_paragraph_line_tree(Path("a.txt"), session_is_invalid=False) is True
    )
    assert (
        text_uses_paragraph_line_tree(Path("a.jsonl"), session_is_invalid=False)
        is False
    )
    assert (
        text_uses_paragraph_line_tree(Path("a.txt"), session_is_invalid=True) is False
    )


def test_paragraph_line_block_range_spans_continuation_lines(tmp_path: Path) -> None:
    draft = tmp_path / "note.txt"
    draft.write_text("Alpha one\nAlpha two\n\nBeta\n", encoding="utf-8")
    bounds = resolve_text_block_line_range(
        draft,
        "1",
        session_is_invalid=False,
    )
    assert bounds == (1, 2)


def test_flat_line_index_for_jsonl(tmp_path: Path) -> None:
    draft = tmp_path / "events.jsonl"
    draft.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    bounds = resolve_text_block_line_range(
        draft,
        "1",
        session_is_invalid=False,
    )
    assert bounds == (2, 2)


def test_text_handler_move_via_delete_insert_preserves_content() -> None:
    handler = TextHandler()
    source = "First line\nSecond line\n\nThird block\n"
    marked = handler.mark(source)
    tail_sid = NodeId(3)
    head_sid = NodeId(1)
    moved = handler.op_move(marked, tail_sid, head_sid, "before")
    restored = handler.unmark(moved)
    assert restored.splitlines() == ["Third block", "First line", "", "Second line"]


def test_expand_text_move_to_delete_insert(tmp_path: Path) -> None:
    draft = tmp_path / "note.txt"
    draft.write_text("Alpha one\nAlpha two\n\nThird block\n", encoding="utf-8")
    session = MagicMock()
    session.draft_path = draft
    session.is_invalid = False
    buffer = draft.read_text(encoding="utf-8").splitlines(keepends=True)
    operations = [
        {
            "type": "move",
            "node_ref": "3",
            "target_node_id": "1",
            "position": "before",
        }
    ]
    expanded, err = expand_text_move_operations(session, buffer, operations)
    assert err is None
    assert len(expanded) == 2
    assert expanded[0]["type"] == "delete"
    assert expanded[0]["start_line"] == 4
    assert expanded[0]["end_line"] == 4
    assert expanded[1]["type"] == "insert"
    assert expanded[1]["content"] == "Third block\n"
    assert expanded[1]["start_line"] == 1
