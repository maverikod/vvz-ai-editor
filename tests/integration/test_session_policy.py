"""Session policy integration: lock contention, broken CA session, zombie cleanup (C-015, C-022).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.core.editor_workspace_paths import file_workspace_layout
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)
from ai_editor.core.workspace_session_cleanup import cleanup_zombie_ca_session

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
    for sid in ("ca-lock-a", "ca-lock-b", "ca-broken", "ca-zombie"):
        release_session(sid, "policy.txt")
    yield
    for sid in ("ca-lock-a", "ca-lock-b", "ca-broken", "ca-zombie"):
        release_session(sid, "policy.txt")


@pytest.mark.asyncio
async def test_lock_contention_second_ca_session_cannot_open_same_file(
    tmp_path: Path,
) -> None:
    """C-022(5): second CA session gets upstream lock error; no workspace for it."""
    workspace = tmp_path / "workspace"
    sid_a = "ca-lock-a"
    sid_b = "ca-lock-b"
    project_a = "proj-a"
    project_b = "proj-b"
    file_path = "policy.txt"
    origin_bytes = b"locked content\n"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = _mock_upstream(origin_bytes=origin_bytes)

    def _lock(session_id: str, project_id: str, file_path: str) -> bytes:
        if session_id == sid_b:
            raise RuntimeError("FILE_LOCKED: held by another CA session")
        return origin_bytes

    upstream.lock_file_and_download.side_effect = _lock

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_a = await open_cmd.execute(
            session_id=sid_a,
            project_id=project_a,
            file_path=file_path,
        )
        assert isinstance(open_a, SuccessResult)

        open_b = await open_cmd.execute(
            session_id=sid_b,
            project_id=project_b,
            file_path=file_path,
        )
        assert isinstance(open_b, ErrorResult)
        assert open_b.code == "OPEN_ERROR"
        assert "FILE_LOCKED" in open_b.message

    layout_a = file_workspace_layout(workspace, sid_a, project_a, file_path)
    layout_b = file_workspace_layout(workspace, sid_b, project_b, file_path)

    assert layout_a.session_dir.is_dir()
    assert layout_a.origin_path.is_file()
    assert not layout_b.session_dir.exists()
    assert upstream.lock_file_and_download.call_count == 2


@pytest.mark.asyncio
async def test_broken_ca_session_open_rejected(tmp_path: Path) -> None:
    """C-015: OPEN with NOT_FOUND CA session is rejected before upstream lock."""
    workspace = tmp_path / "workspace"
    sid = "ca-broken"
    project_id = "proj"
    file_path = "policy.txt"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        result = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "SESSION_NOT_FOUND"
    upstream.lock_file_and_download.assert_not_called()
    assert not (workspace / sid).exists()


def test_session_guard_rejects_broken_open() -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)
    assert guard.check(OperationKind.OPEN, "broken-open") == GuardDecision.REJECT
    client.validate_ca_session.assert_called_once_with("broken-open")


@pytest.mark.asyncio
async def test_broken_ca_session_edit_rejected_after_open(tmp_path: Path) -> None:
    """C-015: edit is rejected when CA session becomes NOT_FOUND after successful open."""
    workspace = tmp_path / "workspace"
    sid = "ca-broken"
    project_id = "proj"
    file_path = "policy.txt"
    origin_bytes = b"editable line\n"
    phase = "open"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = _mock_upstream(origin_bytes=origin_bytes)

    def _validate(session_id: str) -> CaSessionStatus:
        if phase == "open":
            return CaSessionStatus.VALID
        return CaSessionStatus.NOT_FOUND

    upstream.validate_ca_session.side_effect = _validate

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        assert layout.session_dir.is_dir()

        phase = "edit"
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
                    "content": "edited line\n",
                }
            ],
        )

    assert isinstance(edit_res, ErrorResult)
    assert edit_res.code == "SESSION_NOT_FOUND"
    assert layout.session_dir.is_dir()


@pytest.mark.asyncio
async def test_broken_ca_session_close_cleans_workspace(tmp_path: Path) -> None:
    """C-015/C-022: guard cleanup on NOT_FOUND close removes workspace (close may error)."""
    workspace = tmp_path / "workspace"
    sid = "ca-broken"
    project_id = "proj"
    file_path = "policy.txt"
    origin_bytes = b"close me\n"
    phase = "open"

    workspace.mkdir(parents=True, exist_ok=True)
    upstream = _mock_upstream(origin_bytes=origin_bytes)

    def _validate(session_id: str) -> CaSessionStatus:
        if phase == "open":
            return CaSessionStatus.VALID
        return CaSessionStatus.NOT_FOUND

    upstream.validate_ca_session.side_effect = _validate

    with _upstream_context(workspace=workspace, upstream=upstream):
        open_cmd = UniversalFileOpenCommand()
        open_res = await open_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        _ensure_projectid_marker(layout.session_dir, project_id)
        assert layout.session_dir.is_dir()
        assert layout.file_subtree_dir.is_dir()

        phase = "close"
        close_cmd = UniversalFileCloseCommand()
        close_res = await close_cmd.execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )

    assert isinstance(close_res, ErrorResult)
    assert close_res.code == "SESSION_NOT_FOUND"
    assert not layout.session_dir.exists()
    assert not layout.file_subtree_dir.exists()
    upstream.unlock_session_file.assert_not_called()


def test_zombie_workspace_cleanup_integration(tmp_path: Path) -> None:
    """C-025: orphan session dir under workspace root is removed by cleanup helper."""
    root = tmp_path / "workspace"
    sid = "ca-zombie"
    session_dir = root / sid
    session_dir.mkdir(parents=True)
    marker = session_dir / "orphan.txt"
    marker.write_text("orphan workspace", encoding="utf-8")

    assert cleanup_zombie_ca_session(sid, workspace_root=root) is True
    assert not session_dir.exists()
    assert not marker.exists()


def test_session_guard_triggers_zombie_cleanup_on_terminating_write(
    tmp_path: Path,
) -> None:
    """C-024/C-025: guard delegates NOT_FOUND terminating ops to real cleanup."""
    root = tmp_path / "workspace"
    sid = "ca-zombie"
    session_dir = root / sid
    session_dir.mkdir(parents=True)
    (session_dir / "stale.txt").write_text("stale", encoding="utf-8")

    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)

    decision = guard.check(OperationKind.WRITE, sid, workspace_root=root)

    assert decision == GuardDecision.ALLOW_TERMINATING
    assert not session_dir.exists()
    client.validate_ca_session.assert_called_once_with(sid)
