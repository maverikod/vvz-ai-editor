"""``universal_file_write`` must answer in the shape its ``metadata()`` documents.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``metadata()["return_value"]["success"]["data"]`` promises ``uploaded``,
``format_python``, ``session_id``, ``project_id`` and ``file_path`` on EVERY
successful write. The commit path carried them; the preview path -- explicit
``write_mode="preview"``, ``write_mode`` omitted, and the sidecar first call --
returned only ``success``/``phase``/``write_mode``/``has_changes``/
``unchanged``/``diff``, so 23 live assertions of ``pipeline live-write`` failed
on the deployed 1.0.92.

The documented key list is read from ``metadata()`` here rather than repeated,
so the promise and the check cannot drift apart. ``ca_verify`` is excluded: it
is documented as conditional on ``verify_after_upload`` and an upload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    WriteComparison,
)
from ai_editor.core.upstream.session_guard import GuardDecision

PROJECT_ID = "proj-1"
SESSION_ID = "sess-1"
FILE_PATH = "src/foo.py"

# Documented but conditional: it appears only when verify_after_upload uploaded.
CONDITIONAL_KEYS = {"ca_verify"}
# Types the live contract check asserts for the always-present properties.
DOCUMENTED_TYPES: Dict[str, type] = {
    "phase": str,
    "write_mode": str,
    "has_changes": bool,
    "unchanged": bool,
    "uploaded": bool,
    "diff": str,
    "format_python": bool,
    "session_id": str,
    "project_id": str,
    "file_path": str,
}


def documented_keys() -> set:
    """The always-present ``data`` properties, straight from ``metadata()``."""
    data = UniversalFileWriteCommand.metadata()["return_value"]["success"]["data"]
    return set(data) - CONDITIONAL_KEYS


def assert_documented_shape(result: Any, **expected: Any) -> Mapping[str, Any]:
    """Every documented property present, correctly typed, with pinned values."""
    assert isinstance(result, SuccessResult), result
    data = result.data
    assert data["success"] is True, data
    missing = documented_keys() - set(data)
    assert not missing, f"documented but absent: {sorted(missing)}; got {sorted(data)}"
    for name, kind in DOCUMENTED_TYPES.items():
        assert isinstance(data[name], kind), f"{name}={data[name]!r} is not {kind}"
    for name, value in expected.items():
        assert data[name] == value, f"{name}={data[name]!r}, expected {value!r}"
    return data


def _session(tmp_path: Path, *, text: str, format_group: str = FORMAT_TEXT) -> EditSession:
    """A real on-disk text session: origin snapshot plus an editable draft."""
    abs_path = tmp_path / "foo.py"
    abs_path.write_text(text, encoding="utf-8")
    draft_path = tmp_path / "foo.py.draft"
    draft_path.write_text(text, encoding="utf-8")
    return EditSession(
        session_id=SESSION_ID,
        project_id=PROJECT_ID,
        file_path=FILE_PATH,
        abs_path=abs_path,
        draft_path=draft_path,
        lockfile_path=tmp_path / "foo.lock",
        format_group=format_group,
        handler_id="text",
        tree_id=None,
        core=MagicMock(),
    )


async def _execute(session: EditSession, **params: Any) -> Any:
    """Run the command end to end with the Code Analysis transport mocked."""
    client = MagicMock()
    module = "ai_editor.commands.universal_file_edit.write_command"
    with patch(f"{module}.get_code_analysis_client", return_value=client), patch(
        f"{module}.SessionGuard"
    ) as guard, patch(
        "ai_editor.commands.universal_file_edit.write_command_runtime"
        ".resolve_session_for_command",
        return_value=session,
    ):
        guard.return_value.check.return_value = GuardDecision.ALLOW
        return await UniversalFileWriteCommand().execute(**params)


@pytest.mark.asyncio
async def test_preview_unchanged_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, text="x = 1\n")
    result = await _execute(
        session,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        file_path=FILE_PATH,
        write_mode="preview",
    )
    assert_documented_shape(
        result,
        phase="preview",
        write_mode="preview",
        has_changes=False,
        unchanged=True,
        uploaded=False,
        diff="",
        format_python=False,
        session_id=SESSION_ID,
        project_id=PROJECT_ID,
        file_path=FILE_PATH,
    )


@pytest.mark.asyncio
async def test_preview_changed_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, text="x = 1\n")
    session.draft_path.write_text("x = 2\n", encoding="utf-8")
    data = assert_documented_shape(
        await _execute(
            session,
            project_id=PROJECT_ID,
            session_id=SESSION_ID,
            file_path=FILE_PATH,
            write_mode="preview",
        ),
        phase="preview",
        has_changes=True,
        unchanged=False,
        uploaded=False,
        session_id=SESSION_ID,
        project_id=PROJECT_ID,
        file_path=FILE_PATH,
    )
    assert "-x = 1" in data["diff"] and "+x = 2" in data["diff"], data["diff"]


@pytest.mark.asyncio
async def test_preview_by_default_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    """``write_mode`` omitted still previews, and still answers in full."""
    session = _session(tmp_path, text="x = 1\n")
    result = await _execute(
        session,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        file_path=FILE_PATH,
        write_mode="preview",
        write_mode_explicit=False,
    )
    assert_documented_shape(
        result, phase="preview", write_mode="preview", uploaded=False,
        session_id=SESSION_ID, project_id=PROJECT_ID, file_path=FILE_PATH,
    )


@pytest.mark.asyncio
async def test_sidecar_first_call_preview_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    """The sidecar two-phase first call is a preview and answers like one."""
    session = _session(tmp_path, text="x = 1\n", format_group=FORMAT_SIDECAR)
    with patch(
        "ai_editor.commands.universal_file_edit.write_command_phases"
        ".compare_session_to_origin",
        return_value=WriteComparison(
            result=CompareResult.DIFF,
            origin_bytes=b"x = 1\n",
            exported_bytes=b"x = 2\n",
        ),
    ):
        result = await _execute(
            session,
            project_id=PROJECT_ID,
            session_id=SESSION_ID,
            file_path=FILE_PATH,
            write_mode="preview",
            write_mode_explicit=False,
        )
    assert_documented_shape(
        result, phase="preview", uploaded=False, has_changes=True,
        session_id=SESSION_ID, project_id=PROJECT_ID, file_path=FILE_PATH,
    )
    assert session.lockfile_path.is_file(), "first call must still take the lockfile"


@pytest.mark.asyncio
async def test_preview_echoes_format_python_flag(tmp_path: Path) -> None:
    session = _session(tmp_path, text="x = 1\n")
    data = assert_documented_shape(
        await _execute(
            session,
            project_id=PROJECT_ID,
            session_id=SESSION_ID,
            file_path=FILE_PATH,
            write_mode="preview",
            format_python=True,
        ),
        format_python=True,
    )
    assert data["uploaded"] is False, data


@pytest.mark.asyncio
async def test_preview_with_file_path_omitted_echoes_the_resolved_path(
    tmp_path: Path,
) -> None:
    """The response is how a caller learns which open file the server picked."""
    session = _session(tmp_path, text="x = 1\n")
    result = await _execute(
        session, project_id=PROJECT_ID, session_id=SESSION_ID, write_mode="preview"
    )
    assert_documented_shape(result, file_path=FILE_PATH, uploaded=False)


@pytest.mark.asyncio
async def test_commit_noop_still_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, text="x = 1\n")
    result = await _execute(
        session,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        file_path=FILE_PATH,
        write_mode="commit",
    )
    assert_documented_shape(
        result,
        phase="committed",
        write_mode="commit",
        has_changes=False,
        unchanged=True,
        uploaded=False,
        diff="",
        session_id=SESSION_ID,
        project_id=PROJECT_ID,
        file_path=FILE_PATH,
    )


@pytest.mark.asyncio
async def test_commit_upload_still_carries_every_documented_property(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, text="x = 1\n")
    session.draft_path.write_text("x = 2\n", encoding="utf-8")
    client = MagicMock()
    client.upload_session_file_content.return_value = b"x = 2\n"
    client.get_project_root.return_value = None
    module = "ai_editor.commands.universal_file_edit.write_command"
    with patch(f"{module}.get_code_analysis_client", return_value=client), patch(
        f"{module}.SessionGuard"
    ) as guard, patch(
        "ai_editor.commands.universal_file_edit.write_command_runtime"
        ".resolve_session_for_command",
        return_value=session,
    ), patch(
        "ai_editor.commands.universal_file_edit.write_command_phases"
        ".validate_draft_in_project_context"
    ) as validate:
        guard.return_value.check.return_value = GuardDecision.ALLOW
        validate.return_value = MagicMock(
            success=True, temp_path=None, quality_results={}, handler_results={}
        )
        result = await UniversalFileWriteCommand().execute(
            project_id=PROJECT_ID,
            session_id=SESSION_ID,
            file_path=FILE_PATH,
            write_mode="commit",
        )
    assert_documented_shape(
        result,
        phase="committed",
        write_mode="commit",
        has_changes=True,
        unchanged=False,
        uploaded=True,
        session_id=SESSION_ID,
        project_id=PROJECT_ID,
        file_path=FILE_PATH,
    )
