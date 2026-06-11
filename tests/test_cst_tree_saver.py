"""
Detailed tests for CST tree_saver: target.tmp path, file lock, cleanup on failure.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import builtins
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.core.cst_tree.node_id_markers import strip_persisted_node_ids
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code
from ai_editor.core.cst_tree.tree_saver import save_tree_to_file
from ai_editor.core.cst_tree.tree_sidecar import (
    read_sidecar_payload,
    verify_sidecar_against_source,
)
from ai_editor.tree.sibling_convention import sibling_tree_path


def _make_db_mock() -> MagicMock:
    """Minimal database mock for save_tree_to_file (transactions, files, execute_batch)."""
    db = MagicMock()
    db.begin_transaction = MagicMock(return_value="tid")
    db.commit_transaction = MagicMock()
    db.rollback_transaction = MagicMock()
    db.select = MagicMock(return_value=[])

    def _execute_side_effect(
        sql: str, params: tuple = (), *args: object, **kwargs: object
    ) -> dict:
        s = str(sql)
        if "SELECT editing_pid" in s:
            return {"affected_rows": 0, "data": [{"editing_pid": None}]}
        if "UPDATE files SET editing_pid" in s:
            return {"affected_rows": 1, "data": None}
        return {"affected_rows": 1, "data": None}

    db.execute = MagicMock(side_effect=_execute_side_effect)
    created = MagicMock()
    created.id = 1
    db.create_file = MagicMock(return_value=created)
    updated = MagicMock()
    updated.id = 1
    db.update_file = MagicMock(return_value=updated)
    # Batch path: execute_batch returns one result per operation
    db.execute_batch = MagicMock(
        return_value=[
            {"affected_rows": 1, "lastrowid": i + 1, "data": None} for i in range(100)
        ]
    )
    return db


@pytest.fixture
def db_mock():
    """Database mock for save_tree_to_file."""
    return _make_db_mock()


@pytest.fixture
def tree_in_memory(tmp_path: Path):
    """Create a CST tree from valid code and return (tree_id, root_dir, file_path)."""
    code = '"""Doc."""\n\nx = 1\n'
    path = tmp_path / "out.py"
    tree = create_tree_from_code(str(path), code)
    return tree.tree_id, tmp_path, "out.py"


def test_save_tree_to_file_creates_target_and_removes_tmp(
    tree_in_memory, db_mock
) -> None:
    """On success, target file exists with correct content and no .tmp left."""
    tree_id, root_dir, file_path = tree_in_memory
    target = root_dir / file_path
    path_tmp = Path(str(target) + ".tmp")
    assert not target.exists()
    assert not path_tmp.exists()

    result = save_tree_to_file(
        tree_id=tree_id,
        file_path=file_path,
        root_dir=root_dir,
        project_id=str(uuid.uuid4()),
        database=db_mock,
        validate=True,
        backup=False,
    )

    assert result.get("success") is True
    assert result.get("sync_result", {}).get("skipped_db") is True
    assert target.exists()
    logical_source, persisted_node_ids = strip_persisted_node_ids(
        target.read_text(encoding="utf-8")
    )
    assert logical_source.strip() == '"""Doc."""\n\nx = 1'
    assert not persisted_node_ids
    sc = sibling_tree_path(target.resolve())
    assert sc.is_file()
    payload = read_sidecar_payload(target)
    assert payload is not None
    assert verify_sidecar_against_source(logical_source, payload)
    assert not path_tmp.exists()


def test_save_tree_to_file_uses_tmp_path_convention(
    tree_in_memory, db_mock, tmp_path: Path
) -> None:
    """Save writes to target.tmp then replaces; no other temp name."""
    tree_id, root_dir, file_path = tree_in_memory
    target = root_dir / file_path
    path_tmp = Path(str(target) + ".tmp")

    save_tree_to_file(
        tree_id=tree_id,
        file_path=file_path,
        root_dir=root_dir,
        project_id=str(uuid.uuid4()),
        database=db_mock,
        validate=True,
        backup=False,
    )

    after_tmp = list(root_dir.glob("*.tmp"))
    assert len(after_tmp) == 0, "No .tmp file should remain after success"
    assert path_tmp.parent == target.parent
    assert path_tmp.name == target.name + ".tmp"


def test_save_tree_to_file_validation_failure_cleans_tmp(
    tmp_path: Path, db_mock
) -> None:
    """When validation fails (compile raises on .tmp), .tmp is removed in finally."""
    code = '"""Doc."""\n\nx = 1\n'
    path = tmp_path / "bad.py"
    tree = create_tree_from_code(str(path), code)
    target = tmp_path / "out.py"
    path_tmp = Path(str(target) + ".tmp")
    tree_id = tree.tree_id
    real_compile = builtins.compile

    def failing_compile(source, filename, *args, **kwargs):
        if ".tmp" in str(filename):
            raise SyntaxError("fake validation failure")
        return real_compile(source, filename, *args, **kwargs)

    with patch("builtins.compile", failing_compile):
        result = save_tree_to_file(
            tree_id=tree_id,
            file_path="out.py",
            root_dir=tmp_path,
            project_id=str(uuid.uuid4()),
            database=db_mock,
            validate=True,
            backup=False,
        )

    assert result.get("success") is False
    assert "syntax" in result.get("error", "").lower()
    assert not path_tmp.exists(), ".tmp must be cleaned on validation failure"


def test_save_tree_to_file_tree_not_found_raises(tmp_path: Path, db_mock) -> None:
    """When tree_id is unknown, ValueError is raised (no .tmp created)."""
    with pytest.raises(ValueError, match="Tree not found"):
        save_tree_to_file(
            tree_id="nonexistent-tree-id",
            file_path="out.py",
            root_dir=tmp_path,
            project_id=str(uuid.uuid4()),
            database=db_mock,
            validate=True,
            backup=False,
        )
    path_tmp = tmp_path / "out.py.tmp"
    assert not path_tmp.exists()


def test_save_tree_to_file_lock_released_after_save(tree_in_memory, db_mock) -> None:
    """After save, no .lock file is left (lock released)."""
    tree_id, root_dir, file_path = tree_in_memory
    target = root_dir / file_path
    lock_path = Path(str(target) + ".lock")

    save_tree_to_file(
        tree_id=tree_id,
        file_path=file_path,
        root_dir=root_dir,
        project_id=str(uuid.uuid4()),
        database=db_mock,
        validate=True,
        backup=False,
    )

    assert not lock_path.exists(), "Lock file must be removed after save"


def test_save_tree_to_file_overwrites_existing(tree_in_memory, db_mock) -> None:
    """Saving over an existing file replaces content; .tmp not left."""
    tree_id, root_dir, file_path = tree_in_memory
    target = root_dir / file_path
    target.write_text("old content\n", encoding="utf-8")
    path_tmp = Path(str(target) + ".tmp")

    result = save_tree_to_file(
        tree_id=tree_id,
        file_path=file_path,
        root_dir=root_dir,
        project_id=str(uuid.uuid4()),
        database=db_mock,
        validate=True,
        backup=False,
    )

    assert result.get("success") is True
    assert "old content" not in target.read_text(encoding="utf-8")
    assert not path_tmp.exists()


def test_save_tree_to_file_creates_parent_dir(tree_in_memory, db_mock) -> None:
    """Target parent directory is created if missing."""
    tree_id, root_dir, _ = tree_in_memory
    sub = root_dir / "sub" / "dir"
    file_path = sub / "out.py"
    file_path_str = str(file_path.relative_to(root_dir))

    result = save_tree_to_file(
        tree_id=tree_id,
        file_path=file_path_str,
        root_dir=root_dir,
        project_id=str(uuid.uuid4()),
        database=db_mock,
        validate=True,
        backup=False,
    )

    assert result.get("success") is True
    assert file_path.exists()
    assert file_path.parent.exists()
