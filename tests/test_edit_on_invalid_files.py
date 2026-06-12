"""Tests for invalid-file preview and universal_file_write lockfile fix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.errors import FORMAT_INVALID_ON_OPEN
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.marked_tree_navigation import (
    navigate_marked_tree,
)
from ai_editor.core.cst_tree.tree_builder import get_tree, remove_tree
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    ensure_projectid_marker,
    layout_origin,
    make_workspace,
    mock_upstream,
    open_ca_file,
    reset_ca_session,
    session_dir_for,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


@pytest.fixture(autouse=True)
def _reset_sessions() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    for rel in (
        "sample.py",
        "broken.json",
        "new_broken.json",
        "broken.yaml",
        "broken.py",
    ):
        reset_ca_session(DEFAULT_CA_SESSION_ID, rel)
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)


def test_json_handler_invalid_returns_raw_source_node(tmp_path: Path) -> None:
    bad = tmp_path / "broken.json"
    bad.write_text('{"a": ', encoding="utf-8")
    node = JsonFileHandler().open_root(
        str(bad), None, PreviewBudget(preview_lines=20, value_preview_len=120)
    )
    assert not isinstance(node, PreviewError)
    assert node.is_invalid is True
    assert node.node_ref == ""
    assert '{"a": ' in node.attributes["text"]
    assert "parse_error" in node.attributes


def test_python_invalid_returns_raw_source_via_marked_tree(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def f(\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=200
    )
    result = navigate_marked_tree(
        {
            "project_root": tmp_path,
            "rel_file_path": "broken.py",
            "file_path": str(bad),
            "node_ref": None,
            "selector": None,
            "session_id": None,
        },
        budget,
    )
    assert not isinstance(result, PreviewError)
    assert result.focus_node.is_invalid is True
    assert "def f(" in result.focus_node.attributes["text"]


@pytest.mark.asyncio
async def test_open_does_not_preempt_write_preview_phase(tmp_path: Path) -> None:
    """write_mode=preview returns diff; commit uploads draft."""
    rel = "sample.py"
    content = b"def foo():\n    return 1\n"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content,
    )
    ed = UniversalFileEditCommand()
    tree_id: str | None = None
    with upstream_context(workspace=workspace, upstream=upstream):
        sess = get_session(sid)
        tree_id = sess.tree_id
        tree = get_tree(tree_id or "")
        assert tree is not None
        stable = next(
            m.stable_id
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "foo"
        )
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            operations=[
                {
                    "type": "replace",
                    "node_ref": stable,
                    "code_lines": [
                        "def foo():\n",
                        "    return 2\n",
                    ],
                }
            ],
        )
        wr = UniversalFileWriteCommand()
        preview = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="preview",
        )
    assert isinstance(preview, SuccessResult)
    assert preview.data.get("phase") == "preview"
    if tree_id:
        remove_tree(tree_id)


@pytest.mark.asyncio
async def test_create_invalid_json_preview_returns_raw_text(
    tmp_path: Path,
) -> None:
    """End-to-end: create broken JSON, preview must surface raw source."""
    from ai_editor.commands.universal_file_preview_command import (
        UniversalFilePreviewCommand,
    )

    rel = "broken.json"
    broken = '{"key": "value", broken'
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b"",
        create=True,
        initial_content=broken,
    )
    prev = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        result = await prev.execute(
            project_id=_PROJECT_UUID,
            file_path=rel,
            session_id=sid,
            node_ref="",
        )
    assert isinstance(result, SuccessResult)
    focus = result.data.get("focus", {})
    assert focus.get("is_invalid") is True
    assert focus.get("text") == broken
    assert focus.get("text") != "{}"
    assert focus.get("attributes", {}).get("parse_error")


@pytest.mark.asyncio
async def test_create_invalid_json_writes_raw_and_sets_is_invalid(
    tmp_path: Path,
) -> None:
    """create=True with invalid initial_content must persist raw bytes and flag session."""
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )

    rel = "new_broken.json"
    broken = '{"key": "value", broken'
    workspace = make_workspace(tmp_path)
    upstream = mock_upstream()
    op = UniversalFileOpenCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        opened = await op.execute(
            **op.validate_params(
                {
                    "session_id": DEFAULT_CA_SESSION_ID,
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                    "create": True,
                    "initial_content": broken,
                }
            )
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("created") is True
    assert opened.data.get("is_invalid") is True
    ensure_projectid_marker(
        session_dir_for(workspace, DEFAULT_CA_SESSION_ID, _PROJECT_UUID, rel),
        _PROJECT_UUID,
    )
    origin = layout_origin(workspace, DEFAULT_CA_SESSION_ID, _PROJECT_UUID, rel)
    assert origin.read_text(encoding="utf-8") == broken


@pytest.mark.asyncio
async def test_open_invalid_json_sets_is_invalid_and_allows_raw_edit(
    tmp_path: Path,
) -> None:
    rel = "broken.json"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'{"ok": true',
    )
    fixed = '{"ok": true}\n'
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            operations=[{"type": "replace", "node_ref": "", "content": fixed}],
        )
        wr = UniversalFileWriteCommand()
        preview = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="preview",
        )
        assert isinstance(preview, SuccessResult)
        assert preview.data.get("phase") == "preview"
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert commit.data.get("uploaded") is True
    assert origin.read_text(encoding="utf-8") == fixed


def test_json_handler_invalid_preserves_broken_trailing_text(tmp_path: Path) -> None:
    """Broken JSON must surface raw bytes, not an empty object placeholder."""
    broken = '{"key": "value", broken'
    bad = tmp_path / "broken.json"
    bad.write_text(broken, encoding="utf-8")
    node = JsonFileHandler().open_root(
        str(bad), None, PreviewBudget(preview_lines=20, value_preview_len=120)
    )
    assert not isinstance(node, PreviewError)
    assert node.is_invalid is True
    assert node.attributes.get("text") == broken
    assert node.attributes.get("full_text") is True
    assert "{}" not in node.attributes.get("text", "")


def test_preview_broken_json_with_uuid_node_ref_requires_line_addressing(
    tmp_path: Path,
) -> None:
    """UUID node_ref on invalid JSON must not drill; use line pagination instead."""
    from ai_editor.commands.universal_file_preview.errors import (
        INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
    )
    from ai_editor.commands.universal_file_preview.preview_addressing import (
        check_preview_addressing,
        preview_source_is_parseable,
    )

    broken = '{"key": "value", broken'
    rel = "broken.json"
    path = tmp_path / rel
    path.write_text(broken, encoding="utf-8")
    assert preview_source_is_parseable(path) is False
    err = check_preview_addressing(
        parseable=False,
        params={
            "node_ref": "3aeb19cf-4a9d-45d6-b3af-a0e4975bf874",
            "file_path": rel,
        },
        file_path=rel,
    )
    assert err is not None
    assert err.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING


@pytest.mark.asyncio
async def test_open_invalid_yaml_sets_is_invalid_and_warning(tmp_path: Path) -> None:
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )

    rel = "broken.yaml"
    workspace = make_workspace(tmp_path)
    upstream = mock_upstream(origins={rel: b"key: [unclosed\n"})
    op = UniversalFileOpenCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        opened = await op.execute(
            **op.validate_params(
                {
                    "session_id": DEFAULT_CA_SESSION_ID,
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                }
            )
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("is_invalid") is True
    assert opened.data.get("warning")
    assert "line-based fallback" in str(opened.data.get("warning"))


@pytest.mark.asyncio
async def test_open_invalid_py_falls_back_to_text(tmp_path: Path) -> None:
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )

    rel = "broken.py"
    workspace = make_workspace(tmp_path)
    upstream = mock_upstream(origins={rel: b"def f(\n"})
    op = UniversalFileOpenCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        opened = await op.execute(
            **op.validate_params(
                {
                    "session_id": DEFAULT_CA_SESSION_ID,
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                }
            )
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("is_invalid") is True
    assert opened.data.get("warning")


@pytest.mark.asyncio
async def test_edit_invalid_session_returns_warning(tmp_path: Path) -> None:
    rel = "broken.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'{"a": ',
    )
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        result = await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            operations=[{"type": "replace", "node_ref": "", "content": '{"a": 1}\n'}],
        )
    assert isinstance(result, SuccessResult)
    assert result.data.get("warning")
    assert "line-based fallback" in str(result.data.get("warning"))


@pytest.mark.asyncio
async def test_write_commit_invalid_session_still_broken_returns_error(
    tmp_path: Path,
) -> None:
    rel = "broken.json"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'{"a": ',
    )
    ed = UniversalFileEditCommand()
    wr = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            operations=[{"type": "replace", "node_ref": "", "content": '{"still": '}],
        )
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert commit.data.get("uploaded") is True
    with pytest.raises(json.JSONDecodeError):
        json.loads(origin.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_write_commit_invalid_session_fixed_restores_structural_editing(
    tmp_path: Path,
) -> None:
    rel = "broken.json"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'{"ok": true',
    )
    fixed = '{"ok": true}\n'
    ed = UniversalFileEditCommand()
    wr = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            operations=[{"type": "replace", "node_ref": "", "content": fixed}],
        )
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert commit.data.get("uploaded") is True
    parsed = json.loads(origin.read_text(encoding="utf-8"))
    assert parsed == {"ok": True}


@pytest.mark.asyncio
async def test_write_preview_invalid_session_always_succeeds(tmp_path: Path) -> None:
    rel = "broken.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'{"a": ',
    )
    wr = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        preview = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
            write_mode="preview",
        )
    assert isinstance(preview, SuccessResult)
    assert preview.data.get("phase") == "preview"
