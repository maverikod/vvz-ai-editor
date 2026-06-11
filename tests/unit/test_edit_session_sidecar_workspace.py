"""CST sidecar workspace path tests (T-006 A-001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.edit_session.edit_session import EditSession, EditSessionError


def _open_workspace_session(tmp_path: Path) -> tuple[EditSession, Path, Path]:
    session_root = tmp_path / "sid"
    subtree = session_root / "files" / "proj"
    origin = subtree / "foo.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("x = 0\n", encoding="utf-8")
    edit_subdir = subtree / "edit-uuid"
    edit_subdir.mkdir()
    session = EditSession.open(
        source_abs=origin,
        project_root=tmp_path,
        file_path="foo.py",
        workspace_session_root=session_root,
        workspace_file_subtree_root=subtree,
        workspace_origin_path=origin,
        workspace_edit_subdir=edit_subdir,
    )
    return session, origin, edit_subdir


def test_workspace_open_session_tree_path_under_edit_subdir(tmp_path: Path) -> None:
    session, origin, edit_subdir = _open_workspace_session(tmp_path)
    try:
        assert session.session_dir == edit_subdir.resolve()
        assert session.session_tree_path == (edit_subdir / "foo.py.tree").resolve()
        assert session.tree_abs == session.session_tree_path
        assert session.session_tree_path.parent == edit_subdir
        assert not (origin.parent / "foo.py.tree").exists()
    finally:
        session.close()


def test_apply_cst_sidecar_mutation_rejects_outside_edit_subdir(
    tmp_path: Path,
) -> None:
    session, origin, _edit_subdir = _open_workspace_session(tmp_path)
    try:
        project_sidecar = origin.parent / "foo.py.tree"
        project_sidecar.write_text("dummy\n", encoding="utf-8")
        with pytest.raises(EditSessionError) as exc_info:
            session.apply_cst_sidecar_mutation("x=1\n", sidecar_abs=project_sidecar)
        assert exc_info.value.args[0] == "WORKSPACE_SIDECAR_ESCAPE"
    finally:
        session.close()


def test_apply_cst_sidecar_mutation_accepts_edit_subdir_sidecar(
    tmp_path: Path,
) -> None:
    session, _origin, _edit_subdir = _open_workspace_session(tmp_path)
    try:
        session.session_tree_path.write_text("dummy sidecar\n", encoding="utf-8")
        session.apply_cst_sidecar_mutation(
            "x=1\n",
            sidecar_abs=session.session_tree_path,
        )
        assert session.session_tree_path.is_file()
    finally:
        session.close()
