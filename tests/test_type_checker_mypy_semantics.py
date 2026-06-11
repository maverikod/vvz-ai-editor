"""
Mypy subprocess semantics: non-zero exit vs filtered / attributed errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from subprocess import CompletedProcess
from unittest.mock import patch

from ai_editor.core.code_quality.type_checker import (
    resolve_mypy_config_for_single_file,
    type_check_project_with_mypy,
    type_check_with_mypy,
)


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
