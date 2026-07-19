"""Tests for run_quality_tools mypy config resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_editor.core.file_handlers.registry import HANDLER_PYTHON
from ai_editor.core.file_validation.quality_tools import run_quality_tools

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


def test_run_quality_tools_passes_mypy_config_from_project_root(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
    target = project_root / "sample.py"
    target.write_text("old\n", encoding="utf-8")
    temp_file = project_root / ".ai_editor_write_sample.py"
    temp_file.write_text(_VALID_PY, encoding="utf-8")
    expected_config = project_root / "pyproject.toml"

    with patch(
        "ai_editor.core.file_validation.quality_tools.type_check_with_mypy",
        return_value=(True, None, []),
    ) as mock_mypy:
        with patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_flake8",
            return_value=(True, None, []),
        ):
            with patch(
                "ai_editor.core.file_validation.quality_tools.lint_with_ruff",
                return_value=(True, None, []),
            ):
                ok, err, _ = run_quality_tools(
                    HANDLER_PYTHON,
                    temp_file_path=temp_file,
                    source_code=_VALID_PY,
                    project_root=project_root,
                )

    assert ok is True and err is None
    mock_mypy.assert_called_once()
    assert mock_mypy.call_args.kwargs["config_file"] == expected_config.resolve()
    assert mock_mypy.call_args.kwargs["project_root"] == project_root


def test_run_quality_tools_mypy_config_none_without_project_root(
    tmp_path: Path,
) -> None:
    temp_file = tmp_path / "sample.py"
    temp_file.write_text(_VALID_PY, encoding="utf-8")

    with patch(
        "ai_editor.core.file_validation.quality_tools.resolve_mypy_config_for_single_file",
        return_value=None,
    ) as mock_resolve:
        with patch(
            "ai_editor.core.file_validation.quality_tools.type_check_with_mypy",
            return_value=(True, None, []),
        ):
            with patch(
                "ai_editor.core.file_validation.quality_tools.lint_with_flake8",
                return_value=(True, None, []),
            ):
                with patch(
                    "ai_editor.core.file_validation.quality_tools.lint_with_ruff",
                    return_value=(True, None, []),
                ):
                    run_quality_tools(
                        HANDLER_PYTHON,
                        temp_file_path=temp_file,
                        source_code=_VALID_PY,
                    )

    mock_resolve.assert_called_once_with(temp_file)


def test_run_quality_tools_records_ruff_linter_result(tmp_path: Path) -> None:
    temp_file = tmp_path / "sample.py"
    temp_file.write_text(_VALID_PY, encoding="utf-8")

    with (
        patch(
            "ai_editor.core.file_validation.quality_tools.type_check_with_mypy",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_flake8",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_ruff",
            return_value=(False, "Found 1 ruff errors", ["sample.py:1:1: F401 unused"]),
        ),
    ):
        ok, err, results = run_quality_tools(
            HANDLER_PYTHON,
            temp_file_path=temp_file,
            source_code=_VALID_PY,
        )

    assert ok is False
    assert err == "ruff_linter: Found 1 ruff errors"
    assert results["linter"].success is True
    assert results["ruff_linter"].success is False
    assert results["type_checker"].success is True
