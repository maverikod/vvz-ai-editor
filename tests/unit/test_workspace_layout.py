"""Unit tests for workspace_layout (C-008 Edit Subdirectory allocation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.edit_session.workspace_layout import (
    EDIT_SUBDIR_SUFFIX,
    allocate_edit_subdir,
    edit_subdir_name,
)


def test_edit_subdir_name_fixed_suffix() -> None:
    assert edit_subdir_name("mod.py") == f"mod.py{EDIT_SUBDIR_SUFFIX}"
    assert edit_subdir_name("notes.txt") == f"notes.txt{EDIT_SUBDIR_SUFFIX}"


def test_allocate_edit_subdir_uses_fixed_suffix(tmp_path: Path) -> None:
    """allocate_edit_subdir creates {basename}-edit under file_subtree_dir."""
    file_subtree_dir = tmp_path / "subtree"
    file_subtree_dir.mkdir()

    paths_a = allocate_edit_subdir(
        file_subtree_dir=file_subtree_dir, origin_filename="mod.py"
    )
    paths_b = allocate_edit_subdir(
        file_subtree_dir=file_subtree_dir, origin_filename="mod.py"
    )

    assert paths_a.edit_subdir == paths_b.edit_subdir
    assert paths_a.edit_subdir.name == f"mod.py{EDIT_SUBDIR_SUFFIX}"
    assert paths_a.edit_subdir.is_dir()
    assert paths_a.edit_subdir.parent.resolve() == file_subtree_dir.resolve()
    assert paths_a.origin_path == file_subtree_dir / "mod.py"
    assert paths_a.origin_path.parent == file_subtree_dir
    assert paths_a.session_source_path == paths_a.edit_subdir / "mod.py"
    assert paths_a.session_dir == paths_a.edit_subdir
