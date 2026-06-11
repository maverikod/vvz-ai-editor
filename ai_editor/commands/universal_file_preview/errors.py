"""
Error classification constants and helpers for universal_file_preview.

Defines three error classes (C-014):
  Class 1 — input errors (INPUT_ERROR_* constants)
  Class 2 — file-structure errors (FILE_STRUCTURE_ERROR constant)
  Class 3 — handler-internal errors (HANDLER_ERROR constant)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Class 1 — input error codes
INPUT_ERROR_INVALID_SELECTOR_FORM = "INVALID_SELECTOR_FORM"
INPUT_ERROR_MIXED_SELECTOR_LIST = "MIXED_SELECTOR_LIST"
INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY = "DUPLICATE_SELECTOR_ENTRY"
INPUT_ERROR_OUT_OF_RANGE_INDEX = "OUT_OF_RANGE_INDEX"
INPUT_ERROR_UNKNOWN_IDENTIFIER = "UNKNOWN_IDENTIFIER"
INPUT_ERROR_SELECTOR_ON_EMPTY = "SELECTOR_ON_EMPTY"
INPUT_ERROR_UNKNOWN_EXTENSION = "UNKNOWN_EXTENSION"
INPUT_ERROR_UNKNOWN_NODE_REF = "UNKNOWN_NODE_REF"
INPUT_ERROR_CONFLICTING_PARAMETERS = "CONFLICTING_PARAMETERS"
INPUT_ERROR_REQUIRES_LINE_ADDRESSING = "REQUIRES_LINE_ADDRESSING"
INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING = "REQUIRES_IDENTIFIER_ADDRESSING"
INPUT_ERROR_GLOB_IN_FILE_PATH = "GLOB_IN_FILE_PATH"
# Class 2
FILE_STRUCTURE_ERROR = "FILE_STRUCTURE_ERROR"
# Class 3
HANDLER_ERROR = "HANDLER_ERROR"


@dataclass
class PreviewError:
    """
    Structured error produced by the preview pipeline.

    Attributes:
        error_class: One of 'input', 'file_structure', 'handler_internal'.
        code: Deterministic error code string (one of the constants above).
        message: Human-readable description.
        details: Optional extra payload (parser name, line range, handler name).
    """

    error_class: str
    code: str
    message: str
    details: dict[str, Any] | None = None


def input_error(
    code: str, message: str, details: dict[str, Any] | None = None
) -> PreviewError:
    """Create a Class-1 (input) PreviewError."""
    return PreviewError(
        error_class="input", code=code, message=message, details=details
    )


def file_structure_error(
    parser: str,
    message: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> PreviewError:
    """Create a Class-2 (file-structure) PreviewError."""
    details: dict[str, Any] = {"parser": parser}
    if line_start is not None:
        details["line_start"] = line_start
    if line_end is not None:
        details["line_end"] = line_end
    return PreviewError(
        error_class="file_structure",
        code=FILE_STRUCTURE_ERROR,
        message=message,
        details=details,
    )


def handler_error(handler_name: str, message: str) -> PreviewError:
    """Create a Class-3 (handler-internal) PreviewError."""
    return PreviewError(
        error_class="handler_internal",
        code=HANDLER_ERROR,
        message=message,
        details={"handler": handler_name},
    )
