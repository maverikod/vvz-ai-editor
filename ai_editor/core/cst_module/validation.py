"""
Validation module for CST file operations.

Validates entire file in temporary file before applying changes.
Includes compilation, linting, type checking, and docstring validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import compile_module
from .docstring_validator import validate_module_docstrings
from ..code_quality.linter import lint_with_flake8
from ..code_quality.type_checker import type_check_with_mypy

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a single validation step."""

    success: bool
    error_message: Optional[str] = None
    errors: List[str] = field(default_factory=list)


def validate_file_in_temp(
    source_code: str,
    temp_file_path: Path,
    validate_linter: bool = True,
    validate_type_checker: bool = True,
    validate_docstrings: bool = True,
) -> Tuple[bool, Optional[str], Dict[str, ValidationResult]]:
    """
    Validate entire file in temporary file.

    Performs comprehensive validation:
    1. Compilation check (syntax validation)
    2. Docstring validation (optional)
    3. Linter check (flake8) - optional
    4. Type checker (mypy) - optional

    When both linter and type checker are enabled, steps 3 and 4 run in parallel
    (separate subprocesses) so wall time is roughly max(flake8, mypy) instead of sum.

    Args:
        source_code: Full source code of the file
        temp_file_path: Path to temporary file where source_code is written
        validate_linter: Whether to run linter (flake8)
        validate_type_checker: Whether to run type checker (mypy)
        validate_docstrings: Whether to run docstring policy checks (return hints, etc.)

    Returns:
        Tuple of (overall_success, error_message, results_dict)
        - overall_success: True if all validations passed
        - error_message: Combined error message if validation failed
        - results_dict: Dictionary with ValidationResult for each validation type:
          {
              "compile": ValidationResult,
              "docstrings": ValidationResult,
              "linter": ValidationResult,  # if validate_linter=True
              "type_checker": ValidationResult,  # if validate_type_checker=True
          }
    """
    results: Dict[str, ValidationResult] = {}
    t_start = time.perf_counter()
    t_prev = t_start

    # Ensure temporary file exists and contains source_code
    try:
        temp_file_path.write_text(source_code, encoding="utf-8")
    except Exception as e:
        error_msg = f"Failed to write temporary file: {e}"
        logger.error(error_msg)
        return (
            False,
            error_msg,
            {
                "compile": ValidationResult(
                    success=False, error_message=error_msg, errors=[error_msg]
                )
            },
        )

    # 1. Compilation check
    compile_success, compile_error = compile_module(source_code, str(temp_file_path))
    _t = time.perf_counter()
    logger.info("[PROFILE] validate_file_in_temp compile elapsed=%.3fs", _t - t_prev)
    t_prev = _t
    results["compile"] = ValidationResult(
        success=compile_success,
        error_message=compile_error if not compile_success else None,
        errors=[compile_error] if compile_error else [],
    )

    if not compile_success:
        # If compilation fails, skip other validations
        error_msg = f"Compilation failed: {compile_error}"
        logger.warning(error_msg)
        return (False, error_msg, results)

    # 2. Docstring validation
    if validate_docstrings:
        docstring_success, docstring_error, docstring_errors = (
            validate_module_docstrings(source_code)
        )
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] validate_file_in_temp docstrings elapsed=%.3fs", _t - t_prev
        )
        t_prev = _t
        results["docstrings"] = ValidationResult(
            success=docstring_success,
            error_message=docstring_error,
            errors=docstring_errors,
        )
    else:
        results["docstrings"] = ValidationResult(
            success=True, error_message=None, errors=[]
        )

    # 3–4. Linter and/or type checker (optional); run both in parallel when both on.
    if validate_linter and validate_type_checker:
        t_parallel = time.perf_counter()

        def _flake8_job() -> Tuple[Tuple[bool, Optional[str], List[str]], float]:
            t0 = time.perf_counter()
            return (
                lint_with_flake8(temp_file_path, ignore=None),
                time.perf_counter() - t0,
            )

        def _mypy_job() -> Tuple[Tuple[bool, Optional[str], List[str]], float]:
            t0 = time.perf_counter()
            return (
                type_check_with_mypy(
                    temp_file_path, config_file=None, ignore_errors=False
                ),
                time.perf_counter() - t0,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_lint = pool.submit(_flake8_job)
            f_mypy = pool.submit(_mypy_job)
            (linter_success, linter_error, linter_errors), lint_sec = f_lint.result()
            (type_check_success, type_check_error, type_check_errors), mypy_sec = (
                f_mypy.result()
            )

        _t = time.perf_counter()
        logger.info(
            "[PROFILE] validate_file_in_temp flake8 elapsed=%.3fs (parallel)",
            lint_sec,
        )
        logger.info(
            "[PROFILE] validate_file_in_temp mypy elapsed=%.3fs (parallel)",
            mypy_sec,
        )
        logger.info(
            "[PROFILE] validate_file_in_temp flake8_mypy_parallel_wall elapsed=%.3fs",
            _t - t_parallel,
        )
        t_prev = _t
        results["linter"] = ValidationResult(
            success=linter_success,
            error_message=linter_error,
            errors=linter_errors,
        )
        results["type_checker"] = ValidationResult(
            success=type_check_success,
            error_message=type_check_error,
            errors=type_check_errors,
        )
    else:
        if validate_linter:
            linter_success, linter_error, linter_errors = lint_with_flake8(
                temp_file_path, ignore=None
            )
            _t = time.perf_counter()
            logger.info(
                "[PROFILE] validate_file_in_temp flake8 elapsed=%.3fs", _t - t_prev
            )
            t_prev = _t
            results["linter"] = ValidationResult(
                success=linter_success,
                error_message=linter_error,
                errors=linter_errors,
            )
        else:
            results["linter"] = ValidationResult(
                success=True, error_message=None, errors=[]
            )

        if validate_type_checker:
            type_check_success, type_check_error, type_check_errors = (
                type_check_with_mypy(
                    temp_file_path, config_file=None, ignore_errors=False
                )
            )
            _t = time.perf_counter()
            logger.info(
                "[PROFILE] validate_file_in_temp mypy elapsed=%.3fs", _t - t_prev
            )
            t_prev = _t
            results["type_checker"] = ValidationResult(
                success=type_check_success,
                error_message=type_check_error,
                errors=type_check_errors,
            )
        else:
            results["type_checker"] = ValidationResult(
                success=True, error_message=None, errors=[]
            )

    # Determine overall success
    overall_success = all(result.success for result in results.values())

    # Build combined error message
    error_message = None
    if not overall_success:
        error_parts = []
        for validation_type, result in results.items():
            if not result.success:
                if result.error_message:
                    error_parts.append(f"{validation_type}: {result.error_message}")
                elif result.errors:
                    error_parts.append(
                        f"{validation_type}: {len(result.errors)} error(s)"
                    )
        error_message = "; ".join(error_parts) if error_parts else "Validation failed"

    logger.info(
        "[PROFILE] validate_file_in_temp total elapsed=%.3fs",
        time.perf_counter() - t_start,
    )
    logger.debug(
        f"Validation completed: success={overall_success}, "
        f"results={[(k, v.success) for k, v in results.items()]}"
    )

    return (overall_success, error_message, results)
