"""Acceptance: lock-before-transfer write lifecycle (R1-R6).

Covers the four lifecycle invariants and the new close semantics:

* R1 — open of a NEW file (create=true) issues zero CA calls.
* R2 — open of an EXISTING file acquires the lock then downloads.
* R3 — commit of a NEW file uses lock-then-transfer (upload_create_and_lock),
  never the update-existing path, so "file not found in project index" cannot
  occur for new files.
* R4 — close releases the CA lock only when the file exists on CA; an unwritten
  new file releases nothing.
* write_before_close — true writes then closes; false on a modified-unwritten
  file errors without closing; an unmodified file closes either way.
* R6 — the modified flag is set by a non-empty-diff edit and cleared by commit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
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
from ai_editor.commands.universal_file_edit.session import get_session
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


def _mock_upstream(*, origin_bytes: bytes = b"") -> MagicMock:
    """Build a CA client mock that echoes uploaded content back as accepted bytes."""
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.VALID
    upstream.lock_file_and_download.return_value = origin_bytes
    upstream.upload_session_file_content.side_effect = lambda **kwargs: kwargs[
        "content"
    ]
    upstream.upload_create_and_lock.side_effect = lambda **kwargs: kwargs["content"]
    upstream.unlock_session_file.return_value = True
    return upstream


@contextmanager
def _patch_context(*, workspace: Path, upstream: MagicMock) -> Iterator[None]:
    """Patch workspace-root resolution and CA client construction with mocks."""
    with ExitStack() as stack:
        for target in _RESOLVE_WORKSPACE_PATCHES:
            stack.enter_context(patch(target, return_value=workspace))
        for target in _GET_CA_CLIENT_PATCHES:
            stack.enter_context(patch(target, return_value=upstream))
        yield


def _make_workspace(tmp_path: Path) -> Path:
    """Create a workspace dir with a projectid marker for project-root resolution."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "projectid").write_text('{"id": "p1"}\n', encoding="utf-8")
    return workspace


@pytest.mark.asyncio
async def test_r1_open_new_file_issues_zero_ca_calls(tmp_path: Path) -> None:
    """R1: open(create=true) performs no CA call and marks the file unpersisted."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r1", "p1", "new_r1.txt"
    upstream = _mock_upstream()

    with _patch_context(workspace=workspace, upstream=upstream):
        open_res = await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            create=True,
            initial_content="hello\n",
        )
        assert isinstance(open_res, SuccessResult)
        assert open_res.data.get("created") is True

        # Zero CA round-trips of any kind for a new-file open.
        assert upstream.mock_calls == []

        session = get_session(sid, file_path)
        assert session.persisted_on_ca is False
        assert session.modified is False

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        assert layout.origin_path.read_bytes() == b"hello\n"


@pytest.mark.asyncio
async def test_r2_open_existing_locks_then_downloads(tmp_path: Path) -> None:
    """R2: open(create=false) acquires the lock and downloads via lock_file_and_download."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r2", "p1", "existing_r2.txt"
    upstream = _mock_upstream(origin_bytes=b"on disk\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        open_res = await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(open_res, SuccessResult)
        upstream.lock_file_and_download.assert_called_once_with(
            sid, project_id, file_path
        )
        session = get_session(sid, file_path)
        assert session.persisted_on_ca is True

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        assert layout.origin_path.read_bytes() == b"on disk\n"


@pytest.mark.asyncio
async def test_r3_commit_new_file_uses_lock_then_transfer(tmp_path: Path) -> None:
    """R3: committing a new file calls upload_create_and_lock, not the update path."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r3", "p1", "new_r3.txt"
    upstream = _mock_upstream()

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            create=True,
            initial_content="seed\n",
        )
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {"type": "replace", "start_line": 1, "end_line": 1, "content": "body\n"}
            ],
        )
        commit_res = await UniversalFileWriteCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_mode="commit",
        )
        assert isinstance(commit_res, SuccessResult)
        assert commit_res.data.get("uploaded") is True
        # Lock-then-transfer path only; never the update-existing path.
        upstream.upload_create_and_lock.assert_called_once()
        assert upstream.upload_session_file_content.call_count == 0
        create_call = upstream.upload_create_and_lock.call_args
        assert create_call.kwargs["session_id"] == sid
        assert create_call.kwargs["project_id"] == project_id
        assert create_call.kwargs["file_path"] == file_path
        assert create_call.kwargs["content"] == b"body\n"

        session = get_session(sid, file_path)
        assert session.persisted_on_ca is True
        assert session.modified is False


@pytest.mark.asyncio
async def test_r3_commit_new_file_without_edits_still_persists(tmp_path: Path) -> None:
    """R3: a new file with no edits is still persisted on commit (no skip-on-equal)."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r3b", "p1", "new_r3b.txt"
    upstream = _mock_upstream()

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            create=True,
            initial_content="seed only\n",
        )
        commit_res = await UniversalFileWriteCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_mode="commit",
        )
        assert isinstance(commit_res, SuccessResult)
        assert commit_res.data.get("uploaded") is True
        upstream.upload_create_and_lock.assert_called_once()
        assert get_session(sid, file_path).persisted_on_ca is True


