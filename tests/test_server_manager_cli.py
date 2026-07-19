"""
Tests for `ai_editor.cli.server_manager_cli` (facade) and
`ai_editor.cli.daemon_cli_commands` (lifecycle).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.cli import daemon_cli_commands, server_manager_cli


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    return path


@pytest.fixture
def pidfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".ai-editor-server.pid"
    monkeypatch.setattr(
        daemon_cli_commands,
        "_default_pidfile_path",
        lambda _config_path: path,
    )
    return path


def test_start_spawns_when_no_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])

    def fake_spawn(_config_path: str, pf: Path) -> int:
        pf.write_text("4242", encoding="utf-8")
        return 4242

    monkeypatch.setattr(daemon_cli_commands, "_spawn_daemon", fake_spawn)
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_wait_until_daemon_stable_or_dead",
        lambda *_a, **_kw: True,
    )

    rc = daemon_cli_commands.cmd_start(str(config_path))

    assert rc == 0
    assert pidfile.read_text(encoding="utf-8").strip() == "4242"
    assert "started pid=4242" in capsys.readouterr().out


def test_start_already_running_when_single_daemon_discovered(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [777])

    def fail_spawn(_cp: str, _pf: Path) -> int:
        raise AssertionError("must not spawn when a daemon is already running")

    monkeypatch.setattr(daemon_cli_commands, "_spawn_daemon", fail_spawn)

    rc = daemon_cli_commands.cmd_start(str(config_path))

    assert rc == 0
    assert pidfile.read_text(encoding="utf-8").strip() == "777"
    assert "already running pid=777" in capsys.readouterr().out


def test_start_errors_when_multiple_daemons_discovered(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [1, 2])

    def fail_spawn(_cp: str, _pf: Path) -> int:
        raise AssertionError("must not spawn")

    monkeypatch.setattr(daemon_cli_commands, "_spawn_daemon", fail_spawn)

    rc = daemon_cli_commands.cmd_start(str(config_path))

    assert rc == 1
    err = capsys.readouterr().err
    assert "multiple daemons" in err


def test_stop_kills_pidfile_and_matching_find_daemon_pids(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pidfile.write_text("10", encoding="utf-8")
    alive = {10, 20}

    def find_pids(_cfg: str) -> list[int]:
        return sorted(alive) if alive else []

    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", find_pids)

    killed: list[int] = []

    def kill_one(pid: int, timeout_s: float) -> None:
        killed.append(pid)
        alive.discard(pid)

    monkeypatch.setattr(daemon_cli_commands, "_kill_process_group", kill_one)
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda p: p in alive)
    monkeypatch.setattr(daemon_cli_commands, "_is_zombie", lambda _p: False)
    monkeypatch.setattr(daemon_cli_commands.time, "sleep", lambda _s: None)

    rc = daemon_cli_commands.cmd_stop(str(config_path))

    assert rc == 0
    assert sorted(killed) == [10, 20]
    assert not pidfile.exists()


def test_restart_stops_drains_then_starts(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seq: list[str] = []

    def fake_stop(_cp: str) -> int:
        seq.append("stop")
        return 0

    def fake_drain(*_a: object, **_kw: object) -> bool:
        seq.append("drain")
        return True

    def fake_start(_cp: str) -> int:
        seq.append("start")
        return 0

    monkeypatch.setattr(
        daemon_cli_commands,
        "cmd_stop",
        fake_stop,
    )
    monkeypatch.setattr(
        daemon_cli_commands,
        "_wait_until_no_daemons",
        fake_drain,
    )
    monkeypatch.setattr(daemon_cli_commands.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        daemon_cli_commands,
        "cmd_start",
        fake_start,
    )

    rc = daemon_cli_commands.cmd_restart(str(config_path))
    assert rc == 0
    assert seq == ["stop", "drain", "start"]


def test_status_stopped_no_pidfile(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "stopped"


def test_status_running_matches_find_daemon_pids(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("55", encoding="utf-8")
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [55])

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "running pid=55"


def test_status_running_daemon_without_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not pidfile.exists()
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [42])

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "running pid=42 (pidfile missing)"


def test_status_reports_and_logs_stale_daemon_children(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(
        daemon_cli_commands,
        "_find_stale_daemon_child_pids",
        lambda _cfg: [101, 102],
    )
    monkeypatch.setattr(
        daemon_cli_commands,
        "_append_manager_log",
        lambda _cfg, level, message: log_calls.append((level, message)),
    )

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == (
        "stopped (stale daemon child processes: 101,102)"
    )
    assert log_calls
    assert log_calls[0][0] == "WARNING"
    assert "daemon root is absent" in log_calls[0][1]


def test_status_removes_stale_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("999999", encoding="utf-8")
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: False)

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    assert "stale pidfile" in capsys.readouterr().out
    assert not pidfile.exists()


def test_start_cleans_stale_daemon_children_before_spawn(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    killed: list[int] = []
    log_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(
        daemon_cli_commands,
        "_find_stale_daemon_child_pids",
        lambda _cfg: [101, 102],
    )
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: True)
    monkeypatch.setattr(daemon_cli_commands, "_is_zombie", lambda _pid: False)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_kill_process_group",
        lambda pid, timeout_s: killed.append(pid),
    )
    monkeypatch.setattr(daemon_cli_commands.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_append_manager_log",
        lambda _cfg, level, message: log_calls.append((level, message)),
    )

    def fake_spawn(_config_path: str, pf: Path) -> int:
        pf.write_text("4242", encoding="utf-8")
        return 4242

    monkeypatch.setattr(daemon_cli_commands, "_spawn_daemon", fake_spawn)
    monkeypatch.setattr(
        daemon_cli_commands,
        "_wait_until_daemon_stable_or_dead",
        lambda *_a, **_kw: True,
    )

    rc = daemon_cli_commands.cmd_start(str(config_path))

    assert rc == 0
    assert killed == [101, 102]
    assert "started pid=4242" in capsys.readouterr().out
    assert any("cleaning stale daemon" in msg for _level, msg in log_calls)


def test_resolve_config_cli_over_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = tmp_path / "a.json"
    a.write_text("{}", encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CASMGR_CONFIG", str(b))
    got = server_manager_cli._resolve_config_path(str(a))
    assert got == str(a.resolve())


def test_resolve_config_env_over_system_and_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_cfg = tmp_path / "from_env.json"
    env_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CASMGR_CONFIG", str(env_cfg))
    sys_cfg = tmp_path / "sys.json"
    sys_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_SYSTEM_DEFAULT_CONFIG", sys_cfg)
    cwd_cfg = tmp_path / "config.json"
    cwd_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    got = server_manager_cli._resolve_config_path(None)
    assert got == str(env_cfg.resolve())


def test_resolve_config_system_over_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)
    sys_cfg = tmp_path / "sys.json"
    sys_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_SYSTEM_DEFAULT_CONFIG", sys_cfg)
    cwd_cfg = tmp_path / "config.json"
    cwd_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    got = server_manager_cli._resolve_config_path(None)
    assert got == str(sys_cfg.resolve())


def test_resolve_config_cwd_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(server_manager_cli, "_SYSTEM_DEFAULT_CONFIG", missing)
    monkeypatch.setattr(server_manager_cli, "_LEGACY_SYSTEM_DEFAULT_CONFIG", missing)
    cwd_cfg = tmp_path / "config.json"
    cwd_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    got = server_manager_cli._resolve_config_path(None)
    assert got == str(cwd_cfg.resolve())


def test_resolve_config_none_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)
    monkeypatch.setattr(
        server_manager_cli,
        "_SYSTEM_DEFAULT_CONFIG",
        tmp_path / "missing_system.json",
    )
    monkeypatch.setattr(
        server_manager_cli,
        "_LEGACY_SYSTEM_DEFAULT_CONFIG",
        tmp_path / "missing_legacy_system.json",
    )
    monkeypatch.chdir(tmp_path)
    assert server_manager_cli._resolve_config_path(None) is None
    err = capsys.readouterr().err
    assert "no config found" in err


def test_server_status_uses_cwd_config_without_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)
    monkeypatch.setattr(
        server_manager_cli,
        "_SYSTEM_DEFAULT_CONFIG",
        tmp_path / "no_system.json",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])
    rc = server_manager_cli.server(["status"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "stopped"


def test_status_pidfile_alive_but_not_our_daemon(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("88", encoding="utf-8")
    monkeypatch.setattr(daemon_cli_commands, "find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(daemon_cli_commands, "_is_alive", lambda _pid: True)

    rc = daemon_cli_commands.cmd_status(str(config_path))

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("stopped (pidfile pid=88 alive")
    assert "pidfile likely stale" in out
