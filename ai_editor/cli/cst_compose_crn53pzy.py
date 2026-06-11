"""
Server manager CLI for running `ai-editor-server` as a daemon.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Union

# For stderr redirect: DEVNULL (int) or open file (TextIO)
_StderrDest = Union[int, io.TextIOWrapper]


DEFAULT_SHUTDOWN_GRACE_SECONDS = 10.0

# Override for tests or exotic layouts (must be an existing executable).
_ENV_DAEMON_PYTHON = "AI_EDITOR_DAEMON_PYTHON"

# Config discovery for ``casmgr`` (see ``_resolve_config_path``).
_ENV_CASMGR_CONFIG = "CASMGR_CONFIG"
_SYSTEM_DEFAULT_CONFIG = Path("/etc/casmgr/config.json")
_CWD_CONFIG_NAME = "config.json"


def _resolve_config_path(cli_config: Optional[str]) -> Optional[str]:
    """
    Resolve ``config.json`` path by priority.

    1. ``--config`` from the CLI (must exist).
    2. ``CASMGR_CONFIG`` (must exist if set).
    3. ``/etc/casmgr/config.json`` if present.
    4. ``./config.json`` under the current working directory if present.

    Args:
        cli_config: Optional path passed via ``--config`` flag.

    Returns:
        Absolute path to an existing config file, or ``None`` if none found.
    """
    if cli_config is not None and str(cli_config).strip() != "":
        p = Path(cli_config).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(f"error: config file not found: {p}", file=sys.stderr)
            return None
        return str(p)

    env_val = os.environ.get(_ENV_CASMGR_CONFIG, "").strip()
    if env_val:
        p = Path(env_val).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(
                f"error: {_ENV_CASMGR_CONFIG} points to missing file: {p}",
                file=sys.stderr,
            )
            return None
        return str(p)

    if _SYSTEM_DEFAULT_CONFIG.is_file():
        return str(_SYSTEM_DEFAULT_CONFIG.resolve())

    cwd_cfg = (Path.cwd() / _CWD_CONFIG_NAME).resolve()
    if cwd_cfg.is_file():
        return str(cwd_cfg)

    print(
        "error: no config found; pass --config, set "
        f"{_ENV_CASMGR_CONFIG}, install {_SYSTEM_DEFAULT_CONFIG}, "
        f"or run from a directory containing {_CWD_CONFIG_NAME}.",
        file=sys.stderr,
    )
    return None


def _find_venv_python_near_config(config_path: str) -> Optional[str]:
    """
    Find the Python executable inside a venv next to the config file.

    Args:
        config_path: Absolute path to the server config JSON file.

    Returns:
        Absolute path to the venv Python executable, or ``None`` if not found.
    """
    config_dir = Path(config_path).parent
    for venv_name in (".venv", "venv"):
        candidate = config_dir / venv_name / "bin" / "python"
        if candidate.is_file():
            return str(candidate)
    return None


def _project_root_dir(config_path: str) -> Path:
    """
    Return the project root directory (parent of the config file).

    Args:
        config_path: Absolute path to the server config JSON file.

    Returns:
        Path object pointing to the directory containing the config file.
    """
    return Path(config_path).parent


def _python_executable_for_daemon(config_path: str) -> str:
    """
    Resolve the Python executable to use when spawning the daemon.

    Prefers the venv Python next to the config file; falls back to
    ``sys.executable``.

    Args:
        config_path: Absolute path to the server config JSON file.

    Returns:
        Absolute path to the Python executable as a string.
    """
    venv_py = _find_venv_python_near_config(config_path)
    if venv_py:
        return venv_py
    return sys.executable


def _default_pidfile_path(config_path: str) -> Path:
    """
    Build default pidfile path based on the config location.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Path to pidfile.
    """

    cfg = Path(config_path).resolve()
    return cfg.parent / ".ai-editor-server.pid"


def _read_shutdown_grace_seconds(config_path: str) -> float:
    """
    Read shutdown grace period from config.

    Used as the maximum time to wait after sending SIGTERM before escalating to SIGKILL.

    Supported config locations (first found wins):
    - process_management.shutdown_grace_seconds
    - server_manager.shutdown_grace_seconds

    Args:
        config_path: Path to config.json.

    Returns:
        Grace period in seconds.
    """

    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SHUTDOWN_GRACE_SECONDS

    for section_name in ("process_management", "server_manager"):
        section = cfg.get(section_name)
        if isinstance(section, dict):
            val = section.get("shutdown_grace_seconds")
            if isinstance(val, (int, float)) and float(val) > 0:
                return float(val)
    return DEFAULT_SHUTDOWN_GRACE_SECONDS


def _read_pid(pidfile: Path) -> Optional[int]:
    """
    Read pid from pidfile.

    Args:
        pidfile: Path to pidfile.

    Returns:
        PID if pidfile exists and contains an integer, otherwise None.
    """

    try:
        return int(pidfile.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _resolved_config_path_for_daemon_pid(pid: int, cfg_argv: str) -> Optional[str]:
    """
    Resolve the on-disk config path for a daemon given its ``--config`` argv.

    Relative paths are resolved using the process working directory (Linux:
    ``/proc/<pid>/cwd``). On non-Linux or if resolution fails, returns None.

    Args:
        pid: OS process id of the daemon.
        cfg_argv: Value after ``--config`` in the process argv.

    Returns:
        Absolute resolved config path, or None.
    """

    try:
        p = Path(cfg_argv)
        if p.is_absolute():
            return str(p.resolve())
        if sys.platform != "linux":
            return None
        cwd_link = Path(f"/proc/{pid}/cwd")
        if not cwd_link.exists():
            return None
        return str((cwd_link.resolve() / p).resolve())
    except Exception:
        return None


def _wait_until_daemon_stable_or_dead(
    pid: int,
    *,
    stable_seconds: float = 1.25,
    max_wait_seconds: float = 20.0,
) -> bool:
    """
    Wait until the daemon process is stable or dead.

    Args:
        pid: PID of the daemon process to monitor.
        stable_seconds: Seconds the process must stay alive to be considered stable.
        max_wait_seconds: Maximum total wait time before giving up.

    Returns:
        ``True`` if the process is alive and stable, ``False`` if it died.
    """
    deadline = time.time() + max_wait_seconds
    alive_since: Optional[float] = None

    while time.time() < deadline:
        if _is_alive(pid):
            if alive_since is None:
                alive_since = time.time()
            elif time.time() - alive_since >= stable_seconds:
                return True
        else:
            return False
        time.sleep(0.1)

    return _is_alive(pid)


def _is_alive(pid: int) -> bool:
    """
    Check if a PID exists.

    Args:
        pid: Process id.

    Returns:
        True if process exists, False otherwise.
    """

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # If we don't have permission to signal it, it's still alive.
        return True


def _kill_process_group(pid: int, timeout_s: float) -> None:
    """
    Terminate process group with SIGTERM, then SIGKILL if needed.

    The server spawns child processes (workers). Hung children can keep
    resources (e.g. port 15000) busy even if the parent receives SIGTERM,
    so we must terminate the whole process group.

    Waits until the process is confirmed dead before returning.

    Args:
        pid: Process id of the group leader.
        timeout_s: How long to wait after SIGTERM before escalating to SIGKILL.

    Returns:
        None.
    """
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    except Exception:
        pgid = None

    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _is_alive(pid):
            return
        time.sleep(0.2)

    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return

    # Wait until confirmed dead after SIGKILL.
    sigkill_deadline = time.time() + 5.0
    while time.time() < sigkill_deadline:
        if not _is_alive(pid):
            return
        time.sleep(0.1)


def _find_daemon_pids(config_path: str) -> list[int]:
    """
    Best-effort: find running daemon PIDs for this config.

    Args:
        config_path: Path to config.json.

    Returns:
        List of matching PIDs.
    """

    # We cannot rely on exact string match because the running process may have
    # `--config config.json` (relative) while our config_path can be absolute.
    #
    # Use `ps` output and parse argv as a robust fallback.
    cfg_resolved = str(Path(config_path).resolve())

    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except Exception:
        return []

    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_str, args_str = line.split(maxsplit=1)
            pid = int(pid_str)
        except Exception:
            continue

        if "-m ai_editor.main" not in args_str:
            continue
        if "--daemon" not in args_str:
            continue
        if "--config" not in args_str:
            continue

        parts = args_str.split()
        try:
            cfg_idx = parts.index("--config")
            cfg_val = parts[cfg_idx + 1]
        except Exception:
            continue

        if cfg_val == config_path or cfg_val == cfg_resolved:
            pids.append(pid)
            continue

        resolved = _resolved_config_path_for_daemon_pid(pid, cfg_val)
        if resolved == cfg_resolved:
            pids.append(pid)

    return _root_daemon_pids_only(sorted(set(pids)))


def _read_ppid(pid: int) -> Optional[int]:
    """
    Read the parent PID of a process from ``/proc/<pid>/status``.

    Args:
        pid: PID of the process to inspect.

    Returns:
        Parent PID as an integer, or ``None`` if unavailable.
    """
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        for line in status.splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except Exception:
        pass
    return None


def _root_daemon_pids_only(pids: list[int]) -> list[int]:
    """
    Filter a list of PIDs to only root daemon processes.

    Removes PIDs whose parent is also in the list (child processes).

    Args:
        pids: List of candidate daemon PIDs.

    Returns:
        Filtered list containing only root PIDs.
    """
    pid_set = set(pids)
    return [p for p in pids if _read_ppid(p) not in pid_set]


def _daemon_log_file(config_path: str) -> Path | None:
    """
    Resolve daemon log file path from config so stderr can be redirected there.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Path to mcp_server.log, or None if config cannot be read.
    """
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    server = cfg.get("server")
    if not isinstance(server, dict):
        return None
    log_dir_str = server.get("log_dir", "./logs")
    log_dir = Path(log_dir_str)
    if not log_dir.is_absolute():
        log_dir = (Path(config_path).resolve().parent / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "mcp_server.log"


def _spawn_daemon(config_path: str, pidfile: Path) -> int:
    """
    Spawn daemon server process.

    stderr is redirected to server log file (from config server.log_dir)
    so that crash tracebacks and errors are visible in logs.

    Always passes an **absolute** ``--config`` path so ``ps``/``_find_daemon_pids``
    matches regardless of the caller's current working directory.

    Sets ``cwd`` to the config file's directory (project root) so ``python -m
    ai_editor`` resolves the package when running from a source tree.

    Args:
        config_path: Path to config JSON.
        pidfile: Path to pidfile to write.

    Returns:
        PID of spawned process.
    """
    cfg_abs = str(Path(config_path).resolve())
    project_root = str(_project_root_dir(config_path))
    python = _python_executable_for_daemon(config_path)
    args = [python, "-m", "ai_editor.main", "--config", cfg_abs, "--daemon"]

    stderr_dest: _StderrDest = subprocess.DEVNULL
    log_file_path = _daemon_log_file(cfg_abs)
    if log_file_path is not None:
        try:
            stderr_dest = open(log_file_path, "a", encoding="utf-8")
        except OSError:
            stderr_dest = subprocess.DEVNULL

    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUNBUFFERED", "1")

    try:
        proc = subprocess.Popen(
            args,
            cwd=project_root,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_dest,
            start_new_session=True,
            close_fds=True,
        )
        pidfile.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid
    finally:
        if stderr_dest is not subprocess.DEVNULL and hasattr(stderr_dest, "close"):
            stderr_dest.close()


def _cmd_status(config_path: str) -> int:
    """
    Print daemon status.

    Uses the same process discovery as ``stop`` (``_find_daemon_pids``), not only
    the pidfile. Otherwise ``status`` could report *stopped* while a daemon for
    this config is running (e.g. pidfile deleted, or started via ``main`` without
    going through ``start``).

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    pf_pid = _read_pid(pidfile)
    daemons = _find_daemon_pids(config_path)

    if daemons:
        if len(daemons) == 1:
            d = daemons[0]
            if pf_pid == d:
                print(f"running pid={d}")
            elif pf_pid is None:
                print(f"running pid={d} (pidfile missing)")
            else:
                print(f"running pid={d} (pidfile pid={pf_pid} does not match)")
        else:
            print(f"running multiple pids={','.join(str(p) for p in daemons)}")
        return 0

    if pf_pid is None:
        print("stopped")
        return 0
    if not _is_alive(pf_pid):
        print("stopped (stale pidfile)")
        try:
            pidfile.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    print(
        f"stopped (pidfile pid={pf_pid} alive but no daemon for this config; "
        "pidfile likely stale)"
    )
    return 0


