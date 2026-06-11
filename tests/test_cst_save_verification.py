"""
Tests for CST save verification: disk snapshot, replay, post-replace read-back, double save.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_editor.core.cst_tree.models import TreeOperation, TreeOperationType
from ai_editor.core.cst_tree.node_id_markers import append_persisted_node_ids
from ai_editor.core.cst_tree.tree_builder import (
    _attach_disk_snapshot,
    create_tree_from_code,
    get_tree,
    remove_tree,
)
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_save_verification import (
    CST_REPLAY_MISMATCH,
    FILE_CHANGED_SINCE_LOAD,
    SaveVerificationError,
    assert_disk_matches_tree_snapshot,
    assert_file_bytes_match,
    assert_replay_matches,
    disk_matches_tree_snapshot,
    replay_operations_produce_code,
)
from ai_editor.core.cst_tree.tree_saver import save_tree_to_file


def _make_db_mock() -> MagicMock:
    """Minimal database mock for save_tree_to_file (same pattern as test_cst_tree_saver)."""
    db = MagicMock()
    db.begin_transaction = MagicMock(return_value="tid")
    db.commit_transaction = MagicMock()
    db.rollback_transaction = MagicMock()
    db.select = MagicMock(return_value=[])
    created = MagicMock()
    created.id = 1
    db.create_file = MagicMock(return_value=created)
    updated = MagicMock()
    updated.id = 1
    db.update_file = MagicMock(return_value=updated)
    db.execute_batch = MagicMock(
        return_value=[
            {"affected_rows": 1, "lastrowid": i + 1, "data": None} for i in range(100)
        ]
    )
    db.execute_logical_write_operation = MagicMock(
        return_value={"success": True, "data": {"batch_results": []}}
    )

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
    return db


def _simple_statement_line_at_line(tree_id: str, line: int) -> str:
    tree = get_tree(tree_id)
    assert tree is not None
    for node_id, meta in tree.metadata_map.items():
        if meta.type == "SimpleStatementLine" and meta.start_line == line:
            return node_id
    pytest.fail(f"No SimpleStatementLine at line {line}")


def test_disk_matches_tree_snapshot_true_when_file_matches_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "m.py"
    text = "x = 1\n"
    path.write_text(text, encoding="utf-8")
    tree = create_tree_from_code(str(path), text)
    _attach_disk_snapshot(tree, path.read_text(encoding="utf-8"))
    assert disk_matches_tree_snapshot(path, tree) is True


def test_assert_disk_matches_raises_file_changed_since_load(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    text = "x = 1\n"
    path.write_text(text, encoding="utf-8")
    tree = create_tree_from_code(str(path), text)
    _attach_disk_snapshot(tree, path.read_text(encoding="utf-8"))
    path.write_text("x = 999\n", encoding="utf-8")
    with pytest.raises(SaveVerificationError) as excinfo:
        assert_disk_matches_tree_snapshot(path, tree)
    assert excinfo.value.code == FILE_CHANGED_SINCE_LOAD


def test_replay_operations_match_module_code_after_modify(tmp_path: Path) -> None:
    """Replay on source with markers uses same node IDs as the working tree (step 03)."""
    path = tmp_path / "m.py"
    logical = "x = 1\n"
    seed = create_tree_from_code(str(path), logical)
    marked_source = append_persisted_node_ids(
        logical.rstrip("\n"), seed.metadata_map, seed.root_node_id
    )
    remove_tree(seed.tree_id)
    path.write_text(marked_source, encoding="utf-8")

    tree = create_tree_from_code(str(path), marked_source)
    tree_id = tree.tree_id
    try:
        node_id = _simple_statement_line_at_line(tree_id, 1)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["x = 2"],
            )
        ]
        modify_tree(tree_id, ops)
        working = get_tree(tree_id)
        assert working is not None
        replayed = replay_operations_produce_code(marked_source, ops)
        assert replayed == working.module.code
        assert_replay_matches(
            original_source=marked_source,
            target_path=path,
            tree=working,
            tree_operations=ops,
        )
    finally:
        remove_tree(tree_id)


def test_assert_replay_matches_remaps_ids_across_fresh_parses(tmp_path: Path) -> None:
    """Replay builds a new parse of ``original_source``; op node_ids must remap from working tree."""
    path = tmp_path / "bare_replay.py"
    path.write_text("", encoding="utf-8")
    src = "def f():\n    return 0\n"
    tree = create_tree_from_code(str(path), src)
    tree_id = tree.tree_id
    fd_id: str | None = None
    for nid, meta in tree.metadata_map.items():
        if meta.type == "FunctionDef" and meta.name == "f":
            fd_id = nid
            break
    assert fd_id is not None
    ops = [
        TreeOperation(
            action=TreeOperationType.REPLACE,
            node_id=fd_id,
            code_lines=["def f():\n    return 99\n"],
        )
    ]
    try:
        modify_tree(tree_id, ops)
        working = get_tree(tree_id)
        assert working is not None
        assert "99" in working.module.code
        assert_replay_matches(
            original_source=src,
            target_path=path,
            tree=working,
            tree_operations=ops,
        )
    finally:
        remove_tree(tree_id)


def test_assert_replay_matches_cst_replay_mismatch(tmp_path: Path) -> None:
    """Working tree differs from replay when replay ops intentionally diverge."""
    path = tmp_path / "m.py"
    logical = "x = 1\n"
    seed = create_tree_from_code(str(path), logical)
    marked_source = append_persisted_node_ids(
        logical.rstrip("\n"), seed.metadata_map, seed.root_node_id
    )
    remove_tree(seed.tree_id)
    path.write_text(marked_source, encoding="utf-8")

    tree = create_tree_from_code(str(path), marked_source)
    tree_id = tree.tree_id
    try:
        node_id = _simple_statement_line_at_line(tree_id, 1)
        ops_apply = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["x = 2"],
            )
        ]
        ops_replay_wrong = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["x = 3"],
            )
        ]
        modify_tree(tree_id, ops_apply)
        working = get_tree(tree_id)
        assert working is not None
        with pytest.raises(SaveVerificationError) as excinfo:
            assert_replay_matches(
                original_source=marked_source,
                target_path=path,
                tree=working,
                tree_operations=ops_replay_wrong,
            )
        assert excinfo.value.code == CST_REPLAY_MISMATCH
    finally:
        remove_tree(tree_id)


def test_assert_file_bytes_match_after_os_replace(tmp_path: Path) -> None:
    """Post-replace read-back matches expected UTF-8 text (thin check around atomic replace)."""
    target = tmp_path / "out.py"
    tmp_file = Path(str(target) + ".tmp")
    expected = "# -*- coding: utf-8 -*-\nanswer = 42\n"
    tmp_file.write_text(expected, encoding="utf-8")
    os.replace(str(tmp_file), str(target))
    assert_file_bytes_match(target_path=target, expected=expected)


def test_save_twice_without_reload_second_save_succeeds(
    tmp_path: Path,
) -> None:
    """Snapshot refreshed after first save (tree_saver); second save does not regress FILE_CHANGED."""
    code = '"""Doc."""\n\nx = 1\n'
    rel = "out.py"
    tree = create_tree_from_code(str(tmp_path / rel), code)
    tree_id = tree.tree_id
    db_mock = _make_db_mock()
    pid = str(uuid.uuid4())
    try:
        r1 = save_tree_to_file(
            tree_id=tree_id,
            file_path=rel,
            root_dir=tmp_path,
            project_id=pid,
            database=db_mock,
            validate=True,
            backup=False,
        )
        assert r1.get("success") is True
        assert r1.get("sync_result", {}).get("skipped_db") is True
        r2 = save_tree_to_file(
            tree_id=tree_id,
            file_path=rel,
            root_dir=tmp_path,
            project_id=pid,
            database=db_mock,
            validate=True,
            backup=False,
        )
        assert r2.get("success") is True
        assert r2.get("sync_result", {}).get("skipped_db") is True
    finally:
        remove_tree(tree_id)
