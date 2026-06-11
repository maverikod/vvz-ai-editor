"""Unit tests for SessionGuard zombie cleanup delegation (C-025, C-024)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.core.upstream.code_analysis_client import CaSessionStatus
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


@pytest.mark.parametrize("kind", [OperationKind.WRITE, OperationKind.CLOSE])
def test_terminating_not_found_delegates_cleanup(
    kind: OperationKind, tmp_path: Path
) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)

    with patch(
        "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session"
    ) as mock_cleanup:
        decision = guard.check(kind, "zombie-sid", workspace_root=tmp_path)

    assert decision == GuardDecision.ALLOW_TERMINATING
    client.validate_ca_session.assert_called_once_with("zombie-sid")
    mock_cleanup.assert_called_once_with("zombie-sid", workspace_root=tmp_path)


@pytest.mark.parametrize("kind", [OperationKind.WRITE, OperationKind.CLOSE])
def test_terminating_not_found_resolves_workspace_root_when_omitted(
    kind: OperationKind,
) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.NOT_FOUND
    guard = SessionGuard(client)
    resolved = Path("/resolved/workspace")

    with patch(
        "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
        return_value=resolved,
    ):
        with patch(
            "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session"
        ) as mock_cleanup:
            decision = guard.check(kind, "zombie-sid")

    assert decision == GuardDecision.ALLOW_TERMINATING
    mock_cleanup.assert_called_once_with("zombie-sid", workspace_root=resolved)


@pytest.mark.parametrize("kind", [OperationKind.WRITE, OperationKind.CLOSE])
def test_terminating_valid_skips_cleanup(kind: OperationKind) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.VALID
    guard = SessionGuard(client)

    with patch(
        "ai_editor.core.workspace_session_cleanup.cleanup_zombie_ca_session"
    ) as mock_cleanup:
        decision = guard.check(kind, "live-sid")

    assert decision == GuardDecision.ALLOW_TERMINATING
    mock_cleanup.assert_not_called()
