"""Central registry resolving SourceFile paths to FormatHandler by extension (C-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from ai_editor.tree.format_handler import FormatHandler


class HandlerNotFoundError(KeyError):
    """Raised when no FormatHandler is registered for a file extension."""

    def __init__(self, extension: str) -> None:
        super().__init__(f"No FormatHandler registered for extension {extension!r}")
        self.extension: str = extension


class HandlerRegistry:
    """Central registry resolving a file to its FormatHandler by extension (C-008).

    Sole resolution path from a source file path to its FormatHandler.
    No caller may bypass the registry to select a handler directly.
    """

    def __init__(self) -> None:
        """Initialise with an empty handler map."""
        self._handlers: Dict[str, FormatHandler] = {}

    def register(self, extension: str, handler: FormatHandler) -> None:
        """Register a FormatHandler for a file extension.

        Args:
            extension: File extension including the leading dot (e.g. ".py").
            handler: The FormatHandler instance to register.

        Raises:
            ValueError: If extension does not start with a dot.
        """
        if not extension.startswith("."):
            raise ValueError(f"Extension must start with a dot; got {extension!r}")
        self._handlers[extension] = handler

    def resolve(self, file_path: Path) -> FormatHandler:
        """Return the FormatHandler registered for the file's extension.

        Args:
            file_path: Path whose suffix selects the handler.

        Returns:
            The registered FormatHandler for this extension.

        Raises:
            HandlerNotFoundError: If no handler is registered for file_path.suffix.
        """
        ext = file_path.suffix
        if ext not in self._handlers:
            raise HandlerNotFoundError(ext)
        return self._handlers[ext]

    def extensions(self) -> list[str]:
        """Return sorted list of registered file extensions."""
        return sorted(self._handlers.keys())

    def __contains__(self, extension: str) -> bool:
        """Return True if a handler is registered for the extension."""
        return extension in self._handlers

    @classmethod
    def default_registry(cls) -> HandlerRegistry:
        """Return a HandlerRegistry with all five format handlers registered (C-008).

        Registers:
          .txt, .rst  -> TextHandler (shared instance)
          .md         -> MarkdownHandler
          .yaml, .yml -> YamlHandler (shared instance)
          .json       -> JsonHandler
          .py         -> PythonHandler

        Sole bootstrap for extension-keyed handler resolution. Callers must use
        HandlerRegistry.default_registry() or manual register(); direct handler
        selection bypassing the registry is forbidden.
        """
        from ai_editor.tree.handlers import (
            JsonHandler,
            MarkdownHandler,
            PythonHandler,
            TextHandler,
            YamlHandler,
        )

        registry = cls()
        text_handler = TextHandler()
        registry.register(".txt", text_handler)
        registry.register(".rst", text_handler)
        registry.register(".md", MarkdownHandler())
        yaml_handler = YamlHandler()
        registry.register(".yaml", yaml_handler)
        registry.register(".yml", yaml_handler)
        registry.register(".json", JsonHandler())
        registry.register(".py", PythonHandler())
        return registry
