"""
Shared guards for read_project_text_file / write_project_text_lines.

These commands target non-code plain text (docs, data-ish configs, etc.) and
other blocked program-source suffixes. **Read:** Python paths are delegated inside
``read_project_text_file`` to ``get_file_lines``. **Write:** ``write_project_text_lines``
rejects Python and other blocked source suffixes; use ``replace_file_lines`` or CST
commands for Python.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.venv_path_policy import (
    format_project_venv_write_forbidden_message,
    path_is_under_project_local_venv,
)

# Python and Python-ecosystem sources — use CST (and related) commands, not raw text I/O.
FORBIDDEN_PYTHON_SOURCE_SUFFIXES = frozenset(
    {".py", ".pyi", ".pyw", ".pyx", ".pxd", ".pxi"}
)

# Other common program-source extensions (not an exhaustive language list; avoids .js/.ts where
# many projects use those suffixes for config). Paths with these suffixes are refused.
FORBIDDEN_NON_PYTHON_CODE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".clj",
        ".cljs",
        ".cpp",
        ".cs",
        ".cxx",
        ".dart",
        ".erl",
        ".ex",
        ".exs",
        ".fs",
        ".fsx",
        ".go",
        ".h",
        ".hpp",
        ".hs",
        ".hrl",
        ".ipynb",
        ".jl",
        ".java",
        ".kt",
        ".kts",
        ".lua",
        ".ml",
        ".mli",
        ".pas",
        ".php",
        ".pl",
        ".pm",
        ".pp",
        ".r",
        ".rb",
        ".rs",
        ".scala",
        ".svelte",
        ".swift",
        ".vb",
        ".vue",
    }
)

# Backward-compatible name for tests and callers that only need the union for assertions.
FORBIDDEN_TEXT_SUFFIXES = (
    FORBIDDEN_PYTHON_SOURCE_SUFFIXES | FORBIDDEN_NON_PYTHON_CODE_SUFFIXES
)


def is_python_text_path(file_path: str) -> bool:
    """True if ``file_path`` uses a Python / Python-ecosystem source suffix."""
    return Path(file_path).suffix.lower() in FORBIDDEN_PYTHON_SOURCE_SUFFIXES


def reject_if_python_text_path(file_path: str) -> Optional[ErrorResult]:
    """
    Reject paths that refer to Python (or Python-ecosystem) source files.

    Prefer :func:`reject_if_source_code_text_path`, which enforces the full non-code policy.

    Args:
        file_path: Path as provided to the command (relative to project root).

    Returns:
        ErrorResult with code PYTHON_FILE_FORBIDDEN, or None if allowed by this check.
    """
    suf = Path(file_path).suffix.lower()
    if suf in FORBIDDEN_PYTHON_SOURCE_SUFFIXES:
        return ErrorResult(
            message=(
                "Python source files cannot be read or written with this command; use CST "
                "commands (cst_load_file, cst_modify_tree, cst_save_tree) "
                "instead."
            ),
            code="PYTHON_FILE_FORBIDDEN",
            details={
                "file_path": file_path,
                "forbidden_suffix": suf,
                "reason": "python_source",
            },
        )
    return None


def reject_if_non_python_code_text_path(file_path: str) -> Optional[ErrorResult]:
    """
    Reject paths whose suffix is a known non-Python program source type.

    Returns:
        ErrorResult with code CODE_FILE_FORBIDDEN, or None if allowed.
    """
    suf = Path(file_path).suffix.lower()
    if suf in FORBIDDEN_NON_PYTHON_CODE_SUFFIXES:
        return ErrorResult(
            message=(
                "This command is only for non-code text files (documentation, plain configs, "
                "etc.). Source code paths are not supported; use the appropriate editor or "
                "workflow for that language."
            ),
            code="CODE_FILE_FORBIDDEN",
            details={
                "file_path": file_path,
                "forbidden_suffix": suf,
                "reason": "non_python_source",
            },
        )
    return None


def reject_if_write_under_project_venv(
    absolute_path: Path, project_root: Path
) -> Optional[ErrorResult]:
    """
    Reject server-side writes targeting paths under ``project_root/.venv`` or ``venv``.

    Pip and subprocess tooling may still modify the venv; MCP file commands must not.
    """
    if path_is_under_project_local_venv(absolute_path, project_root):
        return ErrorResult(
            message=format_project_venv_write_forbidden_message(),
            code="PROJECT_VENV_WRITE_FORBIDDEN",
            details={
                "resolved_path": str(absolute_path),
                "project_root": str(project_root),
            },
        )
    return None


def reject_if_source_code_text_path(file_path: str) -> Optional[ErrorResult]:
    """
    Enforce the full policy: refuse Python/* and other blocked source suffixes.

    ``read_project_text_file`` routes Python paths to ``get_file_lines``; this guard is
    still used for callers that need the full reject-both policy. ``write_project_text_lines``
    applies this policy (no Python writes).
    """
    err = reject_if_python_text_path(file_path)
    if err is not None:
        return err
    return reject_if_non_python_code_text_path(file_path)
