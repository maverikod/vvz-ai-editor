"""Universal file save command package."""

from __future__ import annotations

from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.file_handlers.text_handler import (
    persist_plain_text_file_metadata,
)
from ai_editor.core.git_integration import commit_after_write

from ai_editor.commands.universal_file_save_command.save_command import (
    UniversalFileSaveCommand,
)

__all__ = [
    "BackupManager",
    "UniversalFileSaveCommand",
    "commit_after_write",
    "persist_plain_text_file_metadata",
]