def _cmd_stop(config_path: str) -> int:
    """
    Stop daemon process.

    Sends SIGTERM/SIGKILL to all matching pids and waits until every
    process is confirmed dead before returning.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """
    grace = _read_shutdown_grace_seconds(config_path)
    pidfile = _default_pidfile_path(config_path)
    pid = _read_pid(pidfile)

    pids: list[int] = []
    if pid is not None:
        pids.append(pid)
    pids.extend([p for p in _find_daemon_pids(config_path) if p not in pids])

    if not pids:
        return 0

    for p in pids:
        _kill_process_group(p, timeout_s=grace)

    # Final confirmation: wait until all pids are dead.
    wait_deadline = time.time() + 5.0
    while time.time() < wait_deadline:
        if not any(_is_alive(p) for p in pids):
            break
        time.sleep(0.1)
    else:
        still_alive = [p for p in pids if _is_alive(p)]
        if still_alive:
            print(
                f"warning: processes still alive after stop: {still_alive}",
                file=sys.stderr,
            )

    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass
    return 0


def _cmd_start(config_path: str) -> int:
    """
    Start daemon process (if not already running).

    Uses the same discovery as ``status``/``stop`` (``_find_daemon_pids``), not
    only the pidfile, so we do not start a second server when a daemon is already
    running but the pidfile is missing or stale.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    daemons = _find_daemon_pids(config_path)

    if len(daemons) > 1:
        print(
            f"error: multiple daemons for this config (pids={','.join(str(p) for p in daemons)}); "
            "run stop first",
            file=sys.stderr,
        )
        return 1

    if len(daemons) == 1:
        try:
            pidfile.write_text(str(daemons[0]), encoding="utf-8")
        except OSError as e:
            print(f"error: cannot write pidfile: {e}", file=sys.stderr)
            return 1
        print(f"already running pid={daemons[0]}")
        return 0

    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass

    py_exe = _python_executable_for_daemon(config_path)
    root = _project_root_dir(config_path)
    print(f"daemon: python={py_exe} cwd={root}", file=sys.stderr)

    new_pid = _spawn_daemon(config_path, pidfile)
    print(f"started pid={new_pid}")
    if not _wait_until_daemon_stable_or_dead(new_pid):
        log_hint = _daemon_log_file(str(Path(config_path).resolve()))
        where = (
            str(log_hint)
            if log_hint is not None
            else "server log (see config server.log_dir)"
        )
        print(
            f"error: daemon pid={new_pid} exited during startup; check {where}",
            file=sys.stderr,
        )
        try:
            pidfile.unlink(missing_ok=True)
        except OSError:
            pass
        return 1
    return 0


def _cmd_restart(config_path: str) -> int:
    """
    Restart daemon process.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    _cmd_stop(config_path)
    return _cmd_start(config_path)


def server(argv: Optional[list[str]] = None) -> int:
    """
    Console entrypoint for the daemon manager (installed script: ``casmgr``).

    Args:
        argv: Optional argv override.

    Returns:
        Exit code.
    """

    parser = argparse.ArgumentParser(prog="casmgr")
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=(
            "Path to config.json (optional). If omitted: "
            f"{_ENV_CASMGR_CONFIG}, then {_SYSTEM_DEFAULT_CONFIG}, "
            f"then ./{_CWD_CONFIG_NAME} in the current directory."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    ns = parser.parse_args(argv)

    config_path = _resolve_config_path(ns.config)
    if config_path is None:
        return 2

    if ns.cmd == "start":
        return _cmd_start(config_path)
    if ns.cmd == "stop":
        return _cmd_stop(config_path)
    if ns.cmd == "restart":
        return _cmd_restart(config_path)
    if ns.cmd == "status":
        return _cmd_status(config_path)

    raise RuntimeError(f"Unknown command: {ns.cmd}")


if __name__ == "__main__":
    raise SystemExit(server())
