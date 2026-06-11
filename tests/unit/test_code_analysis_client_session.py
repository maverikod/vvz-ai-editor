"""Unit tests for CodeAnalysisClient.validate_ca_session (C-002, C-014)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def test_validate_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))
    monkeypatch.setattr(client, "call", lambda cmd, params=None: {"locks": []})
    assert client.validate_ca_session("ok") == CaSessionStatus.VALID


def test_validate_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))

    def boom(cmd: str, params: dict[str, Any] | None = None) -> Any:
        raise RuntimeError("SESSION_NOT_FOUND")

    monkeypatch.setattr(client, "call", boom)
    assert client.validate_ca_session("missing") == CaSessionStatus.NOT_FOUND


def test_validate_empty() -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))
    assert client.validate_ca_session("") == CaSessionStatus.INVALID
