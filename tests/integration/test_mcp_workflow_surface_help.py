"""Acceptance: MCP Workflow Surface help lists thin commands only (C-016, C-022).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.hooks import register_ai_editor_commands
from mcp_proxy_adapter.commands.command_registry import CommandRegistry

EXPECTED_WORKFLOW_COMMANDS: frozenset[str] = frozenset(
    {
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_preview",
        "health",
    }
)

FORBIDDEN_LEGACY_COMMANDS: frozenset[str] = frozenset(
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
        "universal_file_save",
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

LEGACY_NAME_PREFIXES: tuple[str, ...] = (
    "session_",
    "subordinate_session_",
    "project_file_transfer_",
    "project_file_advisory_",
    "project_file_lock_",
    "session_git_",
)


def _registered_command_names() -> set[str]:
    """Return command names registered by editor hooks (MCP help surface)."""
    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    return set(reg.get_all_commands().keys())


def test_help_lists_universal_file_workflow_and_health_only() -> None:
    """C-022 (6) / C-016: help exposes exactly the thin workflow + health."""
    names = _registered_command_names()
    assert names == EXPECTED_WORKFLOW_COMMANDS, (
        "Editor MCP help surface must list only universal_file_* workflow commands "
        "and health; "
        f"expected={sorted(EXPECTED_WORKFLOW_COMMANDS)!r} "
        f"actual={sorted(names)!r} "
        f"extra={sorted(names - EXPECTED_WORKFLOW_COMMANDS)!r} "
        f"missing={sorted(EXPECTED_WORKFLOW_COMMANDS - names)!r}"
    )


def test_help_excludes_legacy_session_command_families() -> None:
    """C-020 / C-022 (6): no session_*, git, transfer, or legacy universal_file_* families."""
    names = _registered_command_names()
    overlap = names & FORBIDDEN_LEGACY_COMMANDS
    assert not overlap, (
        "Legacy or duplicate MCP command families must not appear in help: "
        f"{sorted(overlap)!r}"
    )
    for command_name in names:
        for prefix in LEGACY_NAME_PREFIXES:
            assert not command_name.startswith(
                prefix
            ), f"Command {command_name!r} matches forbidden legacy prefix {prefix!r}"
