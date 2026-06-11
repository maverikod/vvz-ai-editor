"""Edit subdir allocation inside File Subtree (C-005–C-008, C-019).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

EDIT_SUBDIR_SUFFIX = "-edit"


@dataclass(frozen=True)
class CoreSessionPaths:
    """Paths for one core EditSession workspace-mode open."""

    origin_path: Path
    edit_subdir: Path
    session_source_path: Path
    session_dir: Path


def edit_subdir_name(origin_filename: str) -> str:
    """Return fixed edit subdirectory name: ``{basename}-edit``."""
    name = Path(origin_filename).name
    if not name:
        raise ValueError("origin_filename must be non-empty")
    return f"{name}{EDIT_SUBDIR_SUFFIX}"


def allocate_edit_subdir(
    *, file_subtree_dir: Path, origin_filename: str
) -> CoreSessionPaths:
    """Create ``file_subtree_dir/{origin_filename}-edit/`` (mkdir, idempotent).

    At most one edit subdirectory per file path within a CA session file subtree.
    Does not copy origin snapshot; caller writes ``origin_path`` separately.
    """
    subdir_name = edit_subdir_name(origin_filename)
    edit_subdir = (file_subtree_dir / subdir_name).resolve()
    edit_subdir.mkdir(parents=True, exist_ok=True)
    origin_path = file_subtree_dir / Path(origin_filename).name
    session_source_path = edit_subdir / Path(origin_filename).name
    return CoreSessionPaths(
        origin_path=origin_path,
        edit_subdir=edit_subdir,
        session_source_path=session_source_path,
        session_dir=edit_subdir,
    )


def remove_file_subtree(*, file_subtree_dir: Path) -> None:
    """Remove entire File Subtree (C-006): origin snapshot and all edit subdirectories.

    Inverse of ``ensure_file_subtree`` in ``editor_workspace_paths``. No-op when
    ``file_subtree_dir`` is missing or not a directory.
    """
    if file_subtree_dir.is_dir():
        shutil.rmtree(file_subtree_dir)
