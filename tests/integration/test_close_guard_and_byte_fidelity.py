"""Regression: close never discards edits, preserves bytes, validates parameters.

Three defects measured on the deployed server, each covered here on the real
command path (only the Code Analysis transport and the workspace root are
mocked; the session, draft, format-group and export machinery are the real
ones):

* ``universal_file_close`` returned success and destroyed a confirmed edit
  whenever the session was tree-temp or an uncommitted ``create=true`` draft.
  The documented ``MODIFIED_NOT_WRITTEN`` never fired for those.
* A CRLF file, a file with no final newline and a file with mixed endings were
  rewritten to LF by an open/commit round trip with ZERO edit operations, and
  the server reported ``has_changes: true`` for it.
* ``close`` accepted an empty ``project_id`` (declared required) and an empty
  ``file_path``, tearing the session down anyway.

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

PY_SOURCE = (
    '"""Probe module."""\n\n\ndef probe() -> int:\n'
    '    """Return one.\n\n    Returns:\n        int: one.\n    """\n    return 1\n'
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


async def _open_edit(
    sid: str,
    file_path: str,
    initial: str,
    operations: list,
) -> None:
    """Open a new file with create=true and apply one real edit batch."""
    await UniversalFileOpenCommand().execute(
        session_id=sid,
        project_id="p1",
        file_path=file_path,
        create=True,
        initial_content=initial,
    )
    result = await UniversalFileEditCommand().execute(
        session_id=sid,
        project_id="p1",
        file_path=file_path,
        operations=operations,
    )
    assert isinstance(result, SuccessResult), getattr(result, "message", result)


@pytest.mark.asyncio
async def test_uncommitted_new_text_draft_close_is_refused(tmp_path: Path) -> None:
    """An edited create=true draft is refused, not silently discarded."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream()
    sid, rel = "ca-new-mod", "new_modified.txt"

    with _patch_context(workspace=workspace, upstream=upstream):
        await _open_edit(
            sid,
            rel,
            "alpha\n",
            [{"type": "replace", "start_line": 1, "end_line": 1, "content": "beta\n"}],
        )
        assert get_session(sid, rel).modified is True

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        assert isinstance(close_res, ErrorResult)
        assert close_res.code == "MODIFIED_NOT_WRITTEN"
        # Still open, still holding the edit: nothing was discarded.
        assert get_session(sid, rel).modified is True
        assert upstream.upload_create_and_lock.call_count == 0


@pytest.mark.asyncio
async def test_uncommitted_new_draft_write_before_close_commits(
    tmp_path: Path,
) -> None:
    """The declared escape still works: write_before_close=true commits, then closes."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream()
    sid, rel = "ca-new-wbc", "new_wbc.txt"

    with _patch_context(workspace=workspace, upstream=upstream):
        await _open_edit(
            sid,
            rel,
            "alpha\n",
            [{"type": "replace", "start_line": 1, "end_line": 1, "content": "beta\n"}],
        )
        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1", file_path=rel, write_before_close=True
        )
        assert isinstance(close_res, SuccessResult), getattr(close_res, "message", "")
        # The edit reached CA through the new-file lock-then-transfer path.
        assert upstream.upload_create_and_lock.call_count == 1
        assert upstream.upload_create_and_lock.call_args.kwargs["content"] == b"beta\n"


@pytest.mark.asyncio
async def test_tree_temp_modified_close_is_refused(tmp_path: Path) -> None:
    """Tree-temp sessions lost their carve-out: an edited YAML draft is refused."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream(origin_bytes=b"a: 1\nb: 2\n")
    sid, rel = "ca-tt-mod", "records.yaml"

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        result = await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id="p1",
            file_path=rel,
            operations=[{"type": "replace", "json_pointer": "/a", "value": 99}],
        )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)
        assert get_session(sid, rel).modified is True

        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        assert isinstance(close_res, ErrorResult)
        assert close_res.code == "MODIFIED_NOT_WRITTEN"
        assert get_session(sid, rel).modified is True


