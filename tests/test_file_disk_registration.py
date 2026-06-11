"""
Tests for file_disk_registration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_editor.core.file_disk_registration import (
    collect_file_disk_metadata,
    ensure_file_row_for_disk_path,
)

PATCH_TARGET = "ai_editor.core.upstream.code_analysis_client.get_code_analysis_client"


def _mock_ca_client(*, root: Path, files: list[dict] | None = None) -> MagicMock:
    client = MagicMock()
    client.get_project_root.return_value = root
    client.call.return_value = {"files": files or []}
    return client


def test_collect_file_disk_metadata_python_file(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text('"""doc"""\nx = 1\n', encoding="utf-8")
    lines, has_doc = collect_file_disk_metadata(target)
    assert lines == 3
    assert has_doc is True


def test_ensure_file_row_registers_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "src" / "new.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('hi')\n", encoding="utf-8")
    client = _mock_ca_client(root=tmp_path, files=[])
    with patch(PATCH_TARGET, return_value=client):
        row = ensure_file_row_for_disk_path(None, "project-1", target)
    assert row is not None
    assert row["id"] is None
    assert row["relative_path"] == "src/new.py"
    assert row["project_id"] == "project-1"
    assert row["lines"] == 2
    assert row["has_docstring"] is False
    client.call.assert_any_call("list_project_files", {"project_id": "project-1"})


def test_ensure_file_row_idempotent_and_marks_chunking(tmp_path: Path) -> None:
    target = tmp_path / "b.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = _mock_ca_client(
        root=tmp_path,
        files=[{"file_id": "ca-file-42", "relative_path": "b.py"}],
    )
    with patch(PATCH_TARGET, return_value=client):
        first = ensure_file_row_for_disk_path(
            None, "project-1", target, mark_needs_chunking=True
        )
        second = ensure_file_row_for_disk_path(
            None, "project-1", target, mark_needs_chunking=True
        )
    assert first is not None and second is not None
    assert first["id"] == "ca-file-42"
    assert first["id"] == second["id"]
    assert first["relative_path"] == "b.py"
    assert client.call.call_count == 2


def test_ensure_file_row_returns_none_for_missing_path(tmp_path: Path) -> None:
    client = _mock_ca_client(root=tmp_path, files=[])
    with patch(PATCH_TARGET, return_value=client):
        assert (
            ensure_file_row_for_disk_path(None, "project-1", tmp_path / "nope.py")
            is None
        )
