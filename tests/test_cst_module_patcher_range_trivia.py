"""
Regression: range (and other statement) replacements must preserve LibCST
leading_lines / trailing_whitespace so blank lines outside the edited lines
remain (imports, E302 before classes).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.cst_module import ReplaceOp, Selector, apply_replace_ops


def test_range_replace_single_import_preserves_blank_lines_around() -> None:
    """Blank lines before and after the import line stay when only that line is replaced."""
    source = """from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.cst_tree.node_id_markers import build_exact_key_to_id_from_metadata
"""
    op = ReplaceOp(
        Selector(kind="range", start_line=3, end_line=3),
        "from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult  # type: ignore[import-untyped]",
    )
    new_source, stats = apply_replace_ops(source, [op])
    assert stats["replaced"] == 1
    assert stats["unmatched"] == []
    lines = new_source.splitlines()
    assert lines[0] == "from typing import Any, Dict, List, Optional"
    assert lines[1] == ""
    assert "type: ignore[import-untyped]" in lines[2]
    assert lines[3] == ""
    assert lines[4].startswith("from ..core.cst_tree")


def test_range_replace_class_preserves_double_blank_before_e302_spacing() -> None:
    """Replacing a top-level class must keep leading blank lines on the class node."""
    source = """def foo():
    pass


class Bar:
    pass
"""
    op = ReplaceOp(
        Selector(kind="range", start_line=5, end_line=6),
        "class Barren:\n    pass",
    )
    new_source, stats = apply_replace_ops(source, [op])
    assert stats["replaced"] == 1
    lines = new_source.splitlines()
    assert lines[0] == "def foo():"
    assert lines[1] == "    pass"
    assert lines[2] == ""
    assert lines[3] == ""
    assert lines[4] == "class Barren:"
    assert lines[5] == "    pass"


def test_range_replace_preserves_blank_after_when_followed_by_code() -> None:
    """Blank line before the following statement (its leading_lines) stays when editing the line above."""
    source = "x = 1\n\ny = 2\n"
    op = ReplaceOp(Selector(kind="range", start_line=1, end_line=1), "x = 2")
    new_source, _ = apply_replace_ops(source, [op])
    assert new_source == "x = 2\n\ny = 2\n"


def test_range_line_only_resolves_first_line_of_multiline_call() -> None:
    """Line-only range must match the full SimpleStatementLine span, not only the first line."""
    source = """def f():
    if True:
        logger.warning(
            "hi"
        )
"""
    op = ReplaceOp(Selector(kind="range", start_line=3, end_line=3), "print(42)")
    new_source, stats = apply_replace_ops(source, [op])
    assert stats["replaced"] == 1
    assert stats["unmatched"] == []
    assert "print(42)" in new_source
    assert "logger.warning" not in new_source


def test_range_line_only_nested_indented_block_first_line_multiline() -> None:
    """Same resolution inside a nested IndentedBlock (not only module-level)."""
    source = """def outer():
    if True:
        foo(
            1
        )
"""
    op = ReplaceOp(Selector(kind="range", start_line=3, end_line=3), "x = 0")
    new_source, stats = apply_replace_ops(source, [op])
    assert stats["replaced"] == 1
    assert stats["unmatched"] == []
    assert "x = 0" in new_source
    assert "foo(" not in new_source
