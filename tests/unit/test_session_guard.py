"""Unit tests for SessionGuard (C-024, C-015)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_editor.core.upstream.code_analysis_client import CaSessionStatus
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


@pytest.mark.parametrize(
    "kind",
    [OperationKind.OPEN, OperationKind.EDIT, OperationKind.PREVIEW],
)
def test_normal_ops_allow_valid_session(kind: OperationKind) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.VALID
    guard = SessionGuard(client)
    assert guard.check(kind, "sess-1") == GuardDecision.ALLOW
    client.validate_ca_session.assert_called_once_with("sess-1")


@pytest.mark.parametrize(
    "status",
    [CaSessionStatus.NOT_FOUND, CaSessionStatus.INVALID],
)
@pytest.mark.parametrize(
    "kind",
    [OperationKind.OPEN, OperationKind.EDIT, OperationKind.PREVIEW],
)
def test_normal_ops_reject_broken_session(
    kind: OperationKind, status: CaSessionStatus
) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = status
    guard = SessionGuard(client)
    assert guard.check(kind, "broken") == GuardDecision.REJECT


@pytest.mark.parametrize("kind", [OperationKind.WRITE, OperationKind.CLOSE])
def test_terminating_ops_allow_valid_session(kind: OperationKind) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.VALID
    guard = SessionGuard(client)
    assert guard.check(kind, "sess-1") == GuardDecision.ALLOW_TERMINATING
    client.validate_ca_session.assert_called_once_with("sess-1")


@pytest.mark.parametrize("kind", [OperationKind.WRITE, OperationKind.CLOSE])
def test_terminating_ops_allow_invalid_session(kind: OperationKind) -> None:
    client = MagicMock()
    client.validate_ca_session.return_value = CaSessionStatus.INVALID
    guard = SessionGuard(client)
    assert guard.check(kind, "broken") == GuardDecision.ALLOW_TERMINATING
    client.validate_ca_session.assert_called_once_with("broken")


@pytest.mark.parametrize("kind", list(OperationKind))
def test_empty_session_id_rejects(kind: OperationKind) -> None:
    client = MagicMock()
    guard = SessionGuard(client)
    assert guard.check(kind, "") == GuardDecision.REJECT
    assert guard.check(kind, "   ") == GuardDecision.REJECT
    client.validate_ca_session.assert_not_called()
