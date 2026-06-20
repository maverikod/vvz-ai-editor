"""
Pre-write validation pipeline for universal file commands.

Order:
1. Write serialized source to a temporary file (caller supplies canonical text).
2. Run quality tools (flake8, mypy, black) on the temp file for Python.
3. Run handler-specific validator (docstrings, JSON/YAML parse, etc.).
4. On success the caller promotes the temp file or proceeds with upload.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.core.file_validation.results import ValidationResult

from .handler_validators import run_handler_validator
from .quality_tools import run_quality_tools


@dataclass
class PreWriteValidationOutcome:
    """Result of validate_before_promote."""

    success: bool
    temp_path: Optional[Path] = None
    error_message: Optional[str] = None
    quality_results: Dict[str, ValidationResult] = field(default_factory=dict)
    handler_results: Dict[str, ValidationResult] = field(default_factory=dict)


def write_source_to_temp(source_code: str, target_path: Path) -> Path:
    """Write canonical source beside the target path; return temp path."""
    fd, temp_path_str = tempfile.mkstemp(
        suffix=target_path.suffix or ".tmp",
        prefix=".ai_editor_write_",
        dir=str(target_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(source_code)
    except Exception:
        os.close(fd)
        Path(temp_path_str).unlink(missing_ok=True)
        raise
    return Path(temp_path_str)


def _cleanup_temp(temp_path: Optional[Path]) -> None:
    if temp_path is not None:
        temp_path.unlink(missing_ok=True)


def _merge_validation_details(
    quality: Mapping[str, ValidationResult],
    handler: Mapping[str, ValidationResult],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for phase, results in (("quality", quality), ("handler", handler)):
        for name, result in results.items():
            merged[f"{phase}.{name}"] = {
                "success": result.success,
                "error_message": result.error_message,
                "errors": list(result.errors),
            }
    return merged


def validation_error_result(
    *,
    error_message: str,
    quality_results: Mapping[str, ValidationResult],
    handler_results: Mapping[str, ValidationResult],
) -> ErrorResult:
    return ErrorResult(
        message=f"Validation failed: {error_message}",
        code=cast(Any, "VALIDATION_ERROR"),
        details={
            "error": error_message,
            "validation_results": _merge_validation_details(
                quality_results,
                handler_results,
            ),
        },
    )


def validate_before_promote(
    handler_id: str,
    *,
    source_code: str,
    target_path: Path,
    skip_quality_tools: bool = False,
    validate_docstrings: bool = True,
) -> PreWriteValidationOutcome:
    """
    Write temp file and run quality + handler validation.

    On failure the temp file is removed. On success ``temp_path`` is returned for
    the caller to promote with :func:`promote_temp_to_target`.

    There is no cap on source file size (bytes or lines); validation runs on the
    full serialized content written to the temp file.
    """
    temp_path: Optional[Path] = None
    try:
        temp_path = write_source_to_temp(source_code, target_path)
    except OSError as exc:
        return PreWriteValidationOutcome(
            success=False,
            error_message=f"Failed to write temporary file: {exc}",
        )

    quality_ok, quality_err, quality_results = True, None, {}
    if not skip_quality_tools:
        quality_ok, quality_err, quality_results = run_quality_tools(
            handler_id,
            temp_file_path=temp_path,
            source_code=source_code,
        )
    if not quality_ok:
        _cleanup_temp(temp_path)
        return PreWriteValidationOutcome(
            success=False,
            error_message=quality_err or "Quality checks failed",
            quality_results=quality_results,
        )

    handler_ok, handler_err, handler_results = run_handler_validator(
        handler_id,
        source_code=source_code,
        temp_file_path=temp_path,
        validate_docstrings=validate_docstrings,
    )
    if not handler_ok:
        _cleanup_temp(temp_path)
        return PreWriteValidationOutcome(
            success=False,
            error_message=handler_err or "Handler validation failed",
            quality_results=quality_results,
            handler_results=handler_results,
        )

    return PreWriteValidationOutcome(
        success=True,
        temp_path=temp_path,
        quality_results=quality_results,
        handler_results=handler_results,
    )


def promote_temp_to_target(temp_path: Path, target_path: Path) -> None:
    """Atomically replace the target file with the validated temp file."""
    os.replace(str(temp_path), str(target_path))
