"""
Type checker using mypy as a library.

When no config is provided, uses a minimal config that excludes .venv, venv,
and .mypy_cache so mypy does not crawl the virtualenv (major speedup).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Mypy line format: path:line:column: severity: message or path:line: severity: message
_MYPY_LINE_RE = re.compile(r"^(.+):(\d+):(\d+):\s*(error|note):")
_MYPY_LINE_RE_NOCOL = re.compile(r"^(.+):(\d+):\s*(error|note):")

# Minimal mypy config to exclude .venv/venv so single-file runs don't crawl them
_MYPY_EXCLUDE_VENV_CONFIG = b"""[mypy]
exclude = (\\.venv|venv|\\.mypy_cache)/
"""


def _build_single_file_config(config_file: Path) -> Optional[Path]:
    """
    Create a temporary mypy config that keeps original options but removes
    top-level scope expanders (`files`/`modules`) in primary mypy section.

    This keeps single-file invocation bounded to the explicit target argument.

    Args:
        config_file: Path to original mypy config file (.ini or pyproject.toml).

    Returns:
        Path to temporary sanitised config, or None if no scope keys were removed.
    """
    try:
        text = config_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read mypy config %s: %s", config_file, exc)
        return None

    section_header = (
        "[tool.mypy]" if config_file.suffix.lower() == ".toml" else "[mypy]"
    )
    in_target_section = False
    skipping_multiline_value = False
    removed_scope_keys = False
    sanitized_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_target_section = stripped == section_header
            skipping_multiline_value = False
            sanitized_lines.append(line)
            continue

        if in_target_section:
            if skipping_multiline_value:
                if "]" in stripped:
                    skipping_multiline_value = False
                continue
            if re.match(r"^(files|modules)\s*=", stripped):
                removed_scope_keys = True
                if "[" in stripped and "]" not in stripped:
                    skipping_multiline_value = True
                continue
        sanitized_lines.append(line)

    if not removed_scope_keys:
        return None

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=config_file.suffix or ".ini",
        prefix="mypy_single_file_",
        delete=False,
        encoding="utf-8",
    ) as temp_file:
        temp_file.write("\n".join(sanitized_lines) + "\n")
        return Path(temp_file.name)


def resolve_mypy_config_for_single_file(
    file_path: Path,
    *,
    explicit_config: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve pyproject.toml to use for a single-file mypy run.

    If ``explicit_config`` is set, returns it. Otherwise walks parents of
    ``file_path`` for ``pyproject.toml``, skipping a directory that looks like
    this repository root (contains a ``code_analysis`` package dir).

    Args:
        file_path: Path to the Python file being type-checked.
        explicit_config: Optional explicit config path; returned as-is when set.

    Returns:
        Resolved config path, or None if no suitable pyproject.toml was found.
    """
    if explicit_config is not None:
        return explicit_config.resolve()
    cur = file_path.resolve()
    for d in [cur.parent, *cur.parents]:
        candidate = d / "pyproject.toml"
        if not candidate.is_file():
            continue
        if (d / "code_analysis").is_dir():
            continue
        return candidate.resolve()
    return None


def _filter_mypy_errors_to_target(
    target_path: Path, raw_lines: List[str], cwd: Optional[str]
) -> List[str]:
    """
    Keep only mypy error/note lines that refer to the target file.

    Mypy follows imports and reports errors from many files; this restricts
    the returned list to the single file the caller asked for (deterministic
    single-file scope).

    Args:
        target_path: Resolved path of the file that was type-checked.
        raw_lines: All lines from mypy stdout/stderr.
        cwd: Working directory mypy used (for resolving relative paths).

    Returns:
        Lines that match file:line:col: severity and whose path equals target_path.
    """
    target_resolved = target_path.resolve()
    result: List[str] = []
    base = Path(cwd).resolve() if cwd else Path.cwd()
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        match = _MYPY_LINE_RE.match(line) or _MYPY_LINE_RE_NOCOL.match(line)
        if not match:
            continue
        path_str = match.group(1).strip()
        try:
            p = (
                (base / path_str).resolve()
                if not Path(path_str).is_absolute()
                else Path(path_str).resolve()
            )
            if p == target_resolved:
                result.append(line)
        except (OSError, RuntimeError):
            continue
    return result


