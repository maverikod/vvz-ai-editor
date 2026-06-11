"""
Bounded subprocess capture and POSIX timeout/process-group behavior for project_sandbox.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import shutil
import signal
import sys
from pathlib import Path

import pytest

from ai_editor.core import project_sandbox as ps
from ai_editor.core.project_sandbox import run_in_project_sandbox


def _install_minimal_venv(root: Path) -> None:
    bindir = root / ".venv" / "bin"
    bindir.mkdir(parents=True)
    shutil.copy(Path(sys.executable), bindir / "python")


def test_stdout_truncated_when_exceeding_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _install_minimal_venv(root)
    script = root / "spam.py"
    script.write_text("print('x' * 50000)\n", encoding="utf-8")
    monkeypatch.setattr(ps, "MAX_CAPTURE_BYTES_PER_STREAM", 3000)
    r = run_in_project_sandbox(root, "spam.py", timeout_seconds=30)
    assert r.timed_out is False
    assert r.returncode == 0
    assert "[... output truncated ...]" in r.stdout


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_timeout_sets_timed_out_and_uses_killpg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _install_minimal_venv(root)
    script = root / "slow.py"
    script.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    killpg_calls: list[tuple[int, int]] = []
    real_killpg = os.killpg

    def track_killpg(pgid: int, sig: int) -> None:
        killpg_calls.append((pgid, sig))
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", track_killpg)
    r = run_in_project_sandbox(root, "slow.py", timeout_seconds=2)
    assert r.timed_out is True
    assert r.returncode is None
    assert any(sig == signal.SIGKILL for _, sig in killpg_calls)


def test_post_run_delay_applied_after_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _install_minimal_venv(root)
    script = root / "hi.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    sleeps: list[float] = []

    def track_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ps.time, "sleep", track_sleep)
    r = run_in_project_sandbox(root, "hi.py", post_run_delay_seconds=0.25)
    assert r.timed_out is False
    assert r.returncode == 0
    assert "hello" in r.stdout
    assert sleeps == [0.25]
    assert r.post_run_delay_seconds_applied == 0.25


def test_post_run_delay_negative_raises(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _install_minimal_venv(root)
    script = root / "hi.py"
    script.write_text("print('x')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative"):
        run_in_project_sandbox(root, "hi.py", post_run_delay_seconds=-1.0)


def test_small_script_no_truncation_marker(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _install_minimal_venv(root)
    script = root / "hi.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    r = run_in_project_sandbox(root, "hi.py")
    assert r.timed_out is False
    assert r.returncode == 0
    assert "hello" in r.stdout
    assert "[... output truncated ...]" not in r.stdout
