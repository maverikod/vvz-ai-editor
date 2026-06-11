"""
Regression: module-level insert + save must not explode on-disk line count.

Legacy node-id markers used one line per CST node (v1), so cst_save_tree could
report hundreds of file_lines for a small source change. v2 uses a compact
payload; LibCST visitors must use on_visit (not visit) so position lookup works.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid

import pytest

from ai_editor.core.cst_tree.models import (
    ROOT_NODE_ID_SENTINEL,
    TreeOperation,
    TreeOperationType,
)
from ai_editor.core.cst_tree.node_id_markers import (
    MARKERS_BEGIN,
    MARKERS_END,
    MARKERS_VERSION,
    MARKERS_VERSION_V2,
    MARKER_PREFIX,
    append_persisted_node_ids,
    strip_persisted_node_ids,
)
from ai_editor.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    remove_tree,
)
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_saver import save_tree_to_file
from unittest.mock import MagicMock


def _make_db_mock() -> MagicMock:
    db = MagicMock()
    db.select = MagicMock(return_value=[])
    created = MagicMock()
    created.id = 1
    db.create_file = MagicMock(return_value=created)
    db.update_file = MagicMock(return_value=created)
    db.begin_transaction = MagicMock(return_value="tid")
    db.commit_transaction = MagicMock()
    db.rollback_transaction = MagicMock()

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
    db.execute_batch = MagicMock(
        side_effect=lambda ops, **kw: [{"affected_rows": 1, "data": None} for _ in ops]
    )
    db.execute_logical_write_operation = MagicMock(
        return_value={
            "success": True,
            "data": {"batch_results": [], "transaction_id": "tid"},
        }
    )
    return db


def test_module_insert_does_not_multiply_source_lines(tmp_path) -> None:
    """Single __root__ insert adds at most a few logical lines."""
    src = '"Doc"\nx = 1\n'
    path = tmp_path / "mod.py"
    tree = create_tree_from_code(str(path), src)
    try:
        logical_before = len(tree.module.code.splitlines())
        modify_tree(
            tree.tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=["# sweep marker"],
                )
            ],
        )
        t2 = get_tree(tree.tree_id)
        assert t2 is not None
        logical_after = len(t2.module.code.splitlines())
        assert logical_after == logical_before + 1
    finally:
        remove_tree(tree.tree_id)


def test_v2_marker_block_fixed_small_line_overhead(tmp_path) -> None:
    """Many CST nodes: persisted file uses v2 compact block (not 1 line per node)."""
    lines = ["def f{}():\n    return {}".format(i, i) for i in range(80)]
    src = "\n".join(lines) + "\n"
    path = tmp_path / "many_funcs.py"
    tree = create_tree_from_code(str(path), src)
    try:
        logical_lines = len(tree.module.code.splitlines())
        n_nodes = len(tree.metadata_map)
        assert n_nodes > 80
        persisted = append_persisted_node_ids(
            tree.module.code, tree.metadata_map, tree.root_node_id
        )
        total_lines = len(persisted.splitlines())
        assert MARKERS_VERSION_V2 in persisted
        assert total_lines <= logical_lines + 12
        clean, mapping = strip_persisted_node_ids(persisted + "\n")
        assert clean.strip() == tree.module.code.strip()
        assert len(mapping) == n_nodes
    finally:
        remove_tree(tree.tree_id)


def test_cst_save_tree_physical_lines_near_logical(tmp_path) -> None:
    """After save, file line count stays close to logical (markers are compact)."""
    db = _make_db_mock()
    src = "a = 1\n" * 30
    path = tmp_path / "save_budget.py"
    tree = create_tree_from_code(str(path), src)
    try:
        result = save_tree_to_file(
            tree_id=tree.tree_id,
            file_path=str(path),
            root_dir=tmp_path,
            project_id=str(uuid.uuid4()),
            database=db,
            validate=True,
            backup=False,
        )
        assert result["success"] is True
        assert result.get("sync_result", {}).get("skipped_db") is True
        on_disk = path.read_text(encoding="utf-8")
        logical, legacy = strip_persisted_node_ids(on_disk)
        logical_n = len(logical.splitlines())
        physical_n = len(on_disk.splitlines())
        assert not legacy
        assert physical_n == logical_n
    finally:
        remove_tree(tree.tree_id)


def test_v1_marker_block_still_strips_and_maps() -> None:
    """On-disk files written with legacy v1 line-per-node markers still load."""
    uid = str(uuid.uuid4())
    block = (
        f"{MARKERS_BEGIN}\n{MARKERS_VERSION}\n"
        f"{MARKER_PREFIX}0 Module {uid}\n{MARKERS_END}\n"
    )
    logical = "x = 1\n"
    clean, ids = strip_persisted_node_ids(logical + "\n\n" + block)
    assert clean.strip() == logical.strip()
    assert ids.get("0") == uid
