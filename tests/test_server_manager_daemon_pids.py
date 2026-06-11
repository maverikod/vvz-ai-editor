"""
Tests for daemon PID discovery in `ai_editor.cli.daemon_cli_commands`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ai_editor.cli import daemon_cli_commands, server_manager_cli


@pytest.mark.skipif(sys.platform == "win32", reason="symlink venv layout")
def test_find_venv_keeps_symlink_path_not_system_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: Path.resolve() collapsed .venv/bin/python to /usr/bin/... ."""

    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.symlink_to("/usr/bin/python3")
    monkeypatch.delenv(daemon_cli_commands._ENV_DAEMON_PYTHON, raising=False)

    got = daemon_cli_commands._find_venv_python_near_config(str(cfg))
    assert got == str(venv_py.absolute())
    assert ".venv" in got


@pytest.mark.skipif(
    sys.platform == "win32", reason="chmod +x not used for venv layout test"
)
def test_python_executable_for_daemon_prefers_dot_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_bytes(b"#!/bin/sh\nexec true\n")
    os.chmod(venv_py, 0o755)
    monkeypatch.delenv(daemon_cli_commands._ENV_DAEMON_PYTHON, raising=False)

    got = daemon_cli_commands._python_executable_for_daemon(str(cfg))
    assert got == str(venv_py.absolute())


def test_spawn_daemon_sets_cwd_to_config_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    pidfile = tmp_path / "x.pid"
    captured: dict[str, object] = {}

    class _Proc:
        pid = 99999

    def fake_popen(args: list[str], **kwargs: object) -> _Proc:
        captured["cwd"] = str(kwargs.get("cwd", ""))
        captured["args"] = args
        assert kwargs.get("env") is not None
        return _Proc()

    monkeypatch.setattr(daemon_cli_commands.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_python_executable_for_daemon",
        lambda _c: sys.executable,
    )

    pid = daemon_cli_commands._spawn_daemon(str(cfg), pidfile)
    assert pid == 99999
    assert captured["cwd"] == str(tmp_path.resolve())
    args = captured["args"]
    assert isinstance(args, list)
    cfg_idx = args.index("--config")
    assert args[cfg_idx + 1] == "config.json"


def test_activate_project_root_uses_relative_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    old = Path.cwd()
    try:
        os.chdir(other)
        rel = server_manager_cli._activate_project_root(str(cfg))
        assert rel == "config.json"
        assert Path.cwd() == tmp_path.resolve()
    finally:
        os.chdir(old)


def test_wait_until_daemon_stable_or_dead_false_when_exits_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: False)
    assert not daemon_cli_commands._wait_until_daemon_stable_or_dead(
        1, stable_seconds=0.2, max_wait_seconds=1.0
    )


def test_wait_until_daemon_stable_or_dead_true_when_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: True)
    assert daemon_cli_commands._wait_until_daemon_stable_or_dead(
        1, stable_seconds=0.15, max_wait_seconds=1.0
    )


