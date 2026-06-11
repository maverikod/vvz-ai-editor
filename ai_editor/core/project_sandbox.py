"""
Project sandbox: run Python code only from a given project root.

Runs a script in a subprocess with cwd and PYTHONPATH restricted to the
project root so that only code from that project (and the standard library)
can be executed. Used for registered projects only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# Defense against runaway child output exhausting the analysis-server process.
MAX_CAPTURE_BYTES_PER_STREAM = 2 * 1024 * 1024


class VenvNotFoundError(Exception):
    """Raised when project .venv or venv is not found."""


@dataclass
class SandboxRunResult:
    """Result of running a script in the project sandbox.

    Attributes:
        stdout: Standard output (text).
        stderr: Standard error (text).
        returncode: Process return code (None if timed out).
        timed_out: True if the process was killed due to timeout.
        post_run_delay_seconds_applied: Seconds slept after the subprocess exited
            (only set by :func:`run_in_project_sandbox` when requested).
    """

    stdout: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool
    post_run_delay_seconds_applied: float = 0.0


def _read_pipe_limited_bytes(pipe, max_bytes: int) -> Tuple[str, bool]:
    """Read up to max_bytes from a binary pipe, then drain and discard the rest."""
    chunks: List[bytes] = []
    total = 0
    chunk_size = 65536
    truncated = False
    while total < max_bytes:
        to_read = min(chunk_size, max_bytes - total)
        data = pipe.read(to_read)
        if not data:
            break
        chunks.append(data)
        total += len(data)
    while True:
        data = pipe.read(chunk_size)
        if not data:
            break
        truncated = True
    text = b"".join(chunks).decode("utf-8", errors="replace")
    if truncated:
        text += "\n[... output truncated ...]\n"
    return text, truncated


def _terminate_sandbox_process(proc: subprocess.Popen) -> None:
    """On POSIX, kill the whole process group so grandchildren cannot outlive timeout."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        else:
            proc.kill()
        proc.wait()


def _run_sandbox_subprocess(
    cmd: List[str],
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: Optional[int],
    max_stdout_bytes: Optional[int] = None,
    max_stderr_bytes: Optional[int] = None,
) -> SandboxRunResult:
    """Run cmd with bounded capture, optional timeout, POSIX session for group kill."""
    cap_out = (
        max_stdout_bytes
        if max_stdout_bytes is not None
        else MAX_CAPTURE_BYTES_PER_STREAM
    )
    cap_err = (
        max_stderr_bytes
        if max_stderr_bytes is not None
        else MAX_CAPTURE_BYTES_PER_STREAM
    )
    if os.name == "posix":
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("Popen pipes missing despite stdout=PIPE, stderr=PIPE")

    stdout_pipe = proc.stdout
    stderr_pipe = proc.stderr

    out_holder: List[Tuple[str, bool]] = [("", False)]
    err_holder: List[Tuple[str, bool]] = [("", False)]

    def read_stdout() -> None:
        try:
            out_holder[0] = _read_pipe_limited_bytes(stdout_pipe, cap_out)
        finally:
            try:
                stdout_pipe.close()
            except Exception:
                pass

    def read_stderr() -> None:
        try:
            err_holder[0] = _read_pipe_limited_bytes(stderr_pipe, cap_err)
        finally:
            try:
                stderr_pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=read_stdout, name="sandbox-stdout", daemon=True)
    t_err = threading.Thread(target=read_stderr, name="sandbox-stderr", daemon=True)
    t_out.start()
    t_err.start()

    timed_out = False
    returncode: Optional[int] = None
    try:
        returncode = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_sandbox_process(proc)
        returncode = None
    finally:
        t_out.join()
        t_err.join()

    out_text, _ = out_holder[0]
    err_text, _ = err_holder[0]
    return SandboxRunResult(
        stdout=out_text,
        stderr=err_text,
        returncode=returncode,
        timed_out=timed_out,
        post_run_delay_seconds_applied=0.0,
    )


