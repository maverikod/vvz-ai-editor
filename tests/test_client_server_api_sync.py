"""Ensure client facade commands match the in-process server command registry."""

from __future__ import annotations

import pytest
import pytest_asyncio

import ai_editor.hooks  # noqa: F401
from ai_editor_client.server_api import (
    assert_facade_commands_registered,
    assert_removed_commands_absent,
)
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_server_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


def test_client_facade_commands_registered_on_server() -> None:
    assert_facade_commands_registered(registry.get_command)


def test_removed_commands_absent_from_server() -> None:
    assert_removed_commands_absent(registry.get_command)
