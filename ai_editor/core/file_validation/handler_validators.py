"""
Handler-specific validators invoked after quality-tool checks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

import yaml

from ai_editor.core.cst_module.docstring_validator import validate_module_docstrings
from ai_editor.core.cst_module.utils import compile_module
from ai_editor.core.file_validation.results import ValidationResult
from ai_editor.core.file_handlers.registry import (
    HANDLER_INI,
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_TOML,
    HANDLER_YAML,
)

logger = logging.getLogger(__name__)


def _validate_python_handler(
    source_code: str,
    temp_file_path: Path,
    *,
    validate_docstrings: bool = True,
) -> Dict[str, ValidationResult]:
    results: Dict[str, ValidationResult] = {}

    compile_ok, compile_err = compile_module(source_code, str(temp_file_path))
    results["compile"] = ValidationResult(
        success=compile_ok,
        error_message=compile_err if not compile_ok else None,
        errors=[compile_err] if compile_err else [],
    )
    if not compile_ok:
        return results

    if validate_docstrings:
        doc_ok, doc_err, doc_errors = validate_module_docstrings(source_code)
        results["docstrings"] = ValidationResult(
            success=doc_ok,
            error_message=doc_err,
            errors=doc_errors,
        )
    else:
        results["docstrings"] = ValidationResult(
            success=True, error_message=None, errors=[]
        )
    return results


def _validate_json_handler(source_code: str) -> Dict[str, ValidationResult]:
    try:
        json.loads(source_code)
        return {
            "json_parse": ValidationResult(success=True, error_message=None, errors=[]),
        }
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON: {exc}"
        return {
            "json_parse": ValidationResult(
                success=False,
                error_message=msg,
                errors=[msg],
            ),
        }


def _validate_yaml_handler(source_code: str) -> Dict[str, ValidationResult]:
    try:
        yaml.safe_load(source_code)
        return {
            "yaml_parse": ValidationResult(success=True, error_message=None, errors=[]),
        }
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML: {exc}"
        return {
            "yaml_parse": ValidationResult(
                success=False,
                error_message=msg,
                errors=[msg],
            ),
        }


def _validate_ini_handler(source_code: str) -> Dict[str, ValidationResult]:
    try:
        from ai_editor.core.tree_temp.ini_source_parser import parse_ini_source

        parse_ini_source(source_code)
        return {
            "ini_parse": ValidationResult(success=True, error_message=None, errors=[]),
        }
    except (TypeError, ValueError) as exc:
        msg = f"Invalid INI: {exc}"
        return {
            "ini_parse": ValidationResult(
                success=False,
                error_message=msg,
                errors=[msg],
            ),
        }


def _validate_toml_handler(source_code: str) -> Dict[str, ValidationResult]:
    try:
        from ai_editor.core.tree_temp.toml_source_parser import parse_toml_source

        parse_toml_source(source_code)
        return {
            "toml_parse": ValidationResult(success=True, error_message=None, errors=[]),
        }
    except (TypeError, ValueError) as exc:
        msg = f"Invalid TOML: {exc}"
        return {
            "toml_parse": ValidationResult(
                success=False,
                error_message=msg,
                errors=[msg],
            ),
        }


def _validate_text_handler(_source_code: str) -> Dict[str, ValidationResult]:
    return {
        "text": ValidationResult(success=True, error_message=None, errors=[]),
    }


_HANDLER_RUNNERS = {
    HANDLER_PYTHON: _validate_python_handler,
    HANDLER_JSON: _validate_json_handler,
    HANDLER_YAML: _validate_yaml_handler,
    HANDLER_INI: _validate_ini_handler,
    HANDLER_TOML: _validate_toml_handler,
    HANDLER_TEXT: _validate_text_handler,
}


def run_handler_validator(
    handler_id: str,
    *,
    source_code: str,
    temp_file_path: Path,
    validate_docstrings: bool = True,
) -> Tuple[bool, str | None, Dict[str, ValidationResult]]:
    """Run the mandatory validator for the file handler type."""
    runner = _HANDLER_RUNNERS.get(handler_id)
    if runner is None:
        msg = f"No handler validator registered for {handler_id!r}"
        logger.warning(msg)
        return (
            False,
            msg,
            {
                "handler": ValidationResult(
                    success=False, error_message=msg, errors=[msg]
                ),
            },
        )

    if handler_id == HANDLER_PYTHON:
        results = _validate_python_handler(
            source_code,
            temp_file_path,
            validate_docstrings=validate_docstrings,
        )
    else:
        results = runner(source_code)

    if all(result.success for result in results.values()):
        return True, None, results

    parts: list[str] = []
    for name, result in results.items():
        if not result.success:
            if result.error_message:
                parts.append(f"{name}: {result.error_message}")
            elif result.errors:
                parts.append(f"{name}: {len(result.errors)} error(s)")
    return False, "; ".join(parts) if parts else "Handler validation failed", results
