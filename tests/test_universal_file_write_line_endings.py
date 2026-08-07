"""Line-ending fidelity through the REAL open/edit/write commands (C-012).

Only the Code Analysis transport is mocked; every command below is the real one,
so these tests pin what the editor actually hands to the upload: an edited CRLF
file must reach the upstream as CRLF, and a file with no trailing newline must
not gain one.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    commit_write,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_REL = "notes/endings.txt"
_BETA_OP = {"type": "replace", "start_line": 2, "end_line": 2, "content": "BETA"}


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    yield
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)


def _uploaded_bytes(upstream: MagicMock) -> bytes:
    """The exact bytes the write command handed to Code Analysis."""
    call = upstream.upload_session_file_content.call_args
    assert call is not None, "no upload reached the upstream"
    return call.kwargs["content"]


async def _edit_and_commit(
    tmp_path: Path,
    source: bytes,
    operations: list[dict],
) -> tuple[bytes, SuccessResult]:
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=_REL,
        content=source,
    )
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        result = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": operations,
                }
            )
        )
    assert isinstance(result, SuccessResult), result
    written = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=_REL,
    )
    assert isinstance(written, SuccessResult), written
    return _uploaded_bytes(upstream), written


@pytest.mark.asyncio
async def test_edited_crlf_file_commits_as_crlf(tmp_path: Path) -> None:
    uploaded, written = await _edit_and_commit(
        tmp_path, b"alpha\r\nbeta\r\ngamma\r\n", [_BETA_OP]
    )

    assert uploaded == b"alpha\r\nBETA\r\ngamma\r\n"
    assert written.data["has_changes"] is True


@pytest.mark.asyncio
async def test_edited_lf_file_stays_lf(tmp_path: Path) -> None:
    uploaded, _written = await _edit_and_commit(
        tmp_path, b"alpha\nbeta\ngamma\n", [_BETA_OP]
    )

    assert uploaded == b"alpha\nBETA\ngamma\n"


@pytest.mark.asyncio
async def test_edited_file_without_trailing_newline_does_not_gain_one(
    tmp_path: Path,
) -> None:
    uploaded, _written = await _edit_and_commit(
        tmp_path, b"alpha\nbeta\nno trailing newline", [_BETA_OP]
    )

    assert uploaded == b"alpha\nBETA\nno trailing newline"


@pytest.mark.asyncio
async def test_edited_crlf_file_without_trailing_newline_keeps_both(
    tmp_path: Path,
) -> None:
    uploaded, _written = await _edit_and_commit(
        tmp_path, b"alpha\r\nbeta\r\nno trailing newline", [_BETA_OP]
    )

    assert uploaded == b"alpha\r\nBETA\r\nno trailing newline"


@pytest.mark.asyncio
async def test_mixed_endings_keep_untouched_lines_verbatim(tmp_path: Path) -> None:
    """Documented decision: untouched lines keep their own terminator, the
    rewritten line takes the file's dominant style."""
    uploaded, _written = await _edit_and_commit(
        tmp_path, b"alpha\r\nbeta\ngamma\r\ndelta\r\n", [_BETA_OP]
    )

    assert uploaded == b"alpha\r\nBETA\r\ngamma\r\ndelta\r\n"


@pytest.mark.asyncio
async def test_inserted_line_takes_the_dominant_style(tmp_path: Path) -> None:
    uploaded, _written = await _edit_and_commit(
        tmp_path,
        b"alpha\r\nbeta\r\ngamma\r\n",
        [{"type": "insert", "position": "last", "content": "delta"}],
    )

    assert uploaded == b"alpha\r\nbeta\r\ngamma\r\ndelta\r\n"


@pytest.mark.asyncio
async def test_created_crlf_draft_commits_as_crlf(tmp_path: Path) -> None:
    """The ``create=true`` path takes ``upload_create_and_lock``; it owes the
    same fidelity, edited or not (this is the pipeline live-write fixture)."""
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=_REL,
        content=b"",
        create=True,
        initial_content="alpha\r\nbeta\r\ngamma\r\n",
    )
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edited = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [_BETA_OP],
                }
            )
        )
    assert isinstance(edited, SuccessResult), edited
    written = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=_REL,
    )
    assert isinstance(written, SuccessResult), written
    create_call = upstream.upload_create_and_lock.call_args
    assert create_call is not None, "no create upload reached the upstream"
    assert create_call.kwargs["content"] == b"alpha\r\nBETA\r\ngamma\r\n"
