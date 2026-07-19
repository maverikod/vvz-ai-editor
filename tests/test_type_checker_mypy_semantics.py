"""
Mypy subprocess semantics: non-zero exit vs filtered / attributed errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

from ai_editor.commands.universal_file_edit.write_command_phases import (
    validate_draft_in_project_context,
)
from ai_editor.core.code_quality.type_checker import (
    resolve_mypy_config_for_single_file,
    type_check_project_with_mypy,
    type_check_with_mypy,
)
from ai_editor.core.file_handlers.registry import HANDLER_PYTHON
from ai_editor.core.file_validation.results import ValidationResult

_PROJECT_CONTEXT_DRAFT = '''
"""Draft module validated in the project context."""

from support import VALUE


def read_value() -> int:
    """Return the project-local value.

    Returns:
        The project-local value.
    """
    return VALUE
'''


def test_write_path_mypy_uses_project_context_for_draft_imports(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    config = project_root / "pyproject.toml"
    config.write_text("[tool.mypy]\n", encoding="utf-8")
    (project_root / "support.py").write_text("VALUE: int = 7\n", encoding="utf-8")
    target = tmp_path / "isolated" / "draft.py"
    target.parent.mkdir()
    observed: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        staged_target = Path(cmd[1])
        effective_config = Path(cmd[cmd.index("--config-file") + 1])
        observed.update(
            target=staged_target,
            config=effective_config,
            cwd=Path(kwargs["cwd"]),
            pythonpath=kwargs["env"].get("PYTHONPATH"),
            source=staged_target.read_text(encoding="utf-8"),
        )
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_flake8",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_ruff",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.code_quality.type_checker.subprocess.run",
            fake_run,
        ),
    ):
        outcome = validate_draft_in_project_context(
            HANDLER_PYTHON,
            source_code=_PROJECT_CONTEXT_DRAFT,
            target_path=target,
            project_root=project_root,
        )

    assert outcome.success is True
    assert observed["target"].is_relative_to(project_root)
    assert observed["source"] == _PROJECT_CONTEXT_DRAFT
    assert observed["config"] == config.resolve()
    assert observed["cwd"] == project_root.resolve()
    assert observed["pythonpath"] is None
    assert outcome.temp_path is not None
    outcome.temp_path.unlink(missing_ok=True)


def test_write_path_preserves_genuine_mypy_validation_error(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
    target = tmp_path / "isolated" / "draft.py"
    observed: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        staged_target = Path(cmd[1]).resolve()
        observed["target"] = staged_target
        line = f"{staged_target}:5: error: Incompatible return value"
        return CompletedProcess(cmd, 1, stdout=line + "\n", stderr="")

    with (
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_flake8",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.file_validation.quality_tools.lint_with_ruff",
            return_value=(True, None, []),
        ),
        patch(
            "ai_editor.core.code_quality.type_checker.subprocess.run",
            fake_run,
        ),
    ):
        outcome = validate_draft_in_project_context(
            HANDLER_PYTHON,
            source_code=_PROJECT_CONTEXT_DRAFT,
            target_path=target,
            project_root=project_root,
        )

    assert outcome.success is False
    assert outcome.error_message == "type_checker: Found 1 mypy errors"
    type_checker_result = outcome.quality_results["type_checker"]
    assert isinstance(type_checker_result, ValidationResult)
    assert type_checker_result.success is False
    assert type_checker_result.error_message == "Found 1 mypy errors"
    assert type_checker_result.errors == [
        f"{observed['target']}:5: error: Incompatible return value"
    ]


def test_type_check_success_when_mypy_fails_only_other_files(tmp_path) -> None:
    """Non-zero mypy exit with no error lines for the target file => success."""
    target = tmp_path / "good.py"
    target.write_text("x = 1\n")
    other = tmp_path / "bad.py"
    other.write_text("y = 1\n")
    line = f"{other.resolve()}:1: error: Incompatible types in assignment"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 1, stdout=line + "\n", stderr="")

    with patch("ai_editor.core.code_quality.type_checker.subprocess.run", fake_run):
        ok, err, errs = type_check_with_mypy(target)

    assert ok is True
    assert err is None
    assert errs == []


def test_type_check_failure_when_target_file_has_errors(tmp_path) -> None:
    target = tmp_path / "bad.py"
    target.write_text("x: str = 1\n")
    line = f"{target.resolve()}:1: error: Incompatible types in assignment"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 1, stdout=line + "\n", stderr="")

    with patch("ai_editor.core.code_quality.type_checker.subprocess.run", fake_run):
        ok, err, errs = type_check_with_mypy(target)

    assert ok is False
    assert err is not None
    assert "1 mypy" in err
    assert len(errs) == 1


def test_type_check_success_when_mypy_exit_zero(tmp_path) -> None:
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("ai_editor.core.code_quality.type_checker.subprocess.run", fake_run):
        ok, err, errs = type_check_with_mypy(target)

    assert ok is True
    assert err is None
    assert errs == []


def test_project_mypy_success_when_nonzero_but_no_parsed_file_errors(
    tmp_path,
) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 1, stdout="unstructured mypy noise\n", stderr="")

    with patch("ai_editor.core.code_quality.type_checker.subprocess.run", fake_run):
        ok, per_file = type_check_project_with_mypy(tmp_path)

    assert ok is True
    assert per_file == {}


def test_resolve_mypy_config_explicit_wins(tmp_path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    cfg = tmp_path / "custom.toml"
    cfg.write_text("[tool.mypy]\n")
    got = resolve_mypy_config_for_single_file(f, explicit_config=cfg)
    assert got == cfg.resolve()


def test_resolve_mypy_config_finds_pyproject_parent(tmp_path) -> None:
    root = tmp_path
    (root / "pyproject.toml").write_text("[tool.mypy]\n")
    pkg = root / "pkg"
    pkg.mkdir()
    f = pkg / "m.py"
    f.write_text("x = 1\n")
    got = resolve_mypy_config_for_single_file(f, explicit_config=None)
    assert got == (root / "pyproject.toml").resolve()


def test_resolve_mypy_config_skips_repo_root_with_code_analysis_dir(
    tmp_path,
) -> None:
    """Skip pyproject at repo root when code_analysis/ package marker is present."""
    root = tmp_path
    (root / "pyproject.toml").write_text("[tool.mypy]\n")
    (root / "code_analysis").mkdir()
    pkg = root / "pkg"
    pkg.mkdir()
    f = pkg / "m.py"
    f.write_text("x = 1\n")
    got = resolve_mypy_config_for_single_file(f, explicit_config=None)
    assert got is None


def test_resolve_mypy_config_none_when_no_pyproject(tmp_path) -> None:
    f = tmp_path / "lonely.py"
    f.write_text("x = 1\n")
    assert resolve_mypy_config_for_single_file(f, explicit_config=None) is None


def test_project_mypy_failure_when_parsed_errors_exist(tmp_path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x: str = 1\n")
    line = f"{f.resolve()}:1: error: Incompatible types in assignment"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 1, stdout=line + "\n", stderr="")

    with patch("ai_editor.core.code_quality.type_checker.subprocess.run", fake_run):
        ok, per_file = type_check_project_with_mypy(tmp_path)

    assert ok is False
    assert str(f.resolve()) in per_file
    assert len(per_file[str(f.resolve())]) == 1
