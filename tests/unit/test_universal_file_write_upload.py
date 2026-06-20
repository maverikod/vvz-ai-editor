"""Unit tests for universal_file_write upload and origin sync (C-012, C-015)."""

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
from ai_editor.core.upstream.session_guard import GuardDecision


def _mock_session() -> EditSession:
    core = MagicMock()
    abs_path = MagicMock()
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


def _diff_comparison() -> WriteComparison:
    return WriteComparison(
        result=CompareResult.DIFF,
        origin_bytes=b"x = 1\n",
        exported_bytes=b"x = 2\n",
    )


def _validation_ok() -> PreWriteValidationOutcome:
    return PreWriteValidationOutcome(success=True)


@pytest.mark.asyncio
async def test_upload_success_writes_origin_snapshot() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = _diff_comparison()
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
                        "ai_editor.commands.universal_file_edit.write_command_runtime.validate_before_promote",
                        return_value=_validation_ok(),
                    ):
                        result = await cmd.execute(
                            project_id="proj-1",
                            session_id="sess-1",
                            write_mode="commit",
                        )

    assert isinstance(result, SuccessResult)
    assert result.data["unchanged"] is False
    assert result.data["uploaded"] is True
    client.upload_session_file_content.assert_called_once_with(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        content=b"x = 2\n",
    )
    session.abs_path.write_bytes.assert_called_once_with(accepted_bytes)


@pytest.mark.asyncio
async def test_upload_runtime_error_preserves_origin() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = _diff_comparison()
    client = MagicMock()
    client.upload_session_file_content.side_effect = RuntimeError("upstream timeout")

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
                        "ai_editor.commands.universal_file_edit.write_command_runtime.validate_before_promote",
                        return_value=_validation_ok(),
                    ):
                        result = await cmd.execute(
                            project_id="proj-1",
                            session_id="sess-1",
                            write_mode="commit",
                        )

    assert isinstance(result, ErrorResult)
    assert result.code == "UPSTREAM_UPLOAD_FAILED"
    assert result.message == "upstream timeout"
    assert result.details == {"upstream_error": "upstream timeout"}
    session.abs_path.write_bytes.assert_not_called()
    client.upload_session_file_content.assert_called_once()


@pytest.mark.asyncio
async def test_upload_generic_exception_preserves_origin() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    comparison = _diff_comparison()
    client = MagicMock()
    client.upload_session_file_content.side_effect = ValueError("bad payload")

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
                        "ai_editor.commands.universal_file_edit.write_command_runtime.validate_before_promote",
                        return_value=_validation_ok(),
                    ):
                        result = await cmd.execute(
                            project_id="proj-1",
                            session_id="sess-1",
                            write_mode="commit",
                        )

    assert isinstance(result, ErrorResult)
    assert result.code == "UPSTREAM_UPLOAD_FAILED"
    assert result.message == "bad payload"
    assert result.details == {"upstream_error": "bad payload"}
    session.abs_path.write_bytes.assert_not_called()
    client.upload_session_file_content.assert_called_once()