@pytest.mark.asyncio
async def test_unmodified_session_still_closes(tmp_path: Path) -> None:
    """A session with no edits closes normally, exactly as before."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream(origin_bytes=b"a: 1\n")
    sid, rel = "ca-clean", "clean.yaml"

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        assert isinstance(close_res, SuccessResult), getattr(close_res, "message", "")
        assert close_res.data["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rel", "origin"),
    [
        ("crlf.txt", b"alpha\r\nbeta\r\ngamma\r\n"),
        ("mixed.txt", b"alpha\r\nbeta\ngamma\r\n"),
        ("nonl.txt", b"alpha\nbeta"),
        ("crlf.yaml", b"a: 1\r\nb: 2\r\n"),
        ("crlf.json", b'{\r\n  "a": 1\r\n}\r\n'),
        ("crlf.py", PY_SOURCE.replace("\n", "\r\n").encode()),
        ("nonl.py", PY_SOURCE.rstrip("\n").encode()),
    ],
)
async def test_zero_edit_commit_is_byte_identical(
    tmp_path: Path, rel: str, origin: bytes
) -> None:
    """Open and commit with ZERO edits must upload the origin bytes verbatim."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream(origin_bytes=origin)
    sid = f"ca-bytes-{rel}"

    with _patch_context(workspace=workspace, upstream=upstream):
        opened = await UniversalFileOpenCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        assert isinstance(opened, SuccessResult), getattr(opened, "message", opened)

        write_res = await UniversalFileWriteCommand().execute(
            session_id=sid, project_id="p1", file_path=rel, write_mode="commit"
        )
        assert isinstance(write_res, SuccessResult), getattr(write_res, "message", "")
        # The caller changed nothing, so the server must not claim it did.
        assert write_res.data["has_changes"] is False
        assert write_res.data["unchanged"] is True
        # And nothing was pushed to CA for a no-op round trip.
        assert upstream.upload_session_file_content.call_count == 0


@pytest.mark.asyncio
async def test_edit_on_crlf_file_still_commits_the_edit(tmp_path: Path) -> None:
    """The fidelity guard must never swallow a real edit."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream(origin_bytes=b"alpha\r\nbeta\r\n")
    sid, rel = "ca-crlf-edit", "edited.txt"

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        result = await UniversalFileEditCommand().execute(
            session_id=sid,
            project_id="p1",
            file_path=rel,
            operations=[
                {"type": "replace", "start_line": 1, "end_line": 1, "content": "ALPHA\n"}
            ],
        )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)

        write_res = await UniversalFileWriteCommand().execute(
            session_id=sid, project_id="p1", file_path=rel, write_mode="commit"
        )
        assert isinstance(write_res, SuccessResult), getattr(write_res, "message", "")
        assert write_res.data["has_changes"] is True
        uploaded = upstream.upload_session_file_content.call_args.kwargs["content"]
        assert b"ALPHA" in uploaded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [{"project_id": ""}, {"file_path": ""}],
)
async def test_close_rejects_empty_declared_parameters(
    tmp_path: Path, override: dict
) -> None:
    """An empty project_id or file_path is a VALIDATION_ERROR, not a free close."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream()
    sid, rel = f"ca-empty-{next(iter(override))}", "empty_param.txt"

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id="p1",
            file_path=rel,
            create=True,
            initial_content="alpha\n",
        )
        params = {"session_id": sid, "project_id": "p1", **override}
        close_res = await UniversalFileCloseCommand().execute(**params)
        assert isinstance(close_res, ErrorResult)
        assert close_res.code == "VALIDATION_ERROR"
        # The session survived the rejected call.
        assert get_session(sid, rel) is not None

        ok = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1", file_path=rel
        )
        assert isinstance(ok, SuccessResult)


@pytest.mark.asyncio
async def test_close_without_file_path_still_resolves_single_file(
    tmp_path: Path,
) -> None:
    """Omitting file_path entirely remains the supported single-file form."""
    workspace = _make_workspace(tmp_path)
    upstream = _mock_upstream()
    sid, rel = "ca-omit-fp", "omit.txt"

    with _patch_context(workspace=workspace, upstream=upstream):
        await UniversalFileOpenCommand().execute(
            session_id=sid,
            project_id="p1",
            file_path=rel,
            create=True,
            initial_content="alpha\n",
        )
        close_res = await UniversalFileCloseCommand().execute(
            session_id=sid, project_id="p1"
        )
        assert isinstance(close_res, SuccessResult), getattr(close_res, "message", "")
        assert close_res.data["closed_file_path"] == rel
