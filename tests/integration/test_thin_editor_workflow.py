"""Acceptance: full open → write no-op → edit → write upload → close (C-022).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.core.editor_workspace_paths import file_workspace_layout
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus

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


def _mock_upstream(*, origin_bytes: bytes) -> MagicMock:
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.VALID
    upstream.lock_file_and_download.return_value = origin_bytes
    upstream.upload_session_file_content.side_effect = lambda **kwargs: kwargs[
        "content"
    ]
    upstream.unlock_session_file.return_value = True
    return upstream


@contextmanager
def _patch_context(*, workspace: Path, upstream: MagicMock):
    with ExitStack() as stack:
        for target in _RESOLVE_WORKSPACE_PATCHES:
            stack.enter_context(
                patch(target, return_value=workspace),
            )
        for target in _GET_CA_CLIENT_PATCHES:
            stack.enter_context(
                patch(target, return_value=upstream),
            )
        yield


@pytest.mark.asyncio
async def test_full_workflow_open_edit_write_close_mock_upstream(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sid = "ca-flow"
    project_id = "p1"
    file_path = "flow.txt"
    origin_bytes = b"line one\n"
    edited_text = "line edited\n"
    edited_bytes = edited_text.encode("utf-8")

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "projectid").write_text('{"id": "p1"}\n', encoding="utf-8")

    upstream = _mock_upstream(origin_bytes=origin_bytes)

    with _patch_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)
        assert open_res.data["session_id"] == sid
        assert str(workspace / sid) in open_res.data["session_dir"]

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        assert layout.origin_path.is_file()
        assert layout.origin_path.read_bytes() == origin_bytes

        draft_path = Path(open_res.data["draft_path"])
        assert draft_path.is_file()
        assert draft_path.read_bytes() == origin_bytes
        upstream.lock_file_and_download.assert_called_once()

        write_cmd = UniversalFileWriteCommand()
        noop_res = await write_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_mode="commit",
        )
        assert isinstance(noop_res, SuccessResult)
        assert noop_res.data.get("unchanged") is True
        assert noop_res.data.get("uploaded") is False
        assert upstream.upload_session_file_content.call_count == 0
        assert layout.origin_path.read_bytes() == origin_bytes

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
                    "content": edited_text,
                }
            ],
        )
        assert isinstance(edit_res, SuccessResult)
        assert draft_path.read_text(encoding="utf-8") == edited_text
        assert layout.origin_path.read_bytes() == origin_bytes

        upload_res = await write_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_mode="commit",
        )
        assert isinstance(upload_res, SuccessResult)
        assert upload_res.data.get("unchanged") is False
        assert upload_res.data.get("uploaded") is True
        assert upstream.upload_session_file_content.call_count == 1
        upload_call = upstream.upload_session_file_content.call_args
        assert upload_call.kwargs["session_id"] == sid
        assert upload_call.kwargs["project_id"] == project_id
        assert upload_call.kwargs["file_path"] == file_path
        assert upload_call.kwargs["content"] == edited_bytes
        assert layout.origin_path.read_bytes() == edited_bytes

        assert layout.file_subtree_dir.is_dir()
        assert layout.session_dir.is_dir()

        close_cmd = UniversalFileCloseCommand()
        close_res = await close_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(close_res, SuccessResult)
        assert upstream.unlock_session_file.call_count == 1
        unlock_call = upstream.unlock_session_file.call_args
        assert unlock_call.kwargs["session_id"] == sid
        assert unlock_call.kwargs["project_id"] == project_id
        assert unlock_call.kwargs["file_path"] == file_path
        assert close_res.data.get("workspace_subtree_removed") is True
        assert not layout.file_subtree_dir.exists()
        assert not layout.session_dir.exists()
