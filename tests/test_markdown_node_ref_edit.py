"""Markdown node_ref line ranges: preview attributes and text edit by node_ref."""

from __future__ import annotations

from pathlib import Path

import pytest
from markdown_it import MarkdownIt
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.handlers.markdown_handler import (
    MarkdownFileHandler,
)
from ai_editor.commands.universal_file_preview.handlers.markdown_line_ranges import (
    md_block_node_ref,
)
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.response import build_envelope
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    commit_write,
    ensure_session_marked_tree,
    open_ca_file,
    reset_ca_session,
    session_draft_path,
    upstream_context,
)

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"

_LEAF_SECTION = """\
# Only Section

This section has body text but no sub-sections.
"""

_PARENT_WITH_SUBS = """\
# Parent

Parent body paragraph here.

## Sub One

Sub one body.

## Sub Two

Sub two body.
"""


def _section_tree_budget() -> PreviewBudget:
    return PreviewBudget(
        preview_lines=20,
        value_preview_len=120,
        full_text_max_lines=0,
    )


def _preview_md(tmp_path: Path, content: str, node_ref: str) -> dict:
    md = tmp_path / "doc.md"
    md.write_text(content, encoding="utf-8")
    budget = _section_tree_budget()
    handler = MarkdownFileHandler()
    params = {
        "file_path": str(md),
        "project_id": "test-proj",
        "node_ref": node_ref,
        "selector": None,
        "preview_budget": budget,
    }
    from ai_editor.commands.universal_file_preview.errors import PreviewError

    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    return build_envelope(nav, None, "none")


async def _open_md(tmp: Path, rel: str, content: str) -> tuple[str, Path, Path, object]:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, rel)
    return await open_ca_file(
        tmp,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content.encode("utf-8"),
    )


async def _commit_md(
    *,
    workspace: Path,
    upstream: object,
    sid: str,
    rel: str,
) -> None:
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )


def test_preview_md_section_includes_line_range_attributes(tmp_path: Path) -> None:
    envelope = _preview_md(tmp_path, _LEAF_SECTION, "only-section")
    attrs = envelope["focus"]["attributes"]
    assert attrs["start_line"] == "1"
    assert int(attrs["end_line"]) >= 3


@pytest.mark.asyncio
async def test_edit_md_replace_by_uuid_node_ref_from_annotated_preview(
    tmp_path: Path,
) -> None:
    """uuid5 block node_ref from annotated full-text preview must work in edit."""
    rel = "notes/uuid_doc.md"
    content = "# Title\n\nParagraph to replace.\n"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, content)
    draft_path = str(session_draft_path(sid, rel).resolve())
    token = next(
        t
        for t in MarkdownIt().parse(content)
        if t.type == "paragraph_open" and t.map is not None
    )
    block_ref = md_block_node_ref(draft_path, token)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_ref": block_ref,
                            "content": "Replaced paragraph.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert "Replaced paragraph." in text
    assert "Paragraph to replace." not in text


@pytest.mark.asyncio
async def test_edit_md_replace_by_node_ref(tmp_path: Path) -> None:
    rel = "notes/doc.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_ref": "only-section",
                            "content": "# Only Section\n\nReplaced body.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    commit = await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    _ = commit
    text = origin.read_text(encoding="utf-8")
    assert "Replaced body." in text
    assert "body text but no sub-sections" not in text


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_before_section(tmp_path: Path) -> None:
    rel = "notes/before.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "only-section",
                            "position": "before",
                            "content": "## Preamble\n\nInserted before heading.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert text.index("## Preamble") < text.index("# Only Section")
    assert "Inserted before heading." in text


@pytest.mark.asyncio
async def test_edit_md_insert_position_after_colon_node_ref(tmp_path: Path) -> None:
    rel = "notes/colon.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "position": "after:only-section",
                            "content": "## Trail\n\nAfter via colon syntax.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert "After via colon syntax." in text
    assert text.index("body text") < text.index("## Trail")


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_after_section(tmp_path: Path) -> None:
    rel = "notes/doc.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "only-section",
                            "content": "## Added\n\nNew block.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert "New block." in text
    assert text.index("body text") < text.index("## Added")


def test_preview_md_plain_lines_line_range_attributes(tmp_path: Path) -> None:
    """Plain-line markdown preview exposes full-document line range."""
    content = "a\nb\nc\nd\n"
    envelope = _preview_md(tmp_path, content, "")
    attrs = envelope["focus"]["attributes"]
    assert attrs["start_line"] == "1"
    assert int(attrs["end_line"]) == len(content.splitlines())
    assert content.splitlines()[1:3] == ["b", "c"]


_MD_MULTI_BLOCK = """\
# HRS Title

First paragraph with {abc1}.

Second paragraph with {def2}.

Third paragraph with {ghi3}.
"""


@pytest.mark.asyncio
async def test_edit_md_insert_by_target_node_id_short_id(tmp_path: Path) -> None:
    """Marked-tree short_id via target_node_id must not fall back to line 1."""
    rel = "plans/source_spec.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)
    ensure_session_marked_tree(sid, rel)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": "4",
                            "position": "before",
                            "content": "Inserted between second and third.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert "Inserted between second and third." in text
    assert text.index("Second paragraph") < text.index(
        "Inserted between second and third."
    )
    assert text.index("Inserted between second and third.") < text.index(
        "Third paragraph"
    )
    assert not text.lstrip().startswith("Inserted between")


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_short_id(tmp_path: Path) -> None:
    """Integer node_ref from marked-tree preview inserts relative to that block."""
    rel = "plans/by_ref.md"
    sid, workspace, origin, upstream = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)
    ensure_session_marked_tree(sid, rel)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "4",
                            "position": "before",
                            "content": "Via node_ref short_id.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
    await _commit_md(workspace=workspace, upstream=upstream, sid=sid, rel=rel)
    text = origin.read_text(encoding="utf-8")
    assert "Via node_ref short_id." in text
    assert text.index("Second paragraph") < text.index("Via node_ref short_id.")
    assert text.index("Via node_ref short_id.") < text.index("Third paragraph")


@pytest.mark.asyncio
async def test_edit_md_insert_unknown_slug_returns_error(tmp_path: Path) -> None:
    """Non-resolving slug node_ref must not silently insert at file head."""
    rel = "plans/bad_slug.md"
    sid, workspace, _origin, upstream = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "no-such-section-slug",
                            "position": "before",
                            "content": "Should not appear.\n",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code == "UNKNOWN_NODE_REF"


def test_preview_parent_section_line_range_through_subsections(tmp_path: Path) -> None:
    """# Parent spans until the next h1 (here: end of file), not only direct body lines."""
    envelope = _preview_md(tmp_path, _PARENT_WITH_SUBS, "parent")
    attrs = envelope["focus"]["attributes"]
    assert attrs["start_line"] == "1"
    assert int(attrs["end_line"]) == len(_PARENT_WITH_SUBS.splitlines())
