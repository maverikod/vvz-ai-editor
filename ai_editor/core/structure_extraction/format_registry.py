"""
Format detection and scan policy for structure extraction / fs_grep.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".pyw",
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".markdown",
        ".txt",
        ".toml",
        ".ini",
        ".cfg",
    }
)

PY_SUFFIXES: frozenset[str] = frozenset({".py", ".pyi", ".pyw"})
JSON_SUFFIX = ".json"
YAML_SUFFIXES: frozenset[str] = frozenset({".yaml", ".yml"})
MD_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown"})
TEXT_PLAIN_SUFFIXES: frozenset[str] = frozenset({".txt", ".toml", ".ini", ".cfg"})

DEFAULT_PATH_EXCLUDE_SEGMENTS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "site-packages",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "logs",
    }
)

LOG_FILE_GLOBS: tuple[str, ...] = ("*.log", "*.out", "*.err", "*.pid")

BINARY_OR_SKIP_GLOBS: tuple[str, ...] = (
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.xz",
    "*.7z",
    "*.bin",
)


def suffix_for_path(path: str | Path) -> str:
    return Path(path).suffix.lower()


def format_group_for_suffix(suffix: str) -> str:
    if suffix in PY_SUFFIXES:
        return "sidecar"
    if suffix == JSON_SUFFIX:
        return "tree-temp"
    if suffix in YAML_SUFFIXES:
        return "tree-temp"
    if suffix in MD_SUFFIXES:
        return "markdown"
    if suffix in TEXT_PLAIN_SUFFIXES:
        return "text"
    return "unknown"


def is_supported_extension(path: str | Path) -> bool:
    return suffix_for_path(path) in SUPPORTED_EXTENSIONS


def is_log_like_path(rel_path: str) -> bool:
    name = Path(rel_path).name
    return any(fnmatch.fnmatch(name, pat) for pat in LOG_FILE_GLOBS)


def matches_skip_glob(rel_path: str) -> bool:
    name = Path(rel_path).name
    return any(fnmatch.fnmatch(name, pat) for pat in BINARY_OR_SKIP_GLOBS)


def path_matches_default_excludes(
    rel_path: str, *, exclude_log_files: bool = True
) -> bool:
    """Return True when a project-relative path should be skipped by default."""
    parts = Path(rel_path).parts
    for part in parts:
        if part in DEFAULT_PATH_EXCLUDE_SEGMENTS:
            return True
    if exclude_log_files and is_log_like_path(rel_path):
        return True
    if matches_skip_glob(rel_path):
        return True
    return False


def should_scan_path(
    rel_path: str,
    *,
    scan_all: bool,
    include_logs: bool = False,
) -> bool:
    """Apply scan_all policy: known formats only vs broad text-readable."""
    if path_matches_default_excludes(rel_path, exclude_log_files=not include_logs):
        if scan_all and include_logs and is_log_like_path(rel_path):
            return True
        return False
    if is_log_like_path(rel_path):
        return bool(scan_all and include_logs)
    if scan_all:
        return True
    return suffix_for_path(rel_path) in SUPPORTED_EXTENSIONS


def validate_scan_policy(*, scan_all: bool, include_logs: bool) -> str | None:
    """Return error code when policy is invalid, else None."""
    if include_logs and not scan_all:
        return "INVALID_SCAN_POLICY"
    return None
