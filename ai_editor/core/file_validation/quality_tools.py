"""
Quality-tool checks (flake8, mypy, black) on a temporary file before promotion.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional, Tuple

from ai_editor.core.code_quality.formatter import format_python_source_text
from ai_editor.core.code_quality.linter import lint_with_flake8
from ai_editor.core.code_quality.type_checker import (
    resolve_mypy_config_for_single_file,
    type_check_with_mypy,
)
from ai_editor.core.file_validation.results import ValidationResult
from ai_editor.core.file_handlers.registry import HANDLER_PYTHON

logger = logging.getLogger(__name__)


def _check_black_parseable(source_code: str) -> Tuple[bool, str | None, list[str]]:
    """Verify black can format the source (syntax OK); does not require pre-formatting."""
    _formatted, err = format_python_source_text(source_code)
    if err:
        return False, err, [err]
    return True, None, []


def run_quality_tools(
    handler_id: str,
    *,
    temp_file_path: Path,
    source_code: str,
    project_root: Optional[Path] = None,
) -> Tuple[bool, str | None, Dict[str, ValidationResult]]:
    """Run flake8, mypy, and black-format checks for Python files."""
    if handler_id != HANDLER_PYTHON:
        return True, None, {}

    results: Dict[str, ValidationResult] = {}
    t_start = time.perf_counter()

    black_ok, black_err, black_errors = _check_black_parseable(source_code)
    results["black"] = ValidationResult(
        success=black_ok,
        error_message=black_err,
        errors=black_errors,
    )
    if not black_ok:
        return False, black_err, results

    def _flake8_job() -> Tuple[Tuple[bool, str | None, list[str]], float]:
        t0 = time.perf_counter()
        return lint_with_flake8(temp_file_path, ignore=None), time.perf_counter() - t0

    mypy_probe = (
        project_root / "__init__.py" if project_root is not None else temp_file_path
    )
    mypy_config = resolve_mypy_config_for_single_file(mypy_probe)

    def _mypy_job() -> Tuple[Tuple[bool, str | None, list[str]], float]:
        t0 = time.perf_counter()
        return (
            type_check_with_mypy(
                temp_file_path,
                config_file=mypy_config,
                ignore_errors=False,
            ),
            time.perf_counter() - t0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_lint = pool.submit(_flake8_job)
        f_mypy = pool.submit(_mypy_job)
        (linter_ok, linter_err, linter_errors), lint_sec = f_lint.result()
        (mypy_ok, mypy_err, mypy_errors), mypy_sec = f_mypy.result()

    logger.info(
        "[PROFILE] run_quality_tools flake8=%.3fs mypy=%.3fs total=%.3fs",
        lint_sec,
        mypy_sec,
        time.perf_counter() - t_start,
    )
    results["linter"] = ValidationResult(
        success=linter_ok,
        error_message=linter_err,
        errors=linter_errors,
    )
    results["type_checker"] = ValidationResult(
        success=mypy_ok,
        error_message=mypy_err,
        errors=mypy_errors,
    )

    if linter_ok and mypy_ok:
        return True, None, results

    parts: list[str] = []
    for name, result in results.items():
        if not result.success and result.error_message:
            parts.append(f"{name}: {result.error_message}")
    return False, "; ".join(parts) if parts else "Quality checks failed", results
