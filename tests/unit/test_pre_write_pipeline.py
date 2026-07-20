"""Tests for pre-write validation pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.core.file_handlers.registry import (
    HANDLER_INI,
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_TOML,
)
from ai_editor.core.file_validation.pre_write_pipeline import (
    validate_before_promote,
    validation_error_result,
)
from ai_editor.core.file_validation.results import ValidationResult

_VALID_PY = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def greet(name: str) -> str:
    """Return a greeting.

    Args:
        name: Person name.

    Returns:
        Greeting text.
    """
    return f"Hello, {name}"
'''


def test_validate_before_promote_python_success(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("old\n", encoding="utf-8")
    outcome = validate_before_promote(
        HANDLER_PYTHON,
        source_code=_VALID_PY,
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is True
    assert outcome.temp_path is not None
    assert outcome.temp_path.read_text(encoding="utf-8") == _VALID_PY
    outcome.temp_path.unlink(missing_ok=True)


def test_validate_before_promote_python_docstring_failure(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    bad_py = "def greet(name: str) -> str:\n    return name\n"
    outcome = validate_before_promote(
        HANDLER_PYTHON,
        source_code=bad_py,
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is False
    assert outcome.temp_path is None
    assert outcome.handler_results


def test_validate_before_promote_json_success(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    payload = json.dumps({"a": 1}, indent=2) + "\n"
    outcome = validate_before_promote(
        HANDLER_JSON,
        source_code=payload,
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is True
    if outcome.temp_path is not None:
        outcome.temp_path.unlink(missing_ok=True)


def test_validate_before_promote_json_failure(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    outcome = validate_before_promote(
        HANDLER_JSON,
        source_code="{bad",
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is False
    assert outcome.temp_path is None


@pytest.mark.parametrize(
    ("handler_id", "filename", "source_code"),
    [
        (HANDLER_INI, "settings.ini", "first = 1\n[server]\nhost: localhost\n"),
        (HANDLER_TOML, "settings.toml", 'first = 1\n[server]\nhost = "localhost"\n'),
    ],
)
def test_validate_before_promote_structured_config_success(
    tmp_path: Path,
    handler_id: str,
    filename: str,
    source_code: str,
) -> None:
    target = tmp_path / filename
    outcome = validate_before_promote(
        handler_id,
        source_code=source_code,
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is True
    if outcome.temp_path is not None:
        outcome.temp_path.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("handler_id", "filename", "source_code"),
    [
        (HANDLER_INI, "settings.ini", "first = 1\nnot a key\n"),
        (HANDLER_TOML, "settings.toml", 'first = "unterminated\n'),
    ],
)
def test_validate_before_promote_structured_config_failure(
    tmp_path: Path,
    handler_id: str,
    filename: str,
    source_code: str,
) -> None:
    target = tmp_path / filename
    outcome = validate_before_promote(
        handler_id,
        source_code=source_code,
        target_path=target,
        skip_quality_tools=True,
    )
    assert outcome.success is False
    assert outcome.temp_path is None
    assert outcome.handler_results


def test_validation_error_result_returns_all_errors() -> None:
    many = [f"error-{i}" for i in range(25)]
    err = validation_error_result(
        error_message="docstrings: 25 error(s)",
        quality_results={},
        handler_results={
            "docstrings": ValidationResult(
                success=False,
                error_message="docstrings: 25 error(s)",
                errors=many,
            ),
        },
    )
    details = err.details["validation_results"]["handler.docstrings"]
    assert len(details["errors"]) == 25


def test_validate_before_promote_text_skips_quality(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    outcome = validate_before_promote(
        HANDLER_TEXT,
        source_code="plain text\n",
        target_path=target,
    )
    assert outcome.success is True
    if outcome.temp_path is not None:
        outcome.temp_path.unlink(missing_ok=True)
