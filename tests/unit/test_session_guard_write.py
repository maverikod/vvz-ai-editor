"""Unit tests for SessionGuard integration in universal_file_write (C-015, C-024)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    WriteComparison,
)
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


def _mock_session() -> EditSession:
    core = MagicMock()
    return EditSession(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        abs_path=Path("/tmp/foo.py"),
        draft_path=Path("/tmp/foo.py.draft"),
        lockfile_path=Path("/tmp/foo.lock"),
        format_group="text",
        handler_id="text",
        tree_id=None,
        core=core,
    )


@pytest.mark.asyncio
async def test_write_rejects_empty_session_id() -> None:
    cmd = UniversalFileWriteCommand()
    with (
        patch(
            "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
            return_value=MagicMock(),
        ),
        patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
        ) as mock_get,
        patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
        ) as mock_compare,
    ):
        result = await cmd.execute(
            project_id="p1",
            session_id="",
            write_mode="preview",
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SESSION_REJECTED"
        mock_get.assert_not_called()
        mock_compare.assert_not_called()


@pytest.mark.asyncio
async def test_write_attempted_when_session_not_found_terminating() -> None:
    """Terminating write: broken CA session still runs inline compare path."""
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = WriteComparison(
        result=CompareResult.EQUAL,
        origin_bytes=b"x\n",
        exported_bytes=b"x\n",
    )
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND

    with (
        patch(
            "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
            return_value=client,
        ),
        patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
            return_value=session,
        ) as mock_get,
        patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
            return_value=comparison,
        ) as mock_compare,
        patch(
            "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session",
        ),
    ):
        result = await cmd.execute(
            project_id="p1",
            session_id="broken-ca-session",
            write_mode="commit",
        )

    assert isinstance(result, SuccessResult)
    assert result.data["unchanged"] is True
    mock_get.assert_called_once()
    mock_compare.assert_called_once_with(session, format_python=False)


@pytest.mark.asyncio
async def test_write_proceeds_on_allow_terminating_decision() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
    ) as mock_guard_cls:
        mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW_TERMINATING
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
            return_value=MagicMock(),
        ), patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
            return_value=session,
        ) as mock_get, patch(
            "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
            return_value=WriteComparison(
                result=CompareResult.EQUAL,
                origin_bytes=b"a",
                exported_bytes=b"a",
            ),
        ) as mock_compare:
            result = await cmd.execute(
                project_id="p1",
                session_id="sess-1",
                write_mode="commit",
            )
            assert isinstance(result, SuccessResult)
            assert result.data["unchanged"] is True
            mock_guard_cls.return_value.check.assert_called_once_with(
                OperationKind.WRITE,
                "sess-1",
            )
            mock_get.assert_called_once()
            mock_compare.assert_called_once_with(session, format_python=False)


def test_guard_write_not_found_is_allow_terminating() -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)
    root = MagicMock()
    with patch(
        "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session"
    ) as mock_cleanup:
        assert (
            guard.check(OperationKind.WRITE, "broken", workspace_root=root)
            == GuardDecision.ALLOW_TERMINATING
        )
    client.validate_ca_session.assert_called_once_with("broken")
    mock_cleanup.assert_called_once_with("broken", workspace_root=root)
