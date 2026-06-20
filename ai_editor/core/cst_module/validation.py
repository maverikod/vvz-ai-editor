"""
Validation module for CST file operations.

Validates entire file in temporary file before applying changes.
Delegates to the shared pre-write pipeline (quality tools, then handler validators).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from ai_editor.core.cst_module.utils import compile_module
from ai_editor.core.cst_module.docstring_validator import validate_module_docstrings
from ai_editor.core.file_handlers.registry import HANDLER_PYTHON
from ai_editor.core.file_validation.handler_validators import run_handler_validator
from ai_editor.core.file_validation.quality_tools import run_quality_tools
from ai_editor.core.file_validation.results import ValidationResult

logger = logging.getLogger(__name__)

# Re-export for backward compatibility.
__all__ = ["ValidationResult", "validate_file_in_temp"]


def _from_pipeline_result(result: ValidationResult) -> ValidationResult:
    return ValidationResult(
        success=result.success,
        error_message=result.error_message,
        errors=list(result.errors),
    )


def validate_file_in_temp(
    source_code: str,
    temp_file_path: Path,
    validate_linter: bool = True,
    validate_type_checker: bool = True,
    validate_docstrings: bool = True,
) -> Tuple[bool, Optional[str], Dict[str, ValidationResult]]:
    """
    Validate entire file in temporary file.

    Order:
    1. Quality tools (flake8, mypy, black) when enabled for Python.
    2. Handler validator (compile + docstrings for Python).
    """
    t_start = time.perf_counter()
    results: Dict[str, ValidationResult] = {}

    try:
        temp_file_path.write_text(source_code, encoding="utf-8")
    except Exception as exc:
        error_msg = f"Failed to write temporary file: {exc}"
        logger.error(error_msg)
        return (
            False,
            error_msg,
            {
                "compile": ValidationResult(
                    success=False,
                    error_message=error_msg,
                    errors=[error_msg],
                )
            },
        )

    run_quality = validate_linter or validate_type_checker
    if run_quality:
        quality_ok, quality_err, quality_results = run_quality_tools(
            HANDLER_PYTHON,
            temp_file_path=temp_file_path,
            source_code=source_code,
        )
        for name, item in quality_results.items():
            if name == "linter" and not validate_linter:
                results["linter"] = ValidationResult(success=True, errors=[])
                continue
            if name == "type_checker" and not validate_type_checker:
                results["type_checker"] = ValidationResult(success=True, errors=[])
                continue
            results[name] = _from_pipeline_result(item)
        if not quality_ok:
            skipped = {
                k: ValidationResult(success=True, errors=[])
                for k in ("linter", "type_checker", "black")
                if k not in results
            }
            results.update(skipped)
            logger.info(
                "[PROFILE] validate_file_in_temp quality failed elapsed=%.3fs",
                time.perf_counter() - t_start,
            )
            return False, quality_err, results
    else:
        results["linter"] = ValidationResult(success=True, errors=[])
        results["type_checker"] = ValidationResult(success=True, errors=[])
        results["black"] = ValidationResult(success=True, errors=[])

    if validate_docstrings:
        handler_ok, handler_err, handler_results = run_handler_validator(
            HANDLER_PYTHON,
            source_code=source_code,
            temp_file_path=temp_file_path,
        )
        for name, item in handler_results.items():
            results[name] = _from_pipeline_result(item)
        if not handler_ok:
            logger.info(
                "[PROFILE] validate_file_in_temp handler failed elapsed=%.3fs",
                time.perf_counter() - t_start,
            )
            return False, handler_err, results
    else:
        compile_ok, compile_err = compile_module(source_code, str(temp_file_path))
        results["compile"] = ValidationResult(
            success=compile_ok,
            error_message=compile_err if not compile_ok else None,
            errors=[compile_err] if compile_err else [],
        )
        results["docstrings"] = ValidationResult(success=True, errors=[])
        if not compile_ok:
            return False, compile_err, results

    overall = all(result.success for result in results.values())
    logger.info(
        "[PROFILE] validate_file_in_temp total elapsed=%.3fs success=%s",
        time.perf_counter() - t_start,
        overall,
    )
    return overall, None, results
