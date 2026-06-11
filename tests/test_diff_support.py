"""
Tests for unified diff and changed-line metadata (text handlers).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.file_handlers.base import FileHandlerRequest
from ai_editor.core.file_handlers.diff_support import (
    changed_line_ranges_for_text,
    diff_data_for_text_mutation,
    merge_adjacent_changed_ranges,
    unified_diff_text,
)
from ai_editor.core.file_handlers.text_handler import TextFileHandler


def test_diff_data_skips_body_when_include_diff_false() -> None:
    d = diff_data_for_text_mutation(
        "a\n",
        "b\n",
        include_diff=False,
        before_label="x",
        after_label="y",
    )
    assert d == {"diff": "", "changed_line_ranges": []}


def test_unified_diff_headers_and_hunk() -> None:
    diff = unified_diff_text(
        "one\ntwo\n",
        "one\nTWO\n",
        before_label="a/f",
        after_label="b/f",
        context_lines=3,
    )
    assert "--- a/f" in diff
    assert "+++ b/f" in diff
    assert "@@" in diff
    assert "-two" in diff or "-two\n" in diff
    assert "+TWO" in diff or "+TWO\n" in diff


def test_changed_line_ranges_single_replacement() -> None:
    ranges = changed_line_ranges_for_text("a\nb\nc\n", "a\nX\nc\n")
    assert ranges == [(2, 2)]


def test_merge_adjacent_changed_ranges() -> None:
    assert merge_adjacent_changed_ranges([(1, 2), (3, 4)]) == [(1, 4)]
    assert merge_adjacent_changed_ranges([(2, 2), (4, 5)]) == [(2, 2), (4, 5)]


def test_context_lines_zero_vs_three_changes_diff_size() -> None:
    before = "\n".join([f"L{i}" for i in range(20)]) + "\n"
    after_lines = [f"L{i}" for i in range(20)]
    after_lines[10] = "CHANGED"
    after = "\n".join(after_lines) + "\n"
    d0 = unified_diff_text(
        before, after, before_label="a/x", after_label="b/x", context_lines=0
    )
    d3 = unified_diff_text(
        before, after, before_label="a/x", after_label="b/x", context_lines=3
    )
    assert len(d3) > len(d0)


def test_diff_data_matches_diff_data_for_text_mutation_shape() -> None:
    d = diff_data_for_text_mutation(
        "x\n",
        "y\n",
        include_diff=True,
        before_label="a/t",
        after_label="b/t",
        context_lines=1,
    )
    assert set(d) == {"diff", "changed_line_ranges"}
    assert isinstance(d["diff"], str)
    assert d["changed_line_ranges"] == [[1, 1]]


def test_text_handler_dry_run_save_same_diff_shape_no_file_write(
    tmp_path: Path,
) -> None:
    f = tmp_path / "n.md"
    f.write_text("alpha\nbeta\n", encoding="utf-8")
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="n.md",
        handler_id="text",
        operation="save",
        dry_run=True,
        diff=True,
        extra={
            "absolute_path": f,
            "content": "alpha\nBETA\n",
            "diff_context_lines": 2,
        },
    )
    r = h.save(req)
    assert r.success
    assert r.dry_run is True
    assert f.read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert "changed_line_ranges" in r.data
    assert r.data["changed_line_ranges"] == [[2, 2]]
    assert "@@" in (r.data.get("diff") or "")
    assert "would_change" in r.data


def test_text_handler_apply_matches_dry_run_diff_fields(tmp_path: Path) -> None:
    f = tmp_path / "n.md"
    f.write_text("alpha\nbeta\n", encoding="utf-8")
    h = TextFileHandler()
    extra = {
        "absolute_path": f,
        "content": "alpha\nBETA\n",
        "diff_context_lines": 2,
    }
    dry = h.save(
        FileHandlerRequest(
            project_id="p",
            file_path="n.md",
            handler_id="text",
            operation="save",
            dry_run=True,
            diff=True,
            extra=extra,
        )
    )
    before_apply = f.read_text(encoding="utf-8")
    applied = h.save(
        FileHandlerRequest(
            project_id="p",
            file_path="n.md",
            handler_id="text",
            operation="save",
            dry_run=False,
            diff=True,
            extra=extra,
        )
    )
    after_apply = f.read_text(encoding="utf-8")
    assert before_apply != after_apply
    assert set(applied.data).issuperset({"diff", "changed_line_ranges"})
    assert dry.data["diff"] == applied.data["diff"]
    assert dry.data["changed_line_ranges"] == applied.data["changed_line_ranges"]
