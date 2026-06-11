"""Unit tests for markdown section line range resolution."""

from __future__ import annotations

from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.markdown_line_ranges import (
    md_block_node_ref,
    resolve_markdown_line_range,
)
from markdown_it import MarkdownIt

_LEAF_SECTION = """\
# Only Section

This section has body text but no sub-sections.
"""


def test_section_replace_range_includes_heading_line() -> None:
    bounds = resolve_markdown_line_range(_LEAF_SECTION, "only-section")
    assert not isinstance(bounds, PreviewError)
    start_line, end_line = bounds
    assert start_line == 1
    lines = _LEAF_SECTION.splitlines()
    assert lines[start_line - 1].startswith("# Only Section")
    assert end_line >= start_line


def test_content_suffix_range_excludes_heading_line() -> None:
    bounds = resolve_markdown_line_range(_LEAF_SECTION, "only-section/__content")
    assert not isinstance(bounds, PreviewError)
    start_line, _end_line = bounds
    assert start_line == 3
    assert (
        _LEAF_SECTION.splitlines()[start_line - 1]
        == "This section has body text but no sub-sections."
    )


def test_uuid_block_node_ref_resolves_to_line_range(tmp_path) -> None:
    md = tmp_path / "doc.md"
    path = str(md)
    content = "# Title\n\nBody paragraph.\n"
    md.write_text(content, encoding="utf-8")
    token = next(
        t
        for t in MarkdownIt().parse(content)
        if t.type == "paragraph_open" and t.map is not None
    )
    ref = md_block_node_ref(path, token)
    bounds = resolve_markdown_line_range(content, ref, file_path=path)
    assert not isinstance(bounds, PreviewError)
    start_line, end_line = bounds
    assert start_line == 3
    assert end_line >= 3
    assert "Body paragraph." in content.splitlines()[start_line - 1 : end_line]
