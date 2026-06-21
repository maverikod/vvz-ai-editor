"""Unit tests for plain-text preview line windows (invalid/fallback mode)."""

from __future__ import annotations

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from ai_editor.commands.universal_file_preview.invalid_preview import (
    apply_invalid_line_pagination,
    invalid_preview_line_params,
)
from ai_editor.commands.universal_file_preview.plain_text_preview_window import (
    slice_plain_text_view,
)
from ai_editor.commands.universal_file_preview.response import build_envelope
from ai_editor.commands.universal_file_preview.models import NavigationResult


def test_slice_plain_text_view_limits_lines() -> None:
    source = "\n".join(f"line-{i}" for i in range(100)) + "\n"
    window = slice_plain_text_view(source, line_offset=0, max_lines=20)
    assert window.lines_returned == 20
    assert window.total_lines == 100
    assert window.has_more is True
    assert window.next_line_offset == 20
    assert window.text.count("\n") == 20


def test_slice_plain_text_view_second_page() -> None:
    source = "\n".join(f"line-{i}" for i in range(50)) + "\n"
    window = slice_plain_text_view(source, line_offset=20, max_lines=10)
    assert window.line_offset == 20
    assert window.lines_returned == 10
    assert window.text.startswith("line-20\n")
    assert window.has_more is True
    assert window.next_line_offset == 30


def test_invalid_json_handler_windows_large_file(tmp_path) -> None:
    lines = [f'{{"row": {i},' for i in range(50)]
    bad = tmp_path / "big.json"
    bad.write_text("\n".join(lines), encoding="utf-8")
    budget = PreviewBudget(preview_lines=5, value_preview_len=120)
    node = JsonFileHandler().open_root(str(bad), None, budget)
    assert node.is_invalid is True
    assert node.attributes["preview_total_lines"] == 50
    assert node.attributes["preview_lines_returned"] == 5
    assert node.attributes["preview_has_more"] is True
    assert node.attributes["preview_next_offset"] == 5
    assert node.attributes["full_text"] is False
    assert node.attributes["text"].count("\n") == 5


def test_invalid_preview_line_params_from_budget() -> None:
    budget = PreviewBudget(
        preview_lines=15,
        value_preview_len=80,
        preview_offset=10,
        max_chars=500,
    )
    assert invalid_preview_line_params(budget) == {
        "line_offset": 10,
        "max_lines": 15,
        "max_chars": 500,
    }


def test_apply_invalid_line_pagination_merges_envelope() -> None:
    from ai_editor.commands.universal_file_preview.models import Node, NodeKind

    node = Node(
        node_kind=NodeKind.SCALAR,
        node_ref="",
        is_invalid=True,
        attributes={
            "text": "a\nb\n",
            "preview_total_lines": 2,
            "preview_line_offset": 0,
            "preview_lines_returned": 2,
            "preview_has_more": False,
            "preview_next_offset": None,
        },
    )
    nav = NavigationResult(
        focus_node=node,
        selected_blocks=[],
        total_blocks=0,
    )
    envelope = build_envelope(nav, None, "none")
    merged = apply_invalid_line_pagination(envelope, node.attributes)
    assert merged["preview_total_lines"] == 2
    assert merged["preview_has_more"] is False
    assert merged["preview_total_chars"] == len("a\nb\n")
