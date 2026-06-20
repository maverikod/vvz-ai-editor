"""Multi-file CA session acceptance: open, write, close by file_path (C-004, C-006, C-022, {8b1h}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.core.editor_workspace_paths import file_workspace_layout
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus

_ORIGIN_BY_PATH = {
    "pkg/a.py": b'"""Alpha module."""\n\nx = 1\n',
    "other/b.py": b'"""Beta module."""\n\ny = 1\n',
}

_GET_CA_CLIENT_PATCHES = (
    "ai_editor.commands.universal_file_edit.open_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.open_command_runtime.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.close_command.get_code_analysis_client",
    "ai_editor.core.upstream.code_analysis_client.get_code_analysis_client",
)

_RESOLVE_WORKSPACE_PATCHES = (
    "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
    "ai_editor.commands.universal_file_edit.open_command_runtime.resolve_workspace_root",
    "ai_editor.commands.universal_file_edit.close_command.resolve_workspace_root",
)


def _mock_upstream() -> MagicMock:
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.VALID

    def _lock(*args: object, **kwargs: object) -> bytes:
        if len(args) >= 3:
            file_path = str(args[2])
        else:
            file_path = str(kwargs.get("file_path") or kwargs.get("path") or "")
        if file_path not in _ORIGIN_BY_PATH:
            raise KeyError(f"unexpected file_path: {file_path}")
        return _ORIGIN_BY_PATH[file_path]

    upstream.lock_file_and_download.side_effect = _lock
    upstream.upload_session_file_content.side_effect = lambda **kwargs: kwargs[
        "content"
    ]
    upstream.unlock_session_file.return_value = True
    return upstream


@contextmanager
def _upstream_context(*, workspace: Path, upstream: MagicMock) -> Iterator[None]:
    with ExitStack() as stack:
        for target in _RESOLVE_WORKSPACE_PATCHES:
            stack.enter_context(patch(target, return_value=workspace))
        for target in _GET_CA_CLIENT_PATCHES:
            stack.enter_context(patch(target, return_value=upstream))
        yield


def _ensure_projectid_marker(session_dir: Path, project_id: str) -> None:
    """BackupManager marker under session_dir (C-022: not at workspace root)."""
    (session_dir / "projectid").write_text(
        f'{{"id": "{project_id}"}}\n',
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_ca_sessions() -> Generator[None, None, None]:
    sid = "ca-multi"
    for file_path in _ORIGIN_BY_PATH:
        release_session(sid, file_path)
    yield
    for file_path in _ORIGIN_BY_PATH:
        release_session(sid, file_path)


def _assert_c022_all_under_session_dir(
    workspace: Path, session_dir: Path, *paths: Path
) -> None:
    ws = workspace.resolve()
    sd = session_dir.resolve()
    assert sd.is_dir()
    assert sd.is_relative_to(ws)
    for item in ws.iterdir():
        assert item.resolve() == sd
    for path in paths:
        assert path.resolve().is_relative_to(sd)
    for path in sd.rglob("*"):
        assert path.resolve().is_relative_to(sd)


async def _open_file(*, sid: str, project_id: str, file_path: str) -> SuccessResult:
    cmd = UniversalFileOpenCommand()
    res = await cmd.execute(session_id=sid, project_id=project_id, file_path=file_path)
    assert isinstance(res, SuccessResult), res
    return res


@pytest.mark.asyncio
async def test_multi_file_open_two_subtrees_share_session_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = "ca-multi"
    project_id = "proj"
    file_a = "pkg/a.py"
    file_b = "other/b.py"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = _mock_upstream()

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_a = await _open_file(sid=sid, project_id=project_id, file_path=file_a)
        open_b = await _open_file(sid=sid, project_id=project_id, file_path=file_b)

    layout_a = file_workspace_layout(workspace, sid, project_id, file_a)
    layout_b = file_workspace_layout(workspace, sid, project_id, file_b)

    assert open_a.data["session_id"] == sid
    assert open_b.data["session_id"] == sid
    assert layout_a.session_dir == layout_b.session_dir
    assert layout_a.file_subtree_dir != layout_b.file_subtree_dir
    assert layout_a.file_subtree_dir.is_dir()
    assert layout_b.file_subtree_dir.is_dir()

    assert layout_a.origin_path.is_file()
    assert layout_b.origin_path.is_file()
    assert layout_a.origin_path.read_bytes() == _ORIGIN_BY_PATH[file_a]
    assert layout_b.origin_path.read_bytes() == _ORIGIN_BY_PATH[file_b]

    draft_a = Path(open_a.data["draft_path"])
    draft_b = Path(open_b.data["draft_path"])
    assert draft_a.is_file()
    assert draft_b.is_file()
    assert draft_a.parent.is_dir()
    assert draft_b.parent.is_dir()
    assert draft_a.parent.is_relative_to(layout_a.file_subtree_dir)
    assert draft_b.parent.is_relative_to(layout_b.file_subtree_dir)

    _assert_c022_all_under_session_dir(
        workspace,
        layout_a.session_dir,
        layout_a.file_subtree_dir,
        layout_b.file_subtree_dir,
        layout_a.origin_path,
        layout_b.origin_path,
        draft_a,
        draft_b,
    )

    assert upstream.lock_file_and_download.call_count == 2
    assert str(workspace / sid) in open_a.data["session_dir"]
    assert str(workspace / sid) in open_b.data["session_dir"]


@pytest.mark.asyncio
async def test_multi_file_write_and_close_by_file_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = "ca-multi"
    project_id = "proj"
    file_a = "pkg/a.py"
    file_b = "other/b.py"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = _mock_upstream()

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_a = await _open_file(sid=sid, project_id=project_id, file_path=file_a)
        open_b = await _open_file(sid=sid, project_id=project_id, file_path=file_b)

        layout_a = file_workspace_layout(workspace, sid, project_id, file_a)
        layout_b = file_workspace_layout(workspace, sid, project_id, file_b)
        session_dir = layout_a.session_dir
        _ensure_projectid_marker(session_dir, project_id)
        draft_b = Path(open_b.data["draft_path"])

        write_cmd = UniversalFileWriteCommand()
        write_a = await write_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_a,
        )
        assert isinstance(write_a, SuccessResult)
        assert write_a.data.get("unchanged") is True
        assert upstream.upload_session_file_content.call_count == 0

        edit_cmd = UniversalFileEditCommand()
        search_cmd = UniversalFileSearchCommand()
        search_b = await search_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_b,
            search_type="simple",
            start_line=3,
            end_line=3,
        )
        assert isinstance(search_b, SuccessResult)
        y_ref = search_b.data["matches"][0]["node_ref"]
        edit_b = await edit_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_b,
            operations=[
                {
                    "type": "replace",
                    "node_ref": y_ref,
                    "code_lines": ["y = 2"],
                }
            ],
        )
        assert isinstance(edit_b, SuccessResult)

        write_b = await write_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_b,
            write_mode="commit",
        )
        assert isinstance(write_b, SuccessResult)
        assert write_b.data.get("unchanged") is not True
        assert upstream.upload_session_file_content.call_count >= 1

        close_cmd = UniversalFileCloseCommand()
        close_a = await close_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_a,
        )
        assert isinstance(close_a, SuccessResult)
        assert upstream.unlock_session_file.call_count == 1

    assert not layout_a.file_subtree_dir.exists()
    assert layout_b.file_subtree_dir.is_dir()
    assert layout_b.origin_path.is_file()
    assert session_dir.is_dir()

    _assert_c022_all_under_session_dir(
        workspace,
        session_dir,
        layout_b.file_subtree_dir,
        layout_b.origin_path,
    )

    unlock_call = upstream.unlock_session_file.call_args
    assert unlock_call.kwargs.get("file_path") == file_a or file_a in unlock_call.args
