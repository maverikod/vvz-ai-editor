"""
Command registration hooks for ai-editor-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Import patch for CommandExecutionJob to support progress tracking
# This must be imported before CommandExecutionJob is used
from .core.command_execution_job_patch import patch_command_execution_job  # noqa: F401

from mcp_proxy_adapter.commands.hooks import register_custom_commands_hook
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import register_auto_import_module

from .hooks_register_part1 import register_commands_part1
from .hooks_register_part2 import register_commands_part2

_ADAPTER_DEMO_COMMANDS = frozenset({"echo", "job_status", "long_task"})


def _unregister_adapter_demo_commands(reg: registry) -> None:
    """Remove mcp_proxy_adapter built-in demo commands from the registry."""
    commands = getattr(reg, "_commands", None)
    command_types = getattr(reg, "_command_types", None)
    instances = getattr(reg, "_instances", None)
    for name in _ADAPTER_DEMO_COMMANDS:
        if commands is not None:
            commands.pop(name, None)
        if command_types is not None:
            command_types.pop(name, None)
        if instances is not None:
            instances.pop(name, None)


def register_ai_editor_commands(reg: registry) -> None:
    """Register AI Editor file-editing commands and minimal infrastructure.

    Args:
        reg: MCP command registry instance.

    Returns:
        None
    """
    register_commands_part1(reg)
    register_commands_part2(reg)
    from .commands.command_metadata_helpers import (
        apply_metadata_finalization_to_registry,
    )

    apply_metadata_finalization_to_registry(reg)
    _unregister_adapter_demo_commands(reg)


# Register hook
register_custom_commands_hook(register_ai_editor_commands)

# Register modules for auto-import in child processes (spawn mode).
register_auto_import_module("ai_editor.core.command_execution_job_patch")
register_auto_import_module("ai_editor.commands.universal_file_preview_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.open_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.edit_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.write_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.close_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.move_nodes_command")
register_auto_import_module("ai_editor.commands.universal_file_edit.search_command")
register_auto_import_module(
    "ai_editor.commands.universal_file_edit.node_at_line_command"
)
register_auto_import_module(
    "ai_editor.commands.universal_file_edit.session_undo_command"
)
register_auto_import_module(
    "ai_editor.commands.universal_file_edit.session_redo_command"
)
register_auto_import_module(
    "ai_editor.commands.universal_file_edit.session_write_command"
)
