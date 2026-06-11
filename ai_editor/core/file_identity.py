"""
Project-scoped file path identity helpers.

Centralizes rules for absolute path normalization and how ``relative_path``
relates across ``project_id`` values. Cross-project identity uses the absolute
``path`` only; matching ``relative_path`` alone is never a conflict.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Union

from ai_editor.core.path_normalization import normalize_path_simple

PathLike = Union[str, Path]


class FileIdentityCase(Enum):
    """How two file records relate in terms of project id and paths."""

    SAME_PROJECT_SAME_ABSOLUTE_PATH = "same_project_same_absolute_path"
    DIFFERENT_PROJECT_SAME_ABSOLUTE_PATH = "different_project_same_absolute_path"
    DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY = (
        "different_project_same_relative_path_only"
    )
    UNRELATED = "unrelated"


def normalize_project_file_path(path: PathLike) -> str:
    """Return normalized absolute path string (same rules as ``path`` column)."""
    return normalize_path_simple(path)


def is_database_path_stored_absolute(stored: str) -> bool:
    """True if ``stored`` looks like a legacy absolute filesystem path (not project-relative)."""
    s = (stored or "").strip()
    if not s:
        return False
    return Path(s).is_absolute()


def absolute_path_for_indexed_file(
    project_root: PathLike, row: Mapping[str, Any]
) -> str:
    """
    Normalized absolute path for a ``files`` row.

    Active rows store project-relative POSIX paths in ``path`` (and usually the same
    in ``relative_path``). Legacy rows may store an absolute path in ``path``;
    soft-deleted rows may store an absolute trash path.
    """
    root_resolved = normalize_path_simple(project_root)
    raw_path = (row.get("path") or "").strip()
    raw_rel = (row.get("relative_path") or "").strip()
    if raw_path and is_database_path_stored_absolute(raw_path):
        return normalize_path_simple(raw_path)
    rel = raw_rel or raw_path
    if not rel:
        return root_resolved
    return normalize_path_simple(Path(root_resolved) / rel)


# SQL fragment + bind order: (relative_path, path_as_rel, path_as_abs_legacy)
FILE_ROW_PATH_MATCH_SQL = "(relative_path = ? OR path = ? OR path = ?)"


def file_row_path_match_values(
    *, project_root: PathLike, absolute_path: PathLike
) -> tuple[str, str, str]:
    """Three bind values for :data:`FILE_ROW_PATH_MATCH_SQL` (rel duplicated for OR path)."""
    rel = relative_path_for_project(absolute_path, project_root)
    abs_norm = normalize_path_simple(absolute_path)
    return rel, rel, abs_norm


def relative_path_for_project(abs_path: PathLike, project_root: PathLike) -> str:
    """
    Return project-relative path as POSIX ``str``.

    Raises:
        ValueError: If the normalized absolute path is not under ``project_root``.
    """
    root = Path(project_root).resolve()
    normalized_abs = normalize_path_simple(abs_path)
    abs_obj = Path(normalized_abs)
    try:
        rel = abs_obj.relative_to(root)
    except ValueError as e:
        raise ValueError(
            f"File {normalized_abs} is not within project root {root}"
        ) from e
    return rel.as_posix()


def project_relative_file_posix(file_path: PathLike, project_root: PathLike) -> str:
    """
    Normalize ``file_path`` to a project-relative POSIX string under ``project_root``.

    Absolute paths that lie under the project root are trimmed to the relative suffix.
    Paths that are already project-relative are normalized (forward slashes; no ``./`` prefix).

    Raises:
        ValueError: If ``file_path`` is absolute and not under ``project_root``.
    """
    root = Path(project_root).resolve()
    s = str(file_path).strip().replace("\\", "/")
    if not s:
        return ""
    p = Path(s)
    if p.is_absolute():
        return relative_path_for_project(normalize_path_simple(p), root)
    rel = Path(s).as_posix()
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_same_absolute_file(path_a: PathLike, path_b: PathLike) -> bool:
    """True if both paths denote the same normalized absolute file path."""
    return normalize_path_simple(path_a) == normalize_path_simple(path_b)


def _posix_relative_key(relative_path: str) -> str:
    return Path(relative_path).as_posix()


def classify_file_identity_case(
    *,
    project_id_a: str,
    absolute_path_a: PathLike,
    relative_path_a: str,
    project_id_b: str,
    absolute_path_b: PathLike,
    relative_path_b: str,
) -> FileIdentityCase:
    """
    Classify how file A (project a + paths) relates to file B.

    ``DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY`` is a normal, non-conflicting case
    (e.g. parallel ``.venv/site-packages/...`` trees under different roots).
    """
    abs_a = normalize_path_simple(absolute_path_a)
    abs_b = normalize_path_simple(absolute_path_b)
    rel_a = _posix_relative_key(relative_path_a)
    rel_b = _posix_relative_key(relative_path_b)

    if project_id_a == project_id_b:
        if abs_a == abs_b:
            return FileIdentityCase.SAME_PROJECT_SAME_ABSOLUTE_PATH
        return FileIdentityCase.UNRELATED

    if abs_a == abs_b:
        return FileIdentityCase.DIFFERENT_PROJECT_SAME_ABSOLUTE_PATH
    if rel_a == rel_b:
        return FileIdentityCase.DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY
    return FileIdentityCase.UNRELATED