def run_in_project_sandbox(
    root_path: Path,
    script_relative_path: str,
    args: Optional[List[str]] = None,
    timeout_seconds: Optional[int] = None,
    post_run_delay_seconds: Optional[float] = None,
) -> SandboxRunResult:
    """
    Run a Python script under the project sandbox.

    The script must be inside root_path. Execution uses:
    - cwd = root_path
    - PYTHONPATH = root_path only (imports limited to project + stdlib)
    - If root_path/.venv or root_path/venv exists: uses that venv's Python
      (interpreter, VIRTUAL_ENV, PATH) so project dependencies are available.
      Raises VenvNotFoundError if neither .venv nor venv is found.

    Args:
        root_path: Absolute path to the project root (must exist).
        script_relative_path: Path to the script relative to root_path.
            Must not escape the project (e.g. no ".." outside root).
        args: Optional list of arguments passed to the script (argv[1:]).
        timeout_seconds: Optional timeout in seconds; process is killed if exceeded.
        post_run_delay_seconds: Optional extra seconds to sleep after the subprocess
            exits (after stdout/stderr are captured). Use for startup/settling without a
            helper script. Must be non-negative.

    Returns:
        SandboxRunResult with stdout, stderr, returncode, timed_out flag, and
        post_run_delay_seconds_applied.

    Raises:
        ValueError: If root_path does not exist, or script path is outside project.
        FileNotFoundError: If the script file does not exist.
        VenvNotFoundError: If neither .venv nor venv exists under root_path.
    """
    root_resolved = root_path.resolve()
    if not root_resolved.is_dir():
        raise ValueError(f"Project root is not a directory: {root_path}")

    # Resolve script path: always relative to project root, no escape.
    script_path = (root_resolved / script_relative_path).resolve()
    if not script_path.is_relative_to(root_resolved):
        raise ValueError(
            f"Script path must be inside project root: {script_relative_path} "
            f"(resolved to {script_path})"
        )
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    if not script_path.is_file():
        raise ValueError(f"Path is not a file: {script_path}")

    # Prefer project's .venv/bin/python so project dependencies are used
    venv_python: Optional[Path] = None
    for cand in [
        root_resolved / ".venv" / "bin" / "python",
        root_resolved / "venv" / "bin" / "python",
    ]:
        if cand.exists():
            venv_python = cand
            break

    if venv_python is None:
        raise VenvNotFoundError(
            f"Project virtual environment not found under {root_resolved}. "
            "Expected .venv/bin/python or venv/bin/python. "
            "Create a venv in the project root (e.g. python -m venv .venv)."
        )

    interpreter = str(venv_python)
    venv_dir = venv_python.parent.parent
    logger.debug(
        "Using project venv: %s (interpreter=%s)",
        venv_dir,
        interpreter,
    )

    cmd = [interpreter, str(script_path)]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_resolved)
    if venv_dir is not None:
        env["VIRTUAL_ENV"] = str(venv_dir)
        venv_bin = venv_dir / "bin"
        if venv_bin.exists():
            path_prepend = str(venv_bin)
            env["PATH"] = path_prepend + os.pathsep + env.get("PATH", "")

    logger.debug(
        "Running in project sandbox: cwd=%s PYTHONPATH=%s cmd=%s",
        root_resolved,
        env["PYTHONPATH"],
        cmd,
    )
    result = _run_sandbox_subprocess(cmd, root_resolved, env, timeout_seconds)
    delay = 0.0
    if post_run_delay_seconds is not None:
        delay = float(post_run_delay_seconds)
        if delay < 0:
            raise ValueError("post_run_delay_seconds must be non-negative")
    if delay > 0:
        time.sleep(delay)
    return SandboxRunResult(
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        timed_out=result.timed_out,
        post_run_delay_seconds_applied=delay,
    )


def run_module_in_project_sandbox(
    root_path: Path,
    module: str,
    args: Optional[List[str]] = None,
    timeout_seconds: Optional[int] = None,
) -> SandboxRunResult:
    """
    Run a Python module under the project sandbox as `python -m <module> [args]`.

    Uses the same sandbox as run_in_project_sandbox: cwd and PYTHONPATH set to
    project root, project's .venv/venv used if present.

    Args:
        root_path: Absolute path to the project root (must exist).
        module: Module name to run (e.g. "ai_admin" for `python -m ai_admin`).
        args: Optional list of arguments (e.g. ["--help"]).
        timeout_seconds: Optional timeout in seconds.

    Returns:
        SandboxRunResult with stdout, stderr, returncode, and timed_out flag.

    Raises:
        ValueError: If root_path does not exist or module is empty.
        VenvNotFoundError: If neither .venv nor venv exists under root_path.
    """
    root_resolved = root_path.resolve()
    if not root_resolved.is_dir():
        raise ValueError(f"Project root is not a directory: {root_path}")
    if not (module or module.strip()):
        raise ValueError("module must be a non-empty string")

    module = module.strip()
    venv_python: Optional[Path] = None
    for cand in [
        root_resolved / ".venv" / "bin" / "python",
        root_resolved / "venv" / "bin" / "python",
    ]:
        if cand.exists():
            venv_python = cand
            break

    if venv_python is None:
        raise VenvNotFoundError(
            f"Project virtual environment not found under {root_resolved}. "
            "Expected .venv/bin/python or venv/bin/python."
        )

    interpreter = str(venv_python)
    venv_dir = venv_python.parent.parent
    logger.debug(
        "Using project venv for module run: %s module=%s",
        venv_dir,
        module,
    )

    cmd = [interpreter, "-m", module]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_resolved)
    if venv_dir is not None:
        env["VIRTUAL_ENV"] = str(venv_dir)
        venv_bin = venv_dir / "bin"
        if venv_bin.exists():
            path_prepend = str(venv_bin)
            env["PATH"] = path_prepend + os.pathsep + env.get("PATH", "")

    logger.debug(
        "Running module in project sandbox: cwd=%s cmd=%s",
        root_resolved,
        cmd,
    )
    return _run_sandbox_subprocess(cmd, root_resolved, env, timeout_seconds)


def run_pip_in_project_sandbox(
    root_path: Path,
    pip_args: Optional[List[str]] = None,
    timeout_seconds: Optional[int] = None,
) -> SandboxRunResult:
    """
    Run ``python -m pip`` with arguments in the project sandbox.

    Uses the same interpreter, cwd, PYTHONPATH, and venv as
    :func:`run_module_in_project_sandbox` (i.e. ``python -m pip ...``).

    Args:
        root_path: Absolute path to the project root (must exist).
        pip_args: Arguments after ``pip`` (e.g. ``["list", "--format=json"]``).
        timeout_seconds: Optional timeout in seconds.

    Returns:
        SandboxRunResult with stdout, stderr, returncode, and timed_out flag.

    Raises:
        ValueError: If root_path is not a directory.
        VenvNotFoundError: If neither .venv nor venv exists under root_path.
    """
    args = list(pip_args) if pip_args else []
    return run_module_in_project_sandbox(root_path, "pip", args, timeout_seconds)
