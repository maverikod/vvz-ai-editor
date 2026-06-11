"""Tests for health parameter validation."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.core.errors import ValidationError

from ai_editor.commands.health_command import HealthCommand


@pytest.mark.asyncio
async def test_health_validate_params_rejects_unknown_param() -> None:
    cmd = HealthCommand()
    with pytest.raises(ValidationError, match="Invalid parameters"):
        cmd.validate_params({"__unknown_param__": "x"})


@pytest.mark.asyncio
async def test_health_execute_rejects_unknown_param() -> None:
    result = await HealthCommand().execute(__unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "invalid parameters" in result.message.lower()


@pytest.mark.asyncio
async def test_health_execute_succeeds_with_no_params() -> None:
    result = await HealthCommand().execute()
    assert isinstance(result, SuccessResult)
    assert "status" in result.data