@pytest.mark.asyncio
async def test_r4_close_existing_releases_lock(tmp_path: Path) -> None:
    """R4: closing a persisted file releases the CA lock."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r4a", "p1", "existing_r4.txt"
    upstream = _mock_upstream(origin_bytes=b"data\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(close_res, SuccessResult)
        upstream.unlock_session_file.assert_called_once_with(
            session_id=sid, project_id=project_id, file_path=file_path
        )
        assert close_res.data.get("unlock_ok") is True


@pytest.mark.asyncio
async def test_r4_close_unwritten_new_file_releases_nothing(tmp_path: Path) -> None:
    """R4: closing an unwritten new file releases no CA lock and discards the draft."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-r4b", "p1", "new_r4.txt"
    upstream = _mock_upstream()

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            create=True,
            initial_content="draft\n",
        )
        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        assert layout.file_subtree_dir.is_dir()

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        assert isinstance(close_res, SuccessResult)
        assert upstream.unlock_session_file.call_count == 0
        assert close_res.data.get("unlock_ok") is False
        assert not layout.file_subtree_dir.exists()


@pytest.mark.asyncio
async def test_modified_flag_set_on_edit_cleared_on_commit(tmp_path: Path) -> None:
    """R6: a non-empty-diff edit sets modified; a successful commit clears it."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-mod", "p1", "mod.txt"
    upstream = _mock_upstream(origin_bytes=b"first\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        session = get_session(sid, file_path)
        assert session.modified is False

        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "second\n",
                }
            ],
        )
        assert session.modified is True

        await UniversalFileWriteCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_mode="commit",
        )
        assert session.modified is False


@pytest.mark.asyncio
async def test_modified_flag_unchanged_by_noop_edit(tmp_path: Path) -> None:
    """R6: an edit that produces no diff leaves the modified flag as it was."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-noop", "p1", "noop.txt"
    upstream = _mock_upstream(origin_bytes=b"same line\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        session = get_session(sid, file_path)
        # Replace line 1 with identical content: no byte change in the draft.
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "same line\n",
                }
            ],
        )
        assert session.modified is False


@pytest.mark.asyncio
async def test_write_before_close_true_writes_then_closes(tmp_path: Path) -> None:
    """write_before_close=true commits the modified file before closing."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-wbc-t", "p1", "wbc_true.txt"
    upstream = _mock_upstream(origin_bytes=b"old\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {"type": "replace", "start_line": 1, "end_line": 1, "content": "new\n"}
            ],
        )
        layout = file_workspace_layout(workspace, sid, project_id, file_path)

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_before_close=True,
        )
        assert isinstance(close_res, SuccessResult)
        assert upstream.upload_session_file_content.call_count == 1
        upstream.unlock_session_file.assert_called_once()
        assert not layout.file_subtree_dir.exists()


@pytest.mark.asyncio
async def test_write_before_close_false_modified_errors_without_closing(
    tmp_path: Path,
) -> None:
    """write_before_close=false on a modified file errors and does not close."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-wbc-f", "p1", "wbc_false.txt"
    upstream = _mock_upstream(origin_bytes=b"keep\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {"type": "replace", "start_line": 1, "end_line": 1, "content": "edit\n"}
            ],
        )
        layout = file_workspace_layout(workspace, sid, project_id, file_path)

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_before_close=False,
        )
        assert isinstance(close_res, ErrorResult)
        assert close_res.code == "MODIFIED_NOT_WRITTEN"
        # Not closed: no upload, no unlock, workspace intact, session still open.
        assert upstream.upload_session_file_content.call_count == 0
        assert upstream.unlock_session_file.call_count == 0
        assert layout.file_subtree_dir.is_dir()
        assert get_session(sid, file_path).modified is True


@pytest.mark.asyncio
async def test_reverted_modified_draft_closes_as_noop_without_upload(
    tmp_path: Path,
) -> None:
    """A draft edited back to canonical origin closes without write/validation."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-reverted-noop", "p1", "reverted_noop.txt"
    upstream = _mock_upstream(origin_bytes=b"origin\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {"type": "replace", "start_line": 1, "end_line": 1, "content": "edit\n"}
            ],
        )
        await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "origin\n",
                }
            ],
        )
        session = get_session(sid, file_path)
        assert session.modified is True

        layout = file_workspace_layout(workspace, sid, project_id, file_path)
        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_before_close=False,
        )

        assert isinstance(close_res, SuccessResult)
        assert upstream.upload_session_file_content.call_count == 0
        upstream.unlock_session_file.assert_called_once()
        assert not layout.file_subtree_dir.exists()


@pytest.mark.asyncio
async def test_write_before_close_false_unmodified_closes(tmp_path: Path) -> None:
    """An unmodified file closes normally regardless of write_before_close."""
    workspace = _make_workspace(tmp_path)
    sid, project_id, file_path = "ca-wbc-u", "p1", "wbc_unmod.txt"
    upstream = _mock_upstream(origin_bytes=b"unchanged\n")

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
        layout = file_workspace_layout(workspace, sid, project_id, file_path)

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
            write_before_close=False,
        )
        assert isinstance(close_res, SuccessResult)
        assert upstream.upload_session_file_content.call_count == 0
        upstream.unlock_session_file.assert_called_once()
        assert not layout.file_subtree_dir.exists()
