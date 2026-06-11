"""Tests for MarkdownFileHandler annotated full-text mode."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.handlers.markdown_handler import (
    MarkdownFileHandler,
    _md_block_node_ref,
)
from ai_editor.commands.universal_file_preview.models import NodeKind


@pytest.fixture
def handler() -> MarkdownFileHandler:
    return MarkdownFileHandler()


def test_annotated_full_text_prefixes_block_start_lines(
    handler: MarkdownFileHandler, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nBody line.\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=50
    )
    node = handler.open_root(str(md), None, budget=budget)
    assert node.node_kind == NodeKind.TREE_NODE
    assert node.attributes.get("full_text") is True
    text = node.attributes["text"]
    lines = text.splitlines()
    assert lines[0].startswith("[")
    assert lines[0].rstrip().endswith("# Title")
    assert lines[1].startswith(" " * 39)
    assert lines[2].startswith("[")
    assert "Body line." in lines[2]


def test_annotated_full_text_exposes_top_level_blocks(
    handler: MarkdownFileHandler, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# H\n\npara\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=50
    )
    node = handler.open_root(str(md), None, budget=budget)
    types = {c.type_label for c in node.children}
    assert "heading_open" in types
    assert "paragraph_open" in types
    for child in node.children:
        assert child.node_kind == NodeKind.TREE_NODE
        assert "start_line" in child.attributes
        assert "end_line" in child.attributes


def test_resolve_uuid_block_node_ref(
    handler: MarkdownFileHandler, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    path = str(md)
    md.write_text("# Only\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=50
    )
    handler.open_root(path, None, budget=budget)
    from markdown_it import MarkdownIt

    tokens = [
        t
        for t in MarkdownIt().parse("# Only\n")
        if t.map is not None and t.type == "heading_open"
    ]
    ref = _md_block_node_ref(path, tokens[0])
    resolved = handler.resolve_node_ref(ref, None)
    assert resolved.node_kind == NodeKind.TREE_NODE
    assert resolved.type_label == "heading_open"


def test_open_root_reads_original_when_draft_empty(
    handler: MarkdownFileHandler, tmp_path: Path
) -> None:
    """Preview edit sessions use draft path; fall back when draft is still empty."""
    original = tmp_path / "doc.md"
    original.write_text("# Hello\n\nWorld\n", encoding="utf-8")
    draft = tmp_path / "doc.md.draft"
    draft.write_text("", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=9999
    )
    node = handler.open_root(str(draft), None, budget=budget)
    assert node.node_kind == NodeKind.TREE_NODE
    assert node.attributes.get("full_text") is True
    text = node.attributes["text"]
    assert "# Hello" in text
    assert "World" in text
    assert len(node.children) > 0


def test_uuid5_stable_across_reads(tmp_path: Path) -> None:
    path = str(tmp_path / "x.md")
    from markdown_it import MarkdownIt

    token = next(
        t
        for t in MarkdownIt().parse("# x\n")
        if t.type == "heading_open" and t.map is not None
    )
    a = _md_block_node_ref(path, token)
    b = _md_block_node_ref(path, token)
    assert a == b
    uuid.UUID(a)
