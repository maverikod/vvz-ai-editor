"""MCP help surface lists only thin-workflow commands (C-016, C-022).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from ai_editor.hooks import register_ai_editor_commands
from mcp_proxy_adapter.commands.command_registry import CommandRegistry

EXPECTED: frozenset[str] = frozenset(
    {
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_preview",
        "health",
    }
)

FORBIDDEN: frozenset[str] = frozenset(
    {
        "session_create",
        "session_delete",
        "session_list",
        "session_view",
        "session_open_file",
        "session_close_file",
        "session_list_file_locks",
        "subordinate_session_create",
        "subordinate_session_delete",
        "subordinate_session_get",
        "subordinate_session_list",
        "subordinate_session_update",
        "project_file_transfer_download_begin",
        "project_file_transfer_upload_save",
        "project_file_advisory_lock_batch",
        "project_file_lock_status",
        "universal_file_move_nodes",
        "universal_file_search",
        "session_git_log",
        "session_git_diff",
        "session_git_show",
        "session_git_status",
        "session_git_revert",
        "session_undo",
        "session_redo",
        "session_write",
        "queue_health",
    }
)


def _registered_command_names() -> set[str]:
    """Return command names registered by editor hooks (MCP help surface)."""
    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    return set(reg.get_all_commands().keys())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected_command_registered(name: str) -> None:
    """Each thin-workflow command must appear in the MCP help registry."""
    assert (
        name in _registered_command_names()
    ), f"Expected command {name!r} missing from MCP help surface after G-006 cleanup"


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_removed_command_not_registered(name: str) -> None:
    """Legacy / duplicate families must not appear after G-006 unregister work."""
    assert (
        name not in _registered_command_names()
    ), f"Forbidden command {name!r} still registered on MCP help surface"


def test_help_surface_exactly_six_commands() -> None:
    """C-016: registry exposes exactly the six thin-workflow commands, no extras."""
    names = _registered_command_names()
    assert names == EXPECTED, (
        "Editor MCP help surface must list only universal_file_* workflow commands "
        "and health; "
        f"expected={sorted(EXPECTED)!r} "
        f"actual={sorted(names)!r} "
        f"extra={sorted(names - EXPECTED)!r} "
        f"missing={sorted(EXPECTED - names)!r}"
    )