@pytest.mark.skipif(sys.platform != "linux", reason="/proc/<pid>/cwd is Linux-specific")
def test_resolved_config_path_relative_uses_proc_cwd(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        got = daemon_cli_commands._resolved_config_path_for_daemon_pid(
            os.getpid(), "config.json"
        )
    finally:
        os.chdir(old)
    assert got == str(cfg.resolve())


def test_resolved_config_path_absolute(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text("{}", encoding="utf-8")
    got = daemon_cli_commands._resolved_config_path_for_daemon_pid(
        os.getpid(), str(cfg)
    )
    assert got == str(cfg.resolve())


def test_find_daemon_pids_matches_via_resolved_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    cfg_res = str(cfg.resolve())

    ps_line = (
        "5000 python -m ai_editor.main --config config.json --daemon\n"
        "6000 python -m ai_editor.main --config other.json --daemon\n"
    )
    monkeypatch.setattr(
        daemon_cli_commands.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )

    def fake_resolve(pid: int, cfg_argv: str) -> str | None:
        if pid == 5000 and cfg_argv == "config.json":
            return cfg_res
        return None

    monkeypatch.setattr(
        daemon_cli_commands,
        "_resolved_config_path_for_daemon_pid",
        fake_resolve,
    )

    assert daemon_cli_commands.find_daemon_pids(cfg_res) == [5000]


def test_find_daemon_pids_matches_same_inode_different_path_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Container /workspace vs host path to the same bind-mounted config file."""

    project = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    host_cfg = project / "config.json"
    host_cfg.write_text("{}", encoding="utf-8")
    container_cfg = workspace / "config.json"
    os.link(host_cfg, container_cfg)

    container_resolved = str(container_cfg.resolve())
    host_resolved = str(host_cfg.resolve())
    assert container_resolved != host_resolved

    ps_line = "5000 python -m ai_editor.main --config config.json --daemon\n"
    monkeypatch.setattr(
        daemon_cli_commands.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )

    def fake_resolve(pid: int, cfg_argv: str) -> str | None:
        if pid == 5000 and cfg_argv == "config.json":
            return host_resolved
        return None

    monkeypatch.setattr(
        daemon_cli_commands,
        "_resolved_config_path_for_daemon_pid",
        fake_resolve,
    )

    assert daemon_cli_commands.find_daemon_pids(container_resolved) == [5000]


def test_root_daemon_pids_only_drops_fork_children_with_same_cmdline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Children keep parent's argv until exec; only session roots must count."""

    def ppid_of(pid: int) -> int | None:
        return {100: 1, 101: 100, 102: 100}.get(pid)

    monkeypatch.setattr(daemon_cli_commands, "_read_ppid", ppid_of)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_read_pgid",
        lambda pid: 100,
    )

    assert daemon_cli_commands._root_daemon_pids_only([100, 101, 102]) == [100]


def test_find_daemon_pids_excludes_orphaned_daemon_group_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workers inherited daemon argv, but their dead group leader was the real daemon."""

    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    cfg_res = str(cfg.resolve())
    (tmp_path / ".ai-editor-server.pid").write_text("1000", encoding="utf-8")
    ps_line = (
        f"1001 python -m ai_editor.main --config {cfg_res} --daemon\n"
        f"1002 python -m ai_editor.main --config {cfg_res} --daemon\n"
    )
    monkeypatch.setattr(
        daemon_cli_commands.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )
    monkeypatch.setattr(daemon_cli_commands, "_is_zombie", lambda _pid: False)
    monkeypatch.setattr(daemon_cli_commands, "_read_ppid", lambda _pid: 1)
    monkeypatch.setattr(daemon_cli_commands, "_read_pgid", lambda _pid: 1000)
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda pid: pid != 1000)

    assert daemon_cli_commands.find_daemon_pids(cfg_res) == []
    assert daemon_cli_commands._find_stale_daemon_child_pids(cfg_res) == [1001, 1002]


def test_find_daemon_pids_excludes_known_worker_pid_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text('{"server": {"log_dir": "logs"}}', encoding="utf-8")
    cfg_res = str(cfg.resolve())
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "indexing_worker.pid").write_text("2001", encoding="utf-8")
    ps_line = (
        f"2000 python -m ai_editor.main --config {cfg_res} --daemon\n"
        f"2001 python -m ai_editor.main --config {cfg_res} --daemon\n"
    )
    monkeypatch.setattr(
        daemon_cli_commands.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )
    monkeypatch.setattr(daemon_cli_commands, "_is_zombie", lambda _pid: False)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_read_ppid",
        lambda pid: 1 if pid == 2000 else 2000,
    )
    monkeypatch.setattr(
        daemon_cli_commands,
        "_read_pgid",
        lambda pid: 2000,
    )
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: True)

    assert daemon_cli_commands.find_daemon_pids(cfg_res) == [2000]
    assert daemon_cli_commands._find_stale_daemon_child_pids(cfg_res) == [2001]


def test_find_daemon_pids_does_not_match_other_basename_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: basename-only match used to kill unrelated ``config.json`` daemons."""

    mine = tmp_path / "mine" / "config.json"
    mine.parent.mkdir(parents=True)
    mine.write_text("{}", encoding="utf-8")

    ps_line = "7000 python -m ai_editor.main --config config.json --daemon\n"
    monkeypatch.setattr(
        daemon_cli_commands.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )
    monkeypatch.setattr(
        daemon_cli_commands,
        "_resolved_config_path_for_daemon_pid",
        lambda _pid, _argv: None,
    )

    assert daemon_cli_commands.find_daemon_pids(str(mine.resolve())) == []
