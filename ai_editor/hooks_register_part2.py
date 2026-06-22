"""
Register universal file editing commands for AI Editor (preview, open, edit, write, close).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging

from mcp_proxy_adapter.commands.command_registry import registry

logger = logging.getLogger(__name__)


def register_commands_part2(reg: registry) -> None:
    """Register universal file preview and edit workflow commands."""
    try:
        from .commands.universal_file_preview_command import (
            UniversalFilePreviewCommand,
        )

        reg.register(UniversalFilePreviewCommand, "custom")
        logger.info("Registered universal_file_preview command")
    except ImportError as e:
        logger.warning("Failed to import universal_file_preview command: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register universal_file_preview command: %s",
            e,
            exc_info=True,
        )

    try:
        from .commands.universal_file_edit.open_command import UniversalFileOpenCommand
        from .commands.universal_file_edit.edit_command import UniversalFileEditCommand
        from .commands.universal_file_edit.write_command import (
            UniversalFileWriteCommand,
        )
        from .commands.universal_file_edit.close_command import (
            UniversalFileCloseCommand,
        )

        from ai_editor.commands.universal_file_edit.search_command import (
            UniversalFileSearchCommand,
        )
        from ai_editor.commands.universal_file_edit.node_at_line_command import (
            UniversalFileNodeAtLineCommand,
        )

        reg.register(UniversalFileOpenCommand, "custom")
        reg.register(UniversalFileEditCommand, "custom")
        reg.register(UniversalFileWriteCommand, "custom")
        reg.register(UniversalFileCloseCommand, "custom")
        reg.register(UniversalFileSearchCommand, "custom")
        reg.register(UniversalFileNodeAtLineCommand, "custom")
        logger.info("Registered universal_file_edit commands")
    except ImportError as e:
        logger.warning("Failed to import universal_file_edit commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register universal_file_edit commands: %s",
            e,
            exc_info=True,
        )
