"""
Code linters using CLI subprocesses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def lint_with_flake8(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Lint Python code using the flake8 CLI in a subprocess.

    In-process ``flake8.api.legacy.get_style_guide().check_files()`` is not used:
    it has no wall-clock timeout and could block the server on pathological inputs.
    Subprocess ``flake8`` is capped at 30 seconds and runs with a sanitized
    ``PYTHONPATH`` (see ``_lint_with_subprocess``).
    """
    return _lint_with_subprocess(file_path, ignore)


def lint_with_ruff(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Lint Python code using the ruff CLI in a subprocess.

    Ruff runs as an additional quality gate. It does not replace flake8; both
    linters are kept separate so existing behavior and error reporting remain
    compatible while Ruff-specific checks can be adopted incrementally.
    """
    return _lint_with_ruff_subprocess(file_path, ignore)


def _lint_with_subprocess(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Run flake8 in a subprocess with timeout and sanitized environment."""
    import os
    import subprocess

    try:
        cmd = ["flake8", "--max-line-length=88", str(file_path)]
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        # IMPORTANT:
        # This project contains a package named `code_analysis.commands.ast`, which can
        # shadow the standard library `ast` module if PYTHONPATH is polluted (the server
        # injects command paths into PYTHONPATH for child processes). Flake8 imports
        # stdlib `ast`, so we must sanitize PYTHONPATH for this subprocess.
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0:
            logger.debug(f"No flake8 errors found in {file_path}")
            return (True, None, [])
        else:
            stdout_lines = result.stdout.splitlines() if result.stdout else []
            stderr_lines = result.stderr.splitlines() if result.stderr else []
            errors = [e for e in (stdout_lines + stderr_lines) if e.strip()]

            # Some flake8 failures can print diagnostics only to stderr.
            # If nothing was captured, return a generic failure message.
            error_msg = (
                f"Found {len(errors)} flake8 errors"
                if errors
                else f"flake8 failed with exit code {result.returncode}"
            )
            logger.warning(f"{error_msg} in {file_path}")
            return (False, error_msg, errors)

    except subprocess.TimeoutExpired:
        logger.warning("Flake8 linting timed out")
        return (False, "Linting timed out", [])
    except FileNotFoundError:
        logger.warning("Flake8 not found, skipping linting")
        return (False, "Flake8 not installed", [])
    except Exception as e:
        logger.warning(f"Error during linting: {e}")
        return (False, str(e), [])


def _lint_with_ruff_subprocess(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Run ruff in a subprocess with timeout and sanitized environment."""
    import os
    import subprocess

    try:
        cmd = ["ruff", "check", "--output-format", "concise", str(file_path)]
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0:
            logger.debug(f"No ruff errors found in {file_path}")
            return (True, None, [])

        stdout_lines = result.stdout.splitlines() if result.stdout else []
        stderr_lines = result.stderr.splitlines() if result.stderr else []
        errors = [e for e in (stdout_lines + stderr_lines) if e.strip()]
        error_msg = (
            f"Found {len(errors)} ruff errors"
            if errors
            else f"ruff failed with exit code {result.returncode}"
        )
        logger.warning(f"{error_msg} in {file_path}")
        return (False, error_msg, errors)

    except subprocess.TimeoutExpired:
        logger.warning("Ruff linting timed out")
        return (False, "Ruff linting timed out", [])
    except FileNotFoundError:
        logger.warning("Ruff not found, skipping linting")
        return (False, "Ruff not installed", [])
    except Exception as e:
        logger.warning(f"Error during ruff linting: {e}")
        return (False, str(e), [])
