"""Markdown section body must appear on focus.text, not in blocks[]."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.markdown_handler import (
    MarkdownFileHandler,
)
from ai_editor.commands.universal_file_preview.models import NodeKind
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.response import build_envelope


def _section_tree_budget(*, value_preview_len: int = 10) -> PreviewBudget:
    """Budget that forces section-tree mode (not annotated full-text)."""
    return PreviewBudget(
        preview_lines=20,
        value_preview_len=value_preview_len,
        full_text_max_lines=0,
    )


def _preview_md(
    tmp_path: Path,
    content: str,
    *,
    node_ref: str | None = None,
    value_preview_len: int = 10,
) -> dict:
    md = tmp_path / "doc.md"
    md.write_text(content, encoding="utf-8")
    budget = _section_tree_budget(value_preview_len=value_preview_len)
    handler = MarkdownFileHandler()
    params = {
        "file_path": str(md),
        "project_id": "test-proj",
        "node_ref": node_ref,
        "selector": None,
        "preview_budget": budget,
    }
    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    return build_envelope(nav, None, "none")


_PARENT_WITH_SUBS = """\
# Parent

Parent body paragraph here.

## Sub One

Sub one body.

## Sub Two

Sub two body.
"""

_LEAF_SECTION = """\
# Only Section

This section has body text but no sub-sections.
"""


def test_section_with_subsections_excludes_content_from_blocks(
    tmp_path: Path,
) -> None:
    """AC-1: blocks[] lists only real sub-sections, never /__content."""
    envelope = _preview_md(tmp_path, _PARENT_WITH_SUBS, node_ref="parent")
    blocks = envelope["blocks"]
    assert envelope["total_blocks"] == 2
    assert len(blocks) == 2
    refs = [b["node_ref"] for b in blocks]
    assert refs == ["parent.sub-one", "parent.sub-two"]
    assert not any(ref.endswith("/__content") for ref in refs)


def test_section_focus_text_holds_full_body(tmp_path: Path) -> None:
    """AC-2: focus.text carries full body, not truncated by value_preview_len."""
    long_body = "x" * 200
    content = f"# Parent\n\n{long_body}\n\n## Sub\n\nchild\n"
    envelope = _preview_md(
        tmp_path,
        content,
        node_ref="parent",
        value_preview_len=10,
    )
    focus_text = envelope["focus"].get("text")
    assert isinstance(focus_text, str)
    assert focus_text == long_body
    assert len(focus_text) > 10


def test_leaf_section_has_empty_blocks_and_focus_text(tmp_path: Path) -> None:
    """AC-3: leaf section has empty blocks and body on focus.text."""
    envelope = _preview_md(tmp_path, _LEAF_SECTION, node_ref="only-section")
    assert envelope["total_blocks"] == 0
    assert envelope["blocks"] == []
    focus_text = envelope["focus"].get("text")
    assert isinstance(focus_text, str)
    assert "body text but no sub-sections" in focus_text


def test_content_node_ref_still_resolves_backward_compat(tmp_path: Path) -> None:
    """AC-4: explicit /__content node_ref still resolves as SCALAR focus."""
    md = tmp_path / "doc.md"
    md.write_text(_PARENT_WITH_SUBS, encoding="utf-8")
    handler = MarkdownFileHandler()
    budget = _section_tree_budget()
    assert not isinstance(handler.open_root(str(md), None, budget=budget), PreviewError)
    resolved = handler.resolve_node_ref("parent/__content", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.node_kind == NodeKind.SCALAR
    assert resolved.node_ref == "parent/__content"
    assert resolved.attributes.get("value") == "Parent body paragraph here."

    params = {
        "file_path": str(md),
        "project_id": "test-proj",
        "node_ref": "parent/__content",
        "selector": None,
        "preview_budget": budget,
    }
    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    assert nav.focus_node.node_kind == NodeKind.SCALAR
    envelope = build_envelope(nav, None, "none")
    assert envelope["focus"]["node_kind"] == "scalar"
    assert envelope["total_blocks"] == 0
