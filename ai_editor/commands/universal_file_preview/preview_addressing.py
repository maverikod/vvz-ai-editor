"""
Preview addressing mode: identifier navigation vs invalid-source line pagination.

Normal (parseable) files: node_ref / selector only.
Invalid-source fallback: preview_offset / max_chars over raw text only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_editor.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
)

from .base_handler import FileHandler
from .errors import (
    INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING,
    INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
    PreviewError,
    input_error,
)
from .marked_tree_loader import _read_source_text, resolve_format_handler
from .node_ref_params import normalize_optional_node_ref

_PYTHON_EXTENSIONS = frozenset({".py", ".pyi", ".pyw"})
_ALWAYS_PARSEABLE_EXTENSIONS = frozenset(
    {".md", ".txt", ".rst", ".adoc", ".jsonl", ".ndjson"}
)


def uses_identifier_addressing(params: dict[str, Any]) -> bool:
    """True when the caller navigates by node_ref or selector (all formats)."""
    if normalize_optional_node_ref(params.get("node_ref")) is not None:
        return True
    selector = params.get("selector")
    if selector is None:
        return False
    if isinstance(selector, list) and not selector:
        return False
    return True


def uses_line_fallback_addressing(params: dict[str, Any]) -> bool:
    """True when the caller requests invalid-source char pagination."""
    return int(params.get("preview_offset") or 0) > 0


def preview_source_is_parseable(file_path: Path) -> bool:
    """Return False when whole-file structural parse would fail (all formats)."""
    if not file_path.is_file():
        return True
    content = _read_source_text(preview_abs_path=file_path)
    if not content.strip():
        return True
    ext = file_path.suffix.lower()
    if ext in _ALWAYS_PARSEABLE_EXTENSIONS:
        return True
    if ext in _PYTHON_EXTENSIONS:
        try:
            import libcst as cst

            cst.parse_module(content)
            return True
        except Exception:
            return False
    if ext == ".json":
        try:
            json.loads(content)
            return True
        except json.JSONDecodeError:
            return False
    if ext in {".yaml", ".yml"}:
        try:
            resolve_format_handler(file_path).parse_content(file_path, content)
            return True
        except Exception:
            return False
    return True


def check_preview_addressing(
    *,
    parseable: bool,
    params: dict[str, Any],
    file_path: str,
) -> PreviewError | None:
    """Reject identifier vs line-pagination mismatch before navigation."""
    if parseable and uses_line_fallback_addressing(params):
        return input_error(
            INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING,
            (
                "File parsed successfully. Use identifier-based preview "
                "(node_ref / selector from a prior response), not preview_offset. "
                + mode_notice_text(False)
            ),
            details={"file_path": file_path},
        )
    if not parseable and uses_identifier_addressing(params):
        return input_error(
            INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
            (
                "File has parse errors. Use line-based preview pagination "
                "(preview_offset and max_chars at file root), not node_ref or selector. "
                + mode_notice_text(True)
            ),
            details={"file_path": file_path},
        )
    return None


def parse_error_from_focus(focus_attributes: dict[str, Any] | None) -> str | None:
    """Extract parse_error text from an invalid-source focus node."""
    if not focus_attributes:
        return None
    raw = focus_attributes.get("parse_error")
    return str(raw) if raw is not None else None