def type_check_with_mypy(
    file_path: Path,
    config_file: Optional[Path] = None,
    ignore_errors: bool = False,
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Type check Python code using mypy as a library.

    Args:
        file_path: Path to Python file to type check
        config_file: Optional path to mypy config file
        ignore_errors: If True, treat errors as warnings

    Returns:
        Tuple of (success, error_message, list_of_errors)
    """
    # IMPORTANT:
    # The server process can inject command paths into PYTHONPATH (spawn-mode helpers),
    # and this project contains a package named `code_analysis.commands.ast` that may
    # shadow the stdlib `ast` module for in-process tooling. Running mypy via its
    # library API inside the server process can therefore fail in non-obvious ways.
    # To keep the MCP command robust, always run mypy via subprocess with sanitized
    # environment (see `_type_check_with_subprocess`).
    return _type_check_with_subprocess(file_path, config_file, ignore_errors)


def _type_check_with_subprocess(
    file_path: Path,
    config_file: Optional[Path] = None,
    ignore_errors: bool = False,
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Run mypy in a subprocess with sanitized environment.

    Notes:
        Single-file mode: exactly one file target is passed to mypy (resolved
        absolute path). Config may be stripped of files/modules to avoid
        package-wide scope. Output is filtered to the requested file only.

    Args:
        file_path: Path to Python file to type check.
        config_file: Optional path to mypy config file.
        ignore_errors: If True, treat errors as warnings.

    Returns:
        Tuple of (success, error_message, list_of_errors).
    """
    try:
        # Single-file target: one positional argument only (no package path).
        target_file = file_path.resolve()
        cmd: list[str]
        cwd: Optional[str] = None
        tmp_config: Optional[Path] = None

        if config_file:
            # Preserve config support, but always keep single-file target scope.
            config_for_single_file = _build_single_file_config(config_file)
            effective_config = config_for_single_file or config_file
            if config_for_single_file is not None:
                tmp_config = config_for_single_file
            cmd = ["mypy", str(target_file), "--config-file", str(effective_config)]
            cwd = str(config_file.parent.resolve())
        else:
            # No config: use minimal config that excludes .venv/venv so mypy
            # does not crawl the project's virtualenv (avoids ~minutes per file).
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".ini",
                prefix="mypy_exclude_venv_",
                delete=False,
            ) as f:
                f.write(_MYPY_EXCLUDE_VENV_CONFIG)
                tmp_config = Path(f.name)
            cmd = ["mypy", str(target_file), "--config-file", str(tmp_config)]

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            cwd=cwd,
        )

        if tmp_config is not None:
            try:
                tmp_config.unlink(missing_ok=True)
            except OSError:
                pass

        raw_lines: List[str] = []
        if result.stdout:
            raw_lines.extend(
                [line for line in result.stdout.split("\n") if line.strip()]
            )
        if result.stderr:
            raw_lines.extend(
                [line for line in result.stderr.split("\n") if line.strip()]
            )

        # Scope output to the single requested file (mypy follows imports and
        # reports errors from many modules; we return only errors for target_file).
        errors = _filter_mypy_errors_to_target(target_file, raw_lines, cwd)

        if result.returncode != 0:
            # After filtering, errors may be empty even when mypy returned
            # non-zero exit code. This happens when mypy prints only a summary
            # line such as 'Found 1 error in 1 file (checked 1 source file)'
            # that does not match the target path and is stripped by
            # _filter_mypy_errors_to_target. The file itself has no type
            # errors in that case -- treat as success.
            if not errors:
                logger.debug(
                    "mypy returncode=%d but no target-file errors after"
                    " output filtering; treating as success for %s",
                    result.returncode,
                    target_file,
                )
                return (True, None, [])
            error_msg = f"Found {len(errors)} mypy errors"
            if ignore_errors:
                logger.info(f"{error_msg} in {target_file} (ignored)")
                return (True, None, errors)
            logger.warning(f"{error_msg} in {target_file}")
            return (False, error_msg, errors)

        logger.debug(f"No mypy errors found in {target_file}")
        return (True, None, [])

    except subprocess.TimeoutExpired:
        logger.warning("Mypy type checking timed out")
        return (False, "Type checking timed out", [])
    except FileNotFoundError:
        logger.warning("Mypy not found, skipping type checking")
        return (False, "Mypy not installed", [])
    except Exception as e:
        logger.warning(f"Error during type checking: {e}")
        return (False, str(e), [])


def type_check_project_with_mypy(
    project_path: Path,
    config_file: Optional[Path] = None,
    timeout_sec: int = 120,
) -> Tuple[bool, Dict[str, List[str]]]:
    """
    Run mypy once on the whole project directory (excluding .venv/venv).

    Much faster than per-file runs. Returns per-file error lines keyed by
    normalized absolute path.

    Args:
        project_path: Root directory to check.
        config_file: Optional mypy config (if None, uses exclude-venv config).
        timeout_sec: Subprocess timeout.

    Returns:
        (success, per_file_errors). per_file_errors maps path str -> list of
        error/note lines for that file.
    """
    per_file: Dict[str, List[str]] = {}
    project_path = project_path.resolve()
    cwd = str(project_path)

    if config_file:
        config_path = str(config_file)
    else:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".ini",
            prefix="mypy_exclude_venv_",
            delete=False,
        ) as f:
            f.write(_MYPY_EXCLUDE_VENV_CONFIG)
            config_path = f.name
    try:
        cmd = ["mypy", str(project_path), "--config-file", config_path]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            cwd=cwd,
        )
    finally:
        if not config_file:
            try:
                os.unlink(config_path)
            except OSError:
                pass

    out = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in out.split("\n"):
        line = line.strip()
        if not line or (": error:" not in line and ": note:" not in line):
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_part = parts[0].strip()
        try:
            p = (
                (project_path / file_part).resolve()
                if not Path(file_part).is_absolute()
                else Path(file_part).resolve()
            )
            key = str(p)
            if key not in per_file:
                per_file[key] = []
            per_file[key].append(line)
        except Exception:
            continue
    return (result.returncode == 0, per_file)
