"""Unit tests for SessionGuard integration in universal_file_close (C-013, C-015)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


def _mock_session() -> tuple[EditSession, MagicMock]:
    core = MagicMock()
    session = EditSession(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        abs_path=Path("/tmp/foo.py"),
        draft_path=Path("/tmp/foo.py.draft"),
        lockfile_path=Path("/tmp/foo.py.lock"),
        format_group="text",
        handler_id="text",
        tree_id=None,
        core=core,
    )
    return session, core


@pytest.mark.asyncio
async def test_close_rejects_empty_session_id() -> None:
    cmd = UniversalFileCloseCommand()
    with patch(
        "ai_editor.commands.universal_file_edit.close_command.resolve_session_for_command",
    ) as mock_get:
        result = await cmd.execute(project_id="p1", session_id="")
        assert isinstance(result, ErrorResult)
        assert result.code == "SESSION_REJECTED"
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_close_cleans_workspace_when_ca_session_not_found() -> None:
    """Terminating close: broken CA session still runs local cleanup."""
    cmd = UniversalFileCloseCommand()
    session, mock_core = _mock_session()
    workspace = Path("/tmp/workspace")

    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    client.unlock_session_file.return_value = False

    with patch(
        "ai_editor.commands.universal_file_edit.close_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.close_command.resolve_session_for_command",
            return_value=session,
        ):
            with patch.object(
                cmd,
                "_close_tree_temp_or_text",
                return_value={"success": True, "draft_rebuilt": False},
            ):
                with patch(
                    "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session",
                ) as mock_cleanup:
                    with patch(
                        "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
                        return_value=workspace,
                    ):
                        with patch(
                            "ai_editor.commands.universal_file_edit.close_command.resolve_workspace_root",
                            return_value=workspace,
                        ):
                            with patch(
                                "ai_editor.commands.universal_file_edit.close_command.list_bundle_file_paths",
                                side_effect=[["src/foo.py"], []],
                            ):
                                with patch(
                                    "ai_editor.commands.universal_file_edit.close_command.remove_file_subtree",
                                ):
                                    with patch(
                                        "ai_editor.commands.universal_file_edit.close_command.shutil.rmtree",
                                    ):
                                        with patch(
                                            "ai_editor.commands.universal_file_edit.close_command.release_session",
                                        ) as mock_release:
                                            result = await cmd.execute(
                                                project_id="proj-1",
                                                session_id="broken-ca-session",
                                            )
                                            assert isinstance(result, SuccessResult)
                                            assert result.data["success"] is True
                                            mock_cleanup.assert_called_once_with(
                                                "broken-ca-session",
                                                workspace_root=workspace,
                                            )
                                            mock_core.close.assert_called_once()
                                            mock_release.assert_called_once_with(
                                                "broken-ca-session",
                                                session.file_path,
                                            )
                                            client.unlock_session_file.assert_called_once_with(
                                                session_id="broken-ca-session",
                                                project_id="proj-1",
                                                file_path="src/foo.py",
                                            )


@pytest.mark.asyncio
async def test_close_releases_bundle_when_workspace_file_missing() -> None:
    """Missing workspace files must not block bundle release."""
    cmd = UniversalFileCloseCommand()
    session, mock_core = _mock_session()
    workspace = Path("/tmp/workspace")

    client = MagicMock()
    client.unlock_session_file.return_value = False

    with patch(
        "ai_editor.commands.universal_file_edit.close_command.get_code_analysis_client",
        return_value=client,
    ):
        with patch(
            "ai_editor.commands.universal_file_edit.close_command.resolve_session_for_command",
            return_value=session,
        ):
            with patch.object(
                cmd,
                "_close_tree_temp_or_text",
                side_effect=FileNotFoundError(
                    "File not found: /var/ai-editor/editor_workspaces/sess-1/files/foo.py"
                ),
            ):
                with patch(
                    "ai_editor.commands.universal_file_edit.close_command.resolve_workspace_root",
                    return_value=workspace,
                ):
                    with patch(
                        "ai_editor.commands.universal_file_edit.close_command.list_bundle_file_paths",
                        side_effect=[["src/foo.py"], []],
                    ):
                        with patch(
                            "ai_editor.commands.universal_file_edit.close_command.file_workspace_layout",
                        ) as mock_layout:
                            layout = MagicMock()
                            layout.file_subtree_dir = MagicMock()
                            layout.file_subtree_dir.is_dir.return_value = False
                            layout.session_dir = MagicMock()
                            layout.session_dir.is_dir.return_value = False
                            mock_layout.return_value = layout
                            with patch(
                                "ai_editor.commands.universal_file_edit.close_command.release_session",
                            ) as mock_release:
                                result = await cmd.execute(
                                    project_id="proj-1",
                                    session_id="sess-1",
                                )
                                assert isinstance(result, SuccessResult)
                                assert result.data["success"] is True
                                assert result.data["unlock_ok"] is False
                                assert result.data["workspace_subtree_removed"] is False
                                mock_core.close.assert_called_once()
                                mock_release.assert_called_once_with(
                                    "sess-1",
                                    session.file_path,
                                )


@pytest.mark.asyncio
async def test_close_proceeds_on_allow_terminating_decision() -> None:
    cmd = UniversalFileCloseCommand()
    session, _mock_core = _mock_session()
    workspace = Path("/tmp/workspace")

    with patch(
        "ai_editor.commands.universal_file_edit.close_command.SessionGuard"
    ) as mock_guard_cls:
        mock_guard_cls.return_value.check.return_value = GuardDecision.ALLOW_TERMINATING
        with patch(
            "ai_editor.commands.universal_file_edit.close_command.resolve_session_for_command",
            return_value=session,
        ):
            with patch.object(
                cmd,
                "_close_tree_temp_or_text",
                return_value={"success": True, "draft_rebuilt": False},
            ):
                with patch(
                    "ai_editor.commands.universal_file_edit.close_command.resolve_workspace_root",
                    return_value=workspace,
                ):
                    with patch(
                        "ai_editor.commands.universal_file_edit.close_command.list_bundle_file_paths",
                        side_effect=[["src/foo.py"], []],
                    ):
                        with patch(
                            "ai_editor.commands.universal_file_edit.close_command.remove_file_subtree",
                        ):
                            with patch(
                                "ai_editor.commands.universal_file_edit.close_command.shutil.rmtree",
                            ):
                                with patch(
                                    "ai_editor.commands.universal_file_edit.close_command.get_code_analysis_client",
                                ) as mock_client_factory:
                                    mock_client = MagicMock()
                                    mock_client_factory.return_value = mock_client
                                    result = await cmd.execute(
                                        project_id="proj-1",
                                        session_id="sess-1",
                                    )
                                    assert isinstance(result, SuccessResult)
                                    mock_guard_cls.return_value.check.assert_called_once_with(
                                        OperationKind.CLOSE,
                                        "sess-1",
                                    )
                                    mock_client.unlock_session_file.assert_called_once()


def test_guard_close_not_found_is_allow_terminating() -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)
    with patch(
        "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session",
    ):
        with patch(
            "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
            return_value=Path("/tmp"),
        ):
            assert (
                guard.check(OperationKind.CLOSE, "broken")
                == GuardDecision.ALLOW_TERMINATING
            )
    client.validate_ca_session.assert_called_once_with("broken")
