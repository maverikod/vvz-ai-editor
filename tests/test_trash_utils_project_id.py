"""Trash project_id resolution for DB/FAISS cleanup."""

import uuid
from pathlib import Path

from ai_editor.core.trash_utils import (
    collect_project_ids_for_trash_cleanup,
    is_probable_project_uuid,
    merge_project_ids_for_clear_trash_db_phase,
    resolve_trash_entry_project_id,
)


def test_is_probable_project_uuid_accepts_canonical_uuid_string() -> None:
    u = str(uuid.uuid4())
    assert is_probable_project_uuid(u) is True
    assert is_probable_project_uuid("not-a-uuid") is False


def test_resolve_trash_prefers_projectid_file_over_folder_name(tmp_path: Path) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    folder = "MyProj_2025-01-01T00-00-00Z"
    inner = trash / folder
    inner.mkdir()
    file_pid = str(uuid.uuid4())
    (inner / "projectid").write_text(file_pid, encoding="utf-8")
    wrong_uuid = str(uuid.uuid4())
    assert resolve_trash_entry_project_id(trash, folder) == file_pid
    assert resolve_trash_entry_project_id(trash, wrong_uuid) == wrong_uuid


def test_resolve_trash_uuid_folder_without_projectid_uses_directory_name(
    tmp_path: Path,
) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    pid = str(uuid.uuid4())
    (trash / pid).mkdir()
    assert resolve_trash_entry_project_id(trash, pid) == pid


def test_collect_project_ids_dedupes(tmp_path: Path) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    pid = str(uuid.uuid4())
    (trash / pid).mkdir()
    (trash / "proj_ts").mkdir()
    (trash / "proj_ts" / "projectid").write_text(pid, encoding="utf-8")
    ids = collect_project_ids_for_trash_cleanup(trash)
    assert sorted(ids) == sorted([pid])


def test_merge_appends_db_only_orphans_after_disk_ids(tmp_path: Path) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    pid_disk = str(uuid.uuid4())
    pid_orphan = str(uuid.uuid4())
    (trash / pid_disk).mkdir()
    merged = merge_project_ids_for_clear_trash_db_phase(trash, [pid_orphan])
    assert merged == [pid_disk, pid_orphan]


def test_merge_dedupes_soft_deleted_already_on_disk(tmp_path: Path) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    pid = str(uuid.uuid4())
    (trash / pid).mkdir()
    merged = merge_project_ids_for_clear_trash_db_phase(trash, [pid])
    assert merged == [pid]


def test_merge_db_only_orphans_when_trash_dir_missing(tmp_path: Path) -> None:
    trash = tmp_path / "missing_trash"
    pid = str(uuid.uuid4())
    assert merge_project_ids_for_clear_trash_db_phase(trash, [pid]) == [pid]
