"""
Tests for project_pip session log files under the server log directory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from ai_editor.core.project_pip_logging import (
    PROJECT_PIP_LOG_SUBDIR,
    write_project_pip_session_log,
)


def test_write_project_pip_session_log_creates_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text('{"server": {"log_dir": "logs"}}', encoding="utf-8")
    monkeypatch.setattr(
        "ai_editor.core.project_pip_logging._resolve_active_config_path",
        lambda: cfg,
    )

    out = write_project_pip_session_log(
        command_name="project_pip_install",
        project_id="550e8400-e29b-41d4-a716-446655440000",
        pip_args=["install", "--no-input", "requests"],
        stdout="stdout-line\n",
        stderr="stderr-line\n",
        returncode=0,
        timed_out=False,
        job_id="job-abc",
    )

    assert out["pip_log_write_error"] is None
    assert out["pip_logs_directory"] == str((tmp_path / "logs").resolve())
    path_str = out["pip_output_log_path"]
    assert path_str
    log_path = Path(path_str)
    assert log_path.is_file()
    assert log_path.parent.name == PROJECT_PIP_LOG_SUBDIR
    text = log_path.read_text(encoding="utf-8")
    assert "--- stdout ---" in text
    assert "stdout-line" in text
    assert "--- stderr ---" in text
    assert "stderr-line" in text
    assert "job_id=job-abc" in text
    assert "--- process ---" in text
    assert "returncode=0" in text
    rel = out["pip_output_log_relative"]
    assert isinstance(rel, str)
    assert rel.startswith(f"logs/{PROJECT_PIP_LOG_SUBDIR}/")


def test_write_project_pip_session_log_surfaces_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text('{"server": {"log_dir": "logs"}}', encoding="utf-8")
    monkeypatch.setattr(
        "ai_editor.core.project_pip_logging._resolve_active_config_path",
        lambda: cfg,
    )
    # Not a directory -> mkdir on file path parent may still work; use invalid subdir
    bad = tmp_path / "logs"
    bad.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "ai_editor.core.project_pip_logging.resolve_server_log_dir",
        lambda: bad,
    )

    out = write_project_pip_session_log(
        command_name="project_pip_list",
        project_id="p",
        pip_args=["list"],
        stdout="",
        stderr="",
        returncode=0,
        timed_out=False,
    )
    assert out["pip_output_log_path"] is None
    assert out["pip_log_write_error"]
