"""
Performance timings for cst_save_tree disk-only path (no DB sync).

Measures timings returned by save_tree_to_file; asserts DB-related timing keys
are zero and sync_result reports skipped_db.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.core.cst_tree.tree_builder import create_tree_from_code
from ai_editor.core.cst_tree.tree_saver import save_tree_to_file


def _make_db_mock() -> MagicMock:
    """Database mock passed to file_lock only (CST save is disk-only)."""
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
    return db


@pytest.fixture
def db_mock():
    """Database mock for save_tree_to_file (file_lock only)."""
    return _make_db_mock()


@pytest.fixture
def tree_small(tmp_path: Path):
    """Small file: docstring only."""
    code = '"""Doc."""\n\nx = 1\n'
    path = tmp_path / "small.py"
    tree = create_tree_from_code(str(path), code)
    return tree.tree_id, tmp_path, "small.py"


@pytest.fixture(autouse=True)
def _patch_file_edit_lock_acquire() -> Iterator[None]:
    """MagicMock DB does not return DML affected_rows; lock acquire would fail."""
    with patch(
        "ai_editor.core.database.file_edit_lock.acquire_file_edit_lock_with_retry",
        return_value=True,
    ):
        yield


@pytest.fixture
def tree_with_entities(tmp_path: Path):
    """File with classes/methods/functions/imports."""
    code = '''
"""Module with entities."""

import os
import sys

def foo():
    pass

class Bar:
    def meth(self):
        pass
'''
    path = tmp_path / "with_entities.py"
    tree = create_tree_from_code(str(path), code.strip())
    return tree.tree_id, tmp_path, "with_entities.py"


class TestCstSaveBatchPerformance:
    """Performance tests for cst_save_tree disk-only save path."""

    def test_save_returns_timings(self, tree_small, db_mock) -> None:
        """save_tree_to_file returns timings with zero DB sync keys."""
        tree_id, root_dir, file_path = tree_small
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
        timings = result.get("timings")
        assert timings is not None
        assert "db_file_record" in timings
        assert "sync_file_to_db" in timings
        assert timings["db_file_record"] == 0.0
        assert timings["sync_file_to_db"] == 0.0

    def test_disk_only_db_timings_are_zero(self, tree_small, db_mock) -> None:
        """Disk-only path: DB timing keys must be zero (no round-trips)."""
        tree_id, root_dir, file_path = tree_small
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
        assert result["timings"]["db_file_record"] == 0.0
        assert result["timings"]["sync_file_to_db"] == 0.0

    def test_save_multiple_runs_timings_stable(self, tree_small, db_mock) -> None:
        """Run save 3 times; disk-only DB timings stay zero."""
        tree_id, root_dir, file_path = tree_small
        project_id = str(uuid.uuid4())
        db_record_times: list[float] = []
        sync_times: list[float] = []
        for _ in range(3):
            result = save_tree_to_file(
                tree_id=tree_id,
                file_path=file_path,
                root_dir=root_dir,
                project_id=project_id,
                database=db_mock,
                validate=True,
                backup=False,
            )
            assert result.get("success") is True
            assert result.get("sync_result", {}).get("skipped_db") is True
            db_record_times.append(result["timings"]["db_file_record"])
            sync_times.append(result["timings"]["sync_file_to_db"])
        assert all(t == 0.0 for t in db_record_times)
        assert all(t == 0.0 for t in sync_times)
        print(
            "  disk-only timings: db_file_record and sync_file_to_db all 0.0 "
            f"over {len(db_record_times)} runs"
        )

    def test_save_with_entities_returns_timings(
        self, tree_with_entities, db_mock
    ) -> None:
        """Disk-only save with classes/methods/functions/imports."""
        tree_id, root_dir, file_path = tree_with_entities
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
        assert result.get("timings") is not None
        assert result["timings"]["db_file_record"] == 0.0
        assert result["timings"]["sync_file_to_db"] == 0.0
