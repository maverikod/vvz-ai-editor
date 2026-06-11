"""
Unit tests for core EditSession lifecycle (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.edit_session.edit_session import (
    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,
    EditSession,
    EditSessionError,
    SessionTreeValidity,
    get_active_session,
)
from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.core.tree_lifecycle.checksum import compute_content_checksum


def _setup_valid_json(tmp_path: Path) -> tuple[Path, Path, str]:
    rel_path = "nested/demo.json"
    source_abs = tmp_path / rel_path
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    content = '{"counter": 1}\n'
    source_abs.write_text(content, encoding="utf-8")
    TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=rel_path,
        content_checksum=compute_content_checksum(content),
    )
    return tmp_path, source_abs, rel_path


def _setup_invalid_json(tmp_path: Path) -> tuple[Path, Path, str]:
    rel_path = "broken/demo.json"
    source_abs = tmp_path / rel_path
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    source_abs.write_text("not-json\n", encoding="utf-8")
    return tmp_path, source_abs, rel_path


def test_open_rejects_content_when_valid_external_file(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    with pytest.raises(EditSessionError) as exc_info:
        EditSession.open(
            source_abs=source_abs,
            project_root=root,
            file_path=rel,
            content='{"counter": 99}\n',
        )
    assert exc_info.value.args[0] == CONTENT_NOT_ALLOWED_FOR_VALID_FILE


def test_valid_mutation_commits_tree_and_source(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        assert session.tree_validity == SessionTreeValidity.VALID
        initial_commits = len(session.session_repo.log())
        assert initial_commits == 1

        def mutator(denuded: str) -> str:
            return denuded.replace('"counter": 1', '"counter": 42')

        session.apply_valid_tree_mutation(mutator)
        assert len(session.session_repo.log()) == initial_commits + 1
        assert "42" in session.session_source_path.read_text(encoding="utf-8")
        assert session.session_tree_path.is_file()
    finally:
        session.close()


def test_invalid_plaintext_commits_source_only(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_invalid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        assert session.tree_validity == SessionTreeValidity.INVALID
        before = len(session.session_repo.log())
        session.apply_plaintext_mutation("<<<broken>>>\n")
        assert len(session.session_repo.log()) == before + 1
        assert session.session_repo.log()[0].message == "session: plaintext mutation"
        assert session.tree_validity == SessionTreeValidity.INVALID
    finally:
        session.close()


def test_revalidation_restores_valid_mode(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_invalid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        assert session.tree_validity == SessionTreeValidity.INVALID
        session.apply_plaintext_mutation('{"counter": 7}\n')
        assert session.tree_validity == SessionTreeValidity.VALID
        assert session.session_tree_path.is_file()
    finally:
        session.close()


def test_open_workspace_mode_uses_edit_subdir_not_sibling(tmp_path: Path) -> None:
    session_root = tmp_path / "ca-session-1"
    file_subtree = session_root / "files" / "proj"
    file_subtree.mkdir(parents=True)
    origin_path = file_subtree / "foo.py"
    origin_path.write_text('print("hi")\n', encoding="utf-8")
    edit_subdir = file_subtree / "foo.py-workspace-edit"
    edit_subdir.mkdir()

    session = EditSession.open(
        source_abs=origin_path,
        project_root=tmp_path,
        file_path="foo.py",
        workspace_session_root=session_root,
        workspace_file_subtree_root=file_subtree,
        workspace_origin_path=origin_path,
        workspace_edit_subdir=edit_subdir,
    )
    try:
        assert session.session_dir == edit_subdir.resolve()
        assert session.source_abs == origin_path.resolve()
        assert session.workspace_session_root == session_root.resolve()
        assert session.workspace_file_subtree_root == file_subtree.resolve()
        assert session.tree_validity == SessionTreeValidity.INVALID
        assert session.session_dir != origin_path.parent / f"{origin_path.name}-dummy"
        assert session.session_source_path == edit_subdir / "foo.py"
        assert session.session_source_path.read_text(
            encoding="utf-8"
        ) == origin_path.read_text(encoding="utf-8")
    finally:
        session.close()


def test_close_removes_session_directory(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    session_dir = session.session_dir
    assert session_dir.exists()
    sid = session.session_id
    session.close()
    assert not session_dir.exists()
    with pytest.raises(KeyError):
        get_active_session(sid)
