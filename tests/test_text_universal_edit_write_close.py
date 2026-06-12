"""Text format universal_file_* write_mode preview/commit lifecycle.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    ensure_projectid_marker,
    layout_origin,
    make_workspace,
    mock_upstream,
    reset_ca_session,
    session_dir_for,
    upstream_context,
)

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"
_REL = "notes/sample.txt"
_INIT = b"line one\nline two\n"


@pytest.fixture(autouse=True)
def _reset_session() -> None:
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    yield
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)


async def _open_text(
    tmp: Path,
    rel: str = _REL,
    *,
    content: bytes = _INIT,
) -> tuple[str, Path, Path]:
    workspace = make_workspace(tmp)
    upstream = mock_upstream(origins={rel: content})
    with upstream_context(workspace=workspace, upstream=upstream):
        cmd = UniversalFileOpenCommand()
        res = await cmd.execute(
            session_id=DEFAULT_CA_SESSION_ID,
            project_id=_PROJECT_UUID,
            file_path=rel,
        )
    assert isinstance(res, SuccessResult)
    ensure_projectid_marker(
        session_dir_for(workspace, DEFAULT_CA_SESSION_ID, _PROJECT_UUID, rel),
        _PROJECT_UUID,
    )
    origin = layout_origin(workspace, DEFAULT_CA_SESSION_ID, _PROJECT_UUID, rel)
    return DEFAULT_CA_SESSION_ID, workspace, origin


@pytest.mark.asyncio
async def test_text_write_preview_does_not_touch_disk(tmp_path: Path) -> None:
    """write_mode=preview returns diff; origin stays unchanged while draft is edited."""
    rel = _REL
    sid, workspace, origin = await _open_text(tmp_path, rel)
    before = origin.read_text(encoding="utf-8")
    upstream = mock_upstream(origins={rel: _INIT})

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 1,
                            "end_line": 1,
                            "content": "line ONE\n",
                        }
                    ],
                }
            )
        )
        r1 = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        r2 = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )

    assert isinstance(r1, SuccessResult)
    assert r1.data.get("phase") == "preview"
    assert r1.data.get("has_changes") is True
    assert isinstance(r2, SuccessResult)
    assert r2.data.get("phase") == "preview"
    assert origin.read_text(encoding="utf-8") == before


@pytest.mark.asyncio
async def test_text_preview_commit_close_roundtrip(tmp_path: Path) -> None:
    rel = _REL
    sid, workspace, origin = await _open_text(tmp_path, rel)
    upstream = mock_upstream(origins={rel: _INIT})

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "line TWO\n",
                        }
                    ],
                }
            )
        )
        assert origin.read_text(encoding="utf-8") == "line one\nline two\n"
        commit_write = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
        assert origin.read_text(encoding="utf-8") == "line one\nline TWO\n"
        await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )

    assert isinstance(commit_write, SuccessResult)
    assert commit_write.data.get("uploaded") is True


@pytest.mark.asyncio
async def test_text_second_edit_after_preview_before_commit(tmp_path: Path) -> None:
    """Second line replace before commit applies to draft and uploads merged text."""
    rel = _REL
    sid, workspace, origin = await _open_text(tmp_path, rel)
    upstream = mock_upstream(origins={rel: _INIT})

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 1,
                            "end_line": 1,
                            "content": "first edit\n",
                        }
                    ],
                }
            )
        )
        assert origin.read_text(encoding="utf-8") == "line one\nline two\n"

        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "second edit\n",
                        }
                    ],
                }
            )
        )
        commit = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )

    assert isinstance(commit, SuccessResult)
    assert commit.data.get("uploaded") is True
    assert origin.read_text(encoding="utf-8") == "first edit\nsecond edit\n"


@pytest.mark.asyncio
async def test_text_edit_rejects_stale_line_number_after_prior_edit(
    tmp_path: Path,
) -> None:
    """Out-of-range start_line after a prior edit must fail, not corrupt the draft."""
    rel = _REL
    sid, workspace, origin = await _open_text(tmp_path, rel)
    upstream = mock_upstream(origins={rel: _INIT})

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        first = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "start_line": 1,
                            "content": "inserted\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(first, SuccessResult)
        assert first.data.get("line_count") == 3

        stale = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 10,
                            "end_line": 10,
                            "content": "wrong target\n",
                        }
                    ],
                }
            )
        )

    assert isinstance(stale, ErrorResult)
    assert stale.code == "LINE_OUT_OF_RANGE"
    assert origin.read_text(encoding="utf-8") == "line one\nline two\n"


@pytest.mark.asyncio
async def test_text_edit_anchor_mismatch_rejects_stale_coordinates(
    tmp_path: Path,
) -> None:
    rel = _REL
    sid, workspace, _origin = await _open_text(tmp_path, rel)
    upstream = mock_upstream(origins={rel: _INIT})

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        result = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "updated\n",
                            "anchor_head": "wrong",
                            "anchor_tail": "wrong",
                        }
                    ],
                }
            )
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "ANCHOR_MISMATCH"
