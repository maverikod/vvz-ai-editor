"""Regression tests for project-context draft validation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from ai_editor.commands.universal_file_edit.write_command_phases import (
    validate_draft_in_project_context,
)
from ai_editor.core.file_handlers.registry import HANDLER_PYTHON
from ai_editor.core.file_validation.results import ValidationResult


_VALID_DRAFT = '''
"""Draft module."""

from support import VALUE


def read_value() -> int:
    """Return the project-local value.

    Returns:
        The project-local value.
    """
    return VALUE
'''


def test_draft_imports_are_resolved_from_real_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
    (project_root / "support.py").write_text("VALUE: int = 7\n", encoding="utf-8")
    (tmp_path / "isolated").mkdir()
    target = tmp_path / "isolated" / "draft.py"

    def quality_in_project_context(
        handler_id: str,
        *,
        temp_file_path: Path,
        source_code: str,
        project_root: Path,
    ) -> tuple[bool, None, dict[str, ValidationResult]]:
        assert handler_id == HANDLER_PYTHON
        assert temp_file_path.is_relative_to(project_root)
        previous_path = sys.path[:]
        try:
            sys.path.insert(0, str(project_root))
            exec(compile(source_code, str(temp_file_path), "exec"), {})
        finally:
            sys.path[:] = previous_path
        return True, None, {}

    with patch(
        "ai_editor.core.file_validation.pre_write_pipeline.run_quality_tools",
        side_effect=quality_in_project_context,
    ) as mock_quality:
        outcome = validate_draft_in_project_context(
            HANDLER_PYTHON,
            source_code=_VALID_DRAFT,
            target_path=target,
            project_root=project_root,
        )

    assert outcome.success is True
    assert outcome.temp_path is not None
    quality_kwargs = mock_quality.call_args.kwargs
    staged_path = quality_kwargs["temp_file_path"]
    assert staged_path.is_relative_to(project_root)
    assert quality_kwargs["project_root"] == project_root.resolve()
    outcome.temp_path.unlink(missing_ok=True)


def test_real_diagnostics_still_fail_project_context_gate(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
    (tmp_path / "isolated").mkdir()
    target = tmp_path / "isolated" / "draft.py"

    with patch(
        "ai_editor.core.file_validation.pre_write_pipeline.run_quality_tools",
        return_value=(
            False,
            "type_checker: Found 1 mypy errors",
            {
                "type_checker": ValidationResult(
                    success=False,
                    error_message="Found 1 mypy errors",
                    errors=["draft.py:5:12: error: Incompatible return value"],
                )
            },
        ),
    ):
        outcome = validate_draft_in_project_context(
            HANDLER_PYTHON,
            source_code='''
"""Draft module."""


def read_value() -> int:
    """Return an invalid value."""
    return "wrong"
''',
            target_path=target,
            project_root=project_root,
        )

    assert outcome.success is False
    assert outcome.temp_path is None
    assert outcome.quality_results["type_checker"].success is False
