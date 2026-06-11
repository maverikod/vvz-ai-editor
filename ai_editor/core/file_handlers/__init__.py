"""
Extension-to-handler registry and typed file operations for universal file commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .base import (
    BaseFileHandler,
    ERROR_CODES,
    FileHandlerRequest,
    FileHandlerResult,
    SIDE_EFFECT_BLOCKED,
    STANDARD_HANDLER_ERROR_CODES,
    UNSUPPORTED_EXTENSION,
    UNSUPPORTED_OPERATION,
    VALIDATION_FAILED,
    standard_error_result,
    validate_before_side_effects,
)
from .json_handler import (
    JSON_SUFFIXES,
    JsonFileHandler,
    ensure_json_suffix,
    is_registered_json_suffix,
)
from .yaml_handler import (
    YAML_SUFFIXES,
    YamlFileHandler,
    ensure_yaml_suffix,
    is_registered_yaml_suffix,
)
from .registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    get_handler_schema,
    list_handler_mappings,
    resolve_handler,
    validate_supported,
)
from .python_handler import (
    PYTHON_SUFFIXES,
    PythonFileHandler,
    ensure_python_suffix,
    is_registered_python_suffix,
    read_python_lines_payload,
)
from .text_handler import (
    TEXT_SUFFIXES,
    TextFileHandler,
    persist_plain_text_file_metadata,
    read_lines_range_ok,
)

__all__ = [
    "ERROR_CODES",
    "STANDARD_HANDLER_ERROR_CODES",
    "SIDE_EFFECT_BLOCKED",
    "UNSUPPORTED_EXTENSION",
    "UNSUPPORTED_OPERATION",
    "VALIDATION_FAILED",
    "BaseFileHandler",
    "FileHandlerRequest",
    "FileHandlerResult",
    "HANDLER_JSON",
    "HANDLER_PYTHON",
    "HANDLER_TEXT",
    "HANDLER_YAML",
    "JSON_SUFFIXES",
    "PYTHON_SUFFIXES",
    "YAML_SUFFIXES",
    "JsonFileHandler",
    "PythonFileHandler",
    "YamlFileHandler",
    "ensure_json_suffix",
    "ensure_yaml_suffix",
    "ensure_python_suffix",
    "is_registered_json_suffix",
    "is_registered_python_suffix",
    "is_registered_yaml_suffix",
    "RegistryError",
    "get_handler_schema",
    "list_handler_mappings",
    "resolve_handler",
    "standard_error_result",
    "validate_before_side_effects",
    "validate_supported",
    "TEXT_SUFFIXES",
    "TextFileHandler",
    "persist_plain_text_file_metadata",
    "read_lines_range_ok",
    "read_python_lines_payload",
]
