"""Acceptance: Edit Subdirectory + Edit Stage (C-008, C-011, C-022-2).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.commands.universal_file_preview_command import (
    UniversalFilePreviewCommand,
)
from ai_editor.core.editor_workspace_paths import file_workspace_layout
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus

_SESSION_ID = "ca-edit-stage"
_FILE_PATH = "notes.txt"

_PATCH_TARGETS = (
    "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
    "ai_editor.core.upstream.code_analysis_client.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.open_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.open_command_runtime.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.open_command_runtime.resolve_workspace_root",
    "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_preview_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mock_upstream(*, origin_bytes: bytes) -> MagicMock:
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.VALID
    upstream.lock_file_and_download.return_value = origin_bytes
    return upstream


def _prepare_workspace(workspace: Path, project_id: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "projectid").write_text(
        f'{{"id": "{project_id}"}}\n',
        encoding="utf-8",
    )


@contextmanager
def _open_context(*, workspace: Path, upstream: MagicMock):
    with patch(
        _PATCH_TARGETS[0],
        return_value=workspace,
    ), patch(
        _PATCH_TARGETS[1],
        return_value=upstream,
    ), patch(
        _PATCH_TARGETS[2],
        return_value=upstream,
    ), patch(
        _PATCH_TARGETS[3],
        return_value=upstream,
    ), patch(
        _PATCH_TARGETS[4],
        return_value=workspace,
    ), patch(
        _PATCH_TARGETS[5],
        return_value=upstream,
    ), patch(
        _PATCH_TARGETS[6],
        return_value=upstream,
    ), patch(
        _PATCH_TARGETS[7],
        return_value=upstream,
    ):
        yield


@pytest.fixture(autouse=True)
def _reset_ca_session() -> None:
    release_session(_SESSION_ID, _FILE_PATH)
    yield
    release_session(_SESSION_ID, _FILE_PATH)


@pytest.mark.asyncio
async def test_open_creates_edit_subdirectory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = _SESSION_ID
    project_id = "p1"
    file_path = _FILE_PATH
    origin_bytes = b"hello world\n"

    _prepare_workspace(workspace, project_id)
    upstream = _mock_upstream(origin_bytes=origin_bytes)
    with _open_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )

    assert isinstance(open_res, SuccessResult)
    layout = file_workspace_layout(workspace, sid, project_id, file_path)
    assert layout.origin_path.is_file()
    assert layout.origin_path.read_bytes() == origin_bytes

    draft_path = Path(open_res.data["draft_path"])
    assert draft_path.is_file()

    edit_subdir = draft_path.parent
    assert edit_subdir.is_dir()
    assert edit_subdir.is_relative_to(layout.file_subtree_dir)
    assert edit_subdir != layout.origin_path
    assert draft_path.name == layout.origin_path.name == "notes.txt"
    assert edit_subdir.name == "notes.txt-edit"
    assert str(workspace / sid) in open_res.data["session_dir"]
    upstream.lock_file_and_download.assert_called_once()


@pytest.mark.asyncio
async def test_edit_stage_mutates_edit_subdir_not_origin(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = _SESSION_ID
    project_id = "p1"
    file_path = _FILE_PATH
    origin_bytes = b"hello world\n"

    _prepare_workspace(workspace, project_id)
    upstream = _mock_upstream(origin_bytes=origin_bytes)
    with _open_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        origin_hash_before = _sha256(layout.origin_path)
        draft_path = Path(open_res.data["draft_path"])
        draft_hash_before = _sha256(draft_path)

        edit_cmd = UniversalFileEditCommand()
        edit_res = await edit_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "hello edited\n",
                }
            ],
        )

    assert isinstance(edit_res, SuccessResult)
    assert _sha256(layout.origin_path) == origin_hash_before
    assert layout.origin_path.read_bytes() == origin_bytes
    assert _sha256(draft_path) != draft_hash_before
    assert draft_path.read_text(encoding="utf-8") == "hello edited\n"
    assert draft_path.parent.is_dir()
    assert draft_path.parent.name.startswith("notes.txt-")


@pytest.mark.asyncio
async def test_preview_read_only_does_not_mutate_origin(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = _SESSION_ID
    project_id = "p1"
    file_path = _FILE_PATH
    origin_bytes = b"hello world\n"

    _prepare_workspace(workspace, project_id)
    upstream = _mock_upstream(origin_bytes=origin_bytes)
    with _open_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        origin_hash_before = _sha256(layout.origin_path)

        preview_cmd = UniversalFilePreviewCommand()
        preview_res = await preview_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )

    assert isinstance(preview_res, SuccessResult)
    assert _sha256(layout.origin_path) == origin_hash_before
    assert layout.origin_path.read_bytes() == origin_bytes


@pytest.mark.asyncio
async def test_duplicate_open_same_session_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sid = _SESSION_ID
    project_id = "p1"
    file_path = _FILE_PATH
    origin_bytes = b"hello world\n"

    _prepare_workspace(workspace, project_id)
    upstream = _mock_upstream(origin_bytes=origin_bytes)
    with _open_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        first = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(first, SuccessResult)
        second = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )

    assert isinstance(second, ErrorResult)
    assert second.code == "FILE_ALREADY_OPEN"
    assert upstream.lock_file_and_download.call_count == 1
