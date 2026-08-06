"""Pipeline-level gate that the shipped documentation examples still work ({p036}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: this check discovers every example script under ``docs/examples/``
(never a hard-coded filename -- more examples will be added there as {p036}
grows) and executes each one for real, as an independent OS subprocess with
``sys.executable`` and ``PYTHONPATH`` pointed at ``<repo_root>/src`` so
``tree_engine`` is importable exactly the way a fresh reader of the docs
would run the script. A subprocess is deliberate, not incidental: an example
that raises, calls ``sys.exit``, or hangs must never be able to take the
whole pipeline process down with it; the parent only ever observes an exit
code, captured stdout/stderr, and elapsed time.

A run is judged on three independent axes, and failing any one fails that
example:

1. Exit code. Every current example (``docs/examples/full_cycle.py``) prints
   its own "ALL STAGES PASSED" banner and asserts every claim it narrates
   before that point, so a non-zero exit already means either an unhandled
   exception or a failed assertion inside the example itself.
2. Timeout. A fixed wall-clock budget (see ``TIMEOUT_SECONDS``) bounds a
   hung example to a finite failure instead of hanging this check --
   and by extension CI -- forever. On timeout the subprocess is killed and
   whatever partial output it produced before that point is still reported.
3. Residue. A documentation example is required to be self-contained: it
   must create its own temporary directory and clean it up, and it must
   never write into the repository working tree it was read from. This
   check proves both directly rather than trusting the example's own
   cleanup code: it snapshots the OS temp directory's entries and (when the
   repository is a real git checkout) `git status --porcelain` immediately
   before and after each run, and flags any new temp entry or any new
   working-tree change as a residue failure, naming exactly what leaked.
   Each example is additionally run with its working directory set to a
   throwaway scratch directory outside the repository (removed
   unconditionally afterward), so an example that assumes an unwritten
   contract -- "my relative paths land wherever I'm invoked from" -- cannot
   silently write into the repository even by accident.

Every example runs independently: one failing or hanging example never
aborts the rest, so a single invocation reports every example's verdict.
The check registers itself on the shared pipeline registry (see
``pipeline/registry.py``) and reports through ``CheckResult``/
``CheckStatus`` only -- it never prints and never calls ``sys.exit`` itself;
the pipeline CLI owns all console output and process exit codes.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Set

from pipeline import registry
from pipeline.registry import CheckResult

CHECK_NAME = "check-examples"
CHECK_DESCRIPTION = (
    "Execute every documentation example under docs/examples/ as a real "
    "subprocess (per {p036}): fail on a non-zero exit, a hang past the "
    "timeout, or any residue -- a leaked temp entry or a modified "
    "repository working tree."
)

# Where example scripts live and where the importable engine lives, both
# relative to the repository root (three directories up from this file:
# pipeline/checks/check_examples.py -> pipeline/checks -> pipeline -> root).
EXAMPLES_RELATIVE = Path("docs") / "examples"
SRC_RELATIVE = Path("src")

# Wall-clock budget per example. The real full_cycle.py example completes in
# a few seconds; 60s is a generous margin (roughly 10-20x real runtime) that
# comfortably absorbs a slow CI machine while still turning a genuinely hung
# example into a bounded failure rather than a check that never returns.
TIMEOUT_SECONDS = 60

# Cap on embedded stdout/stderr per example in the report: enough to
# diagnose a failure without re-running it, not so much that one runaway
# example can blow up the whole check's output.
MAX_OUTPUT_CHARS = 10000


def _repo_root() -> Path:
    """Repository root of the tree this check file ships inside."""
    return Path(__file__).resolve().parents[2]


def _discover_examples(examples_dir: Path) -> List[Path]:
    """Every ``*.py`` file under ``examples_dir``, deterministically ordered.

    Never a hard-coded example name: a script dropped into this directory
    later is picked up automatically, with zero change to this module.
    """
    return sorted(p for p in examples_dir.rglob("*.py") if p.is_file())


def _decode(data: object) -> str:
    """Normalize subprocess-captured output to ``str`` regardless of
    whether it arrived as text (the normal case) or bytes (what a killed,
    partially-decoded ``TimeoutExpired`` occasionally carries)."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n... [{omitted} more character(s) truncated]"


def _tempdir_entries() -> Optional[Set[str]]:
    """Snapshot of the OS temp directory's entries, or ``None`` if it could
    not be listed (never treated as a residue finding either way)."""
    try:
        return set(os.listdir(tempfile.gettempdir()))
    except OSError:
        return None


