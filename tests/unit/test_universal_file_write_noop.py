"""Unit tests for universal_file_write no-op branch (C-012)."""

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
from ai_editor.core.file_validation.pre_write_pipeline import PreWriteValidationOutcome
from ai_editor.core.upstream.session_guard import GuardDecision, OperationKind


def _mock_session(*, mock_abs_path: bool = False) -> EditSession:
    core = MagicMock()
    abs_path: Path | MagicMock = MagicMock() if mock_abs_path else Path("/tmp/foo.py")
    return EditSession(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        abs_path=abs_path,
        draft_path=Path("/tmp/foo.py.draft"),
        lockfile_path=Path("/tmp/foo.lock"),
        format_group="text",
        handler_id="text",
        tree_id=None,
        core=core,
    )


@pytest.mark.asyncio
async def test_write_commit_equal_returns_noop_without_upload() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = WriteComparison(
        result=CompareResult.EQUAL,
        origin_bytes=b"x = 1\n",
        exported_bytes=b"x = 1\n",
    )
    client = MagicMock()

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
        ) as mock_guard_cls:
            mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW
            with patch(
                "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
                return_value=session,
            ):
                with patch(
                    "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
                    return_value=comparison,
                ) as mock_compare:
                    result = await cmd.execute(
                        project_id="proj-1",
                        session_id="sess-1",
                        write_mode="commit",
                    )

    assert isinstance(result, SuccessResult)
    assert result.data["unchanged"] is True
    assert result.data["uploaded"] is False
    assert result.data["session_id"] == "sess-1"
    assert result.data["project_id"] == "proj-1"
    assert result.data["file_path"] == "src/foo.py"
    mock_compare.assert_called_once_with(session, format_python=False)
    client.ensure_session_file_lock.assert_called_once_with(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
    )
    client.upload_session_file_content.assert_not_called()
    client.upload_create_and_lock.assert_not_called()


@pytest.mark.asyncio
async def test_write_commit_equal_fails_when_lock_check_fails() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = WriteComparison(
        result=CompareResult.EQUAL,
        origin_bytes=b"x = 1\n",
        exported_bytes=b"x = 1\n",
    )
    client = MagicMock()
    client.ensure_session_file_lock.side_effect = RuntimeError("LOCK_DENIED")

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
        ) as mock_guard_cls:
            mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW
            with patch(
                "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
                return_value=session,
            ):
                with patch(
                    "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
                    return_value=comparison,
                ):
                    result = await cmd.execute(
                        project_id="proj-1",
                        session_id="sess-1",
                        write_mode="commit",
                    )

    assert isinstance(result, ErrorResult)
    assert result.code == "UPSTREAM_LOCK_FAILED"
    assert result.message == "RuntimeError: LOCK_DENIED"
    client.ensure_session_file_lock.assert_called_once_with(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
    )
    client.upload_session_file_content.assert_not_called()
    client.upload_create_and_lock.assert_not_called()


@pytest.mark.asyncio
async def test_write_commit_diff_uploads_and_syncs_origin() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session(mock_abs_path=True)
    comparison = WriteComparison(
        result=CompareResult.DIFF,
        origin_bytes=b"x = 1\n",
        exported_bytes=b"x = 2\n",
    )
    accepted_bytes = b"x = 2\n"
    client = MagicMock()
    client.upload_session_file_content.return_value = accepted_bytes

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
        ) as mock_guard_cls:
            mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW
            with patch(
                "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
                return_value=session,
            ):
                with patch(
                    "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
                    return_value=comparison,
                ):
                    with patch(
                        "ai_editor.commands.universal_file_edit.write_command_runtime.phases.validate_draft_in_project_context",
                        return_value=PreWriteValidationOutcome(success=True),
                    ):
                        result = await cmd.execute(
                            project_id="proj-1",
                            session_id="sess-1",
                            write_mode="commit",
                        )

    assert isinstance(result, SuccessResult)
    assert result.data["unchanged"] is False
    assert result.data["uploaded"] is True
    assert result.data["session_id"] == "sess-1"
    assert result.data["project_id"] == "proj-1"
    assert result.data["file_path"] == "src/foo.py"
    client.upload_session_file_content.assert_called_once_with(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        content=b"x = 2\n",
    )
    session.abs_path.write_bytes.assert_called_once_with(accepted_bytes)


@pytest.mark.asyncio
async def test_write_preview_returns_diff_without_upload() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    session.format_group = "text"
    session.draft_path = MagicMock()
    session.draft_path.read_text.return_value = "x = 2\n"
    session.abs_path = MagicMock()
    session.abs_path.is_file.return_value = True
    session.abs_path.read_text.return_value = "x = 1\n"
    session.abs_path.read_bytes.return_value = b"x = 1\n"
    session.abs_path.__str__ = lambda _s: "/tmp/foo.py"
    client = MagicMock()

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
        ) as mock_guard_cls:
            mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW
            with patch(
                "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
                return_value=session,
            ):
                result = await cmd.execute(
                    project_id="proj-1",
                    session_id="sess-1",
                    write_mode="preview",
                )

    assert isinstance(result, SuccessResult)
    assert result.data["phase"] == "preview"
    assert result.data["has_changes"] is True
    assert "diff" in result.data
    client.upload_session_file_content.assert_not_called()


@pytest.mark.asyncio
async def test_write_guard_reject_skips_compare() -> None:
    cmd = UniversalFileWriteCommand()
    client = MagicMock()

    with patch(
        "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.write_command.SessionGuard"
        ) as mock_guard_cls:
            mock_guard_cls.return_value.check.return_value = GuardDecision.REJECT
            with patch(
                "ai_editor.commands.universal_file_edit.write_command_runtime.resolve_session_for_command",
            ) as mock_resolve_session_for_command:
                with patch(
                    "ai_editor.commands.universal_file_edit.write_command_runtime.compare_session_to_origin",
                ) as mock_compare:
                    result = await cmd.execute(
                        project_id="proj-1",
                        session_id="sess-1",
                        write_mode="commit",
                    )

    assert isinstance(result, ErrorResult)
    assert result.code == "SESSION_REJECTED"
    mock_guard_cls.return_value.check.assert_called_once_with(
        OperationKind.WRITE,
        "sess-1",
    )
    mock_resolve_session_for_command.assert_not_called()
    mock_compare.assert_not_called()
    client.upload_session_file_content.assert_not_called()
