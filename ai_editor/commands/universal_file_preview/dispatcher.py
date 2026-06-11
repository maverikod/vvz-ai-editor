"""
HandlerDispatcher — routes file_path to a FileHandler by extension (C-002).

One extension maps to exactly one FileHandler. Unknown extension
produces UNKNOWN_EXTENSION error (C-014). Adding a new handler does
not change the public command schema.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base_handler import FileHandler
from .errors import PreviewError, input_error, INPUT_ERROR_UNKNOWN_EXTENSION
from .handlers.json_handler import JsonFileHandler
from .handlers.jsonl_handler import JsonLinesFileHandler
from .handlers.markdown_handler import MarkdownFileHandler
from .handlers.python_marked_handler import PythonMarkedTreeHandler
from .handlers.text_handler import TextFileHandler
from .handlers.yaml_handler import YamlFileHandler

logger = logging.getLogger(__name__)


class HandlerDispatcher:
    """
    Routes file_path to a FileHandler (C-003) by extension (C-002).

    Dispatch key is the file extension (case-insensitive, via
    pathlib.Path.suffix.lower()). Each extension maps to exactly one
    handler instance. Unknown extension produces UNKNOWN_EXTENSION input
    error (C-014).

    Attributes:
        _registry: dict[str, FileHandler] — mapping of lowercase extension
                 string to the registered FileHandler instance.
    """

    def __init__(self) -> None:
        """Initialise dispatcher with the default extension-to-handler registry."""
        self._registry: dict[str, FileHandler] = {
            ".py": PythonMarkedTreeHandler(),
            ".pyi": PythonMarkedTreeHandler(),
            ".pyw": PythonMarkedTreeHandler(),
            ".md": MarkdownFileHandler(),
            ".txt": TextFileHandler(),
            ".rst": TextFileHandler(),
            ".adoc": TextFileHandler(),
            ".json": JsonFileHandler(),
            ".jsonl": JsonLinesFileHandler(),
            ".ndjson": JsonLinesFileHandler(),
            ".yaml": YamlFileHandler(),
            ".yml": YamlFileHandler(),
        }

    def dispatch(self, file_path: str) -> FileHandler | PreviewError:
        """
        Resolve the FileHandler for the given file_path by extension.

        Extension matching is case-insensitive. Does not read file content.

        Args:
            file_path: Project-relative path string.

        Returns:
            FileHandler instance, or PreviewError(UNKNOWN_EXTENSION) when
            the extension has no registered handler.
        """
        ext = Path(file_path).suffix.lower()
        handler = self._registry.get(ext)
        if handler is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_EXTENSION,
                f"No handler registered for extension {ext!r} in {file_path!r}.",
                details={"extension": ext, "file_path": file_path},
            )
        return handler