def _git_status_lines(repo_root: Path) -> Optional[List[str]]:
    """``git status --porcelain`` output split into lines, or ``None`` when
    ``repo_root`` is not a real git checkout (a verbatim copy used for
    isolated testing, for instance) or the command itself could not run.
    ``None`` means "cannot judge", never "clean" -- it disables this half of
    the residue check rather than asserting a false negative."""
    if not (repo_root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.splitlines()


@dataclasses.dataclass(frozen=True)
class ExampleResult:
    """One example script's verdict: pass/fail plus everything needed to
    diagnose a failure without re-running it."""

    name: str
    passed: bool
    exit_code: Optional[int]
    duration_seconds: float
    detail: str
    stdout: str = ""
    stderr: str = ""

    def format(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        exit_repr = "TIMEOUT" if self.exit_code is None else str(self.exit_code)
        head = (
            f"[{status}] {self.name} - {self.detail} "
            f"(exit={exit_repr}, {self.duration_seconds:.2f}s)"
        )
        if self.passed:
            return head
        parts = [head]
        if self.stdout.strip():
            parts.append("--- stdout ---\n" + _truncate(self.stdout))
        if self.stderr.strip():
            parts.append("--- stderr ---\n" + _truncate(self.stderr))
        return "\n".join(parts)


def _run_one_example(path: Path, repo_root: Path, src_dir: Path) -> ExampleResult:
    """Run one example as a real subprocess and judge exit code, timeout,
    and residue -- independently, so one bad axis never masks another."""

    name = str(path.relative_to(repo_root))

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")

    # Run outside the repository entirely, so an example that (incorrectly)
    # assumes its relative paths land wherever it was invoked from cannot
    # write into the repository working tree even by accident.
    scratch_cwd = Path(tempfile.mkdtemp(prefix="check-examples-cwd-"))

    before_temp = _tempdir_entries()
    before_git = _git_status_lines(repo_root)
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=scratch_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        duration = time.monotonic() - start
        exit_code: Optional[int] = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        timed_out = True
        exit_code = None
        stdout, stderr = _decode(exc.stdout), _decode(exc.stderr)
    finally:
        shutil.rmtree(scratch_cwd, ignore_errors=True)

    after_temp = _tempdir_entries()
    after_git = _git_status_lines(repo_root)

    residue: List[str] = []
    if before_temp is not None and after_temp is not None:
        leaked = sorted(after_temp - before_temp)
        if leaked:
            residue.append(
                f"leaked {len(leaked)} temp entry(ies) under "
                f"{tempfile.gettempdir()}: {leaked}"
            )
    if before_git is not None and after_git is not None:
        git_leak = sorted(set(after_git) - set(before_git))
        if git_leak:
            residue.append(f"repository working tree changed: {git_leak}")

    if timed_out:
        detail = f"timed out after {TIMEOUT_SECONDS}s and was killed"
        passed = False
    elif exit_code != 0:
        detail = f"non-zero exit code {exit_code}"
        passed = False
    elif residue:
        detail = "; ".join(residue)
        passed = False
    else:
        detail = f"exited 0 in {duration:.2f}s, no residue"
        passed = True

    return ExampleResult(name, passed, exit_code, duration, detail, stdout, stderr)


def check_examples() -> CheckResult:
    """Discover and run every documentation example; report one verdict.

    Every example runs independently -- one failing or hanging example
    never stops the rest -- so a single run's output names every example
    that is actually broken, not just the first one hit.
    """

    repo_root = _repo_root()
    examples_dir = repo_root / EXAMPLES_RELATIVE
    src_dir = repo_root / SRC_RELATIVE

    if not examples_dir.is_dir():
        return CheckResult.fail(
            message=f"examples directory not found at {examples_dir}"
        )

    examples = _discover_examples(examples_dir)
    if not examples:
        return CheckResult.fail(
            message=f"no example script (*.py) found under {examples_dir}"
        )

    results = [_run_one_example(path, repo_root, src_dir) for path in examples]
    output = "\n".join(result.format() for result in results)
    failed = [result for result in results if not result.passed]
    passed_count = len(results) - len(failed)

    if not failed:
        return CheckResult.ok(
            message=f"{passed_count}/{len(results)} documentation example(s) passed",
            output=output,
        )
    return CheckResult.fail(
        message=(
            f"{len(failed)}/{len(results)} documentation example(s) failed: "
            f"{', '.join(result.name for result in failed)}"
        ),
        output=output,
    )


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_examples)
