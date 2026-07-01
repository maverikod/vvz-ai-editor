"""Unit tests for universal_file_write upload and origin sync (C-012, C-015).

Also covers TZ-AIEDITOR-COMMIT-STALE-VALIDATION-001 regression guard:
  A-5: genuinely incomplete docstrings are rejected by local validation (VALIDATION_ERROR)
       before CA upload is ever attempted.
  A-1/A-4: valid content produces SuccessResult; CA validate_syntax_only=True avoids
            stale-state rejection.
"""

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
async def test_upload_success_origin_snapshot_permission_error_is_structured() -> None:
    cmd = UniversalFileWriteCommand()
    session = _mock_session()
    session.modified = True
    comparison = _diff_comparison()
    accepted_bytes = b"x = 2\n"
    client = MagicMock()
    client.upload_session_file_content.return_value = accepted_bytes
    session.abs_path.write_bytes.side_effect = PermissionError(
        13,
        "Permission denied",
        "/workspace/src/foo.py",
    )

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
    assert result.code == "HOST_FILE_OPERATION_ERROR"
    assert result.details is not None
    assert result.details["reason"] == "permission_denied"
    assert result.details["method_name"] == (
        "_run_write_commit_ca:write_origin_snapshot"
    )
    assert session.modified is True
    assert session.persisted_on_ca is True


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


# ---------------------------------------------------------------------------
# TZ-AIEDITOR-COMMIT-STALE-VALIDATION-001 regression guard
# ---------------------------------------------------------------------------

_INCOMPLETE_DOCSTRING_PY = '''\
"""Module docstring."""


def greet(name: str) -> str:
    return f"Hello, {name}"
'''

_COMPLETE_DOCSTRING_PY = '''\
"""Module docstring."""


def greet(name: str) -> str:
    """Return a greeting.

    Args:
        name: Person name.

    Returns:
        Greeting text.
    """
    return f"Hello, {name}"
'''


def _mock_python_session(tmp_path: Path) -> EditSession:
    """EditSession with handler_id=python and a real abs_path on disk."""
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old\n", encoding="utf-8")
    core = MagicMock()
    core.project_root = None
    return EditSession(
        session_id="sess-py",
        project_id="proj-1",
        file_path="src/foo.py",
        abs_path=target,
        draft_path=target,
        lockfile_path=tmp_path / "foo.lock",
        format_group="text",
        handler_id="python",
        tree_id=None,
        core=core,
    )


@pytest.mark.asyncio
async def test_commit_locally_rejects_incomplete_docstrings(tmp_path: Path) -> None:
    """A-5: commit on a draft with missing docstrings returns VALIDATION_ERROR.

    Local validate_before_promote must fire before any CA upload attempt.
    """
    session = _mock_python_session(tmp_path)
    comparison = WriteComparison(
        result=CompareResult.DIFF,
        origin_bytes=b"old\n",
        exported_bytes=_INCOMPLETE_DOCSTRING_PY.encode("utf-8"),
    )
    client = MagicMock()
    client.upload_session_file_content.return_value = _INCOMPLETE_DOCSTRING_PY.encode(
        "utf-8"
    )

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
                    cmd = UniversalFileWriteCommand()
                    result = await cmd.execute(
                        project_id="proj-1",
                        session_id="sess-py",
                        write_mode="commit",
                    )

    assert isinstance(result, ErrorResult), f"Expected ErrorResult, got: {result}"
    assert result.code == "VALIDATION_ERROR", (
        f"Expected VALIDATION_ERROR, got {result.code!r}; "
        "must NOT be UPSTREAM_UPLOAD_FAILED (stale CA rejection)"
    )
    client.upload_session_file_content.assert_not_called()


@pytest.mark.asyncio
async def test_commit_succeeds_for_complete_docstrings(tmp_path: Path) -> None:
    """A-1: commit on a draft with valid docstrings returns SuccessResult."""
    session = _mock_python_session(tmp_path)
    exported = _COMPLETE_DOCSTRING_PY.encode("utf-8")
    comparison = WriteComparison(
        result=CompareResult.DIFF,
        origin_bytes=b"old\n",
        exported_bytes=exported,
    )
    client = MagicMock()
    client.upload_session_file_content.return_value = exported

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
                    cmd = UniversalFileWriteCommand()
                    result = await cmd.execute(
                        project_id="proj-1",
                        session_id="sess-py",
                        write_mode="commit",
                    )

    assert isinstance(result, SuccessResult), (
        f"Expected SuccessResult, got: {result!r}. "
        "After valid docstring edits, commit must not return VALIDATION_ERROR "
        "or UPSTREAM_UPLOAD_FAILED."
    )
    assert result.data["uploaded"] is True
    client.upload_session_file_content.assert_called_once_with(
        session_id="sess-py",
        project_id="proj-1",
        file_path="src/foo.py",
        content=exported,
    )
