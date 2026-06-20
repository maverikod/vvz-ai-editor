"""Tests for info command."""

from __future__ import annotations

import pytest

from ai_editor.commands.info_command import InfoCommand


@pytest.mark.asyncio
async def test_info_returns_guide_payload() -> None:
    result = await InfoCommand().execute()
    assert type(result).__name__ == "SuccessResult"
    data = result.data
    assert "markdown" in data
    assert "lifecycle" in data
    assert "universal_file_open" in data["markdown"]
    assert "info" in data["registered_commands"]
    assert data["examples"]["write_commit"]["write_mode"] == "commit"


@pytest.mark.asyncio
async def test_info_rejects_unknown_params() -> None:
    result = await InfoCommand().execute(unexpected="x")
    assert type(result).__name__ == "ErrorResult"
    assert result.code == "VALIDATION_ERROR"
