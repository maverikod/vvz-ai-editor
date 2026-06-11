"""Unit tests for SessionGuard integration in universal_file_edit (C-024, C-015)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.errors import SESSION_NOT_FOUND
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus


def _mock_ca_client(status: CaSessionStatus) -> MagicMock:
    client = MagicMock()
    client.validate_ca_session.return_value = status
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [CaSessionStatus.NOT_FOUND, CaSessionStatus.INVALID],
)
async def test_edit_rejects_broken_ca_session(status: CaSessionStatus) -> None:
    cmd = UniversalFileEditCommand()
    with patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
        return_value=_mock_ca_client(status),
    ), patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_session",
    ) as get_session_mock:
        result = await cmd.execute(
            project_id="proj-1",
            session_id="broken-session",
            operations=[{"type": "replace", "node_id": "n1", "code_lines": ["x = 1"]}],
        )

    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND
    assert "broken-session" in result.message
    get_session_mock.assert_not_called()


@pytest.mark.asyncio
async def test_edit_rejects_empty_session_id() -> None:
    cmd = UniversalFileEditCommand()
    with patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
        return_value=_mock_ca_client(CaSessionStatus.VALID),
    ) as client_factory, patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_session",
    ) as get_session_mock:
        result = await cmd.execute(
            project_id="proj-1",
            session_id="   ",
            operations=[{"type": "replace", "node_id": "n1", "code_lines": ["x = 1"]}],
        )

    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND
    get_session_mock.assert_not_called()
    client_factory.return_value.validate_ca_session.assert_not_called()


@pytest.mark.asyncio
async def test_edit_reject_skips_draft_mutations() -> None:
    cmd = UniversalFileEditCommand()
    with patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
        return_value=_mock_ca_client(CaSessionStatus.NOT_FOUND),
    ), patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_session",
    ), patch(
        "ai_editor.commands.universal_file_edit.edit_command.run_text_draft_apply",
    ) as text_apply, patch(
        "ai_editor.commands.universal_file_edit.edit_command.run_sidecar_cst_edit_batch",
    ) as sidecar_apply, patch(
        "ai_editor.commands.universal_file_edit.edit_command.tree_temp_edit_batch.apply_tree_temp_mutations",
    ) as tree_apply:
        result = await cmd.execute(
            project_id="proj-1",
            session_id="missing-ca",
            operations=[{"type": "replace", "node_id": "n1", "code_lines": ["x = 1"]}],
        )

    assert isinstance(result, ErrorResult)
    text_apply.assert_not_called()
    sidecar_apply.assert_not_called()
    tree_apply.assert_not_called()
