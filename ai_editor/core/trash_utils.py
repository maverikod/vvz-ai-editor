"""
Utilities for project trash (recycle bin): name sanitization and path building.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence


# Characters illegal or problematic in filenames (Windows + Unix)
_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]+')


def sanitize_project_name(name: str, project_id: str) -> str:
    """
    Sanitize project name for use in filesystem folder names.

    Replaces illegal characters by underscore, collapses multiple underscores,
    strips leading/trailing underscores and dots. If result is empty, returns
    fallback using first 8 chars of project_id.

    Args:
        name: Raw project name (e.g. from DB or root_path basename).
        project_id: Project UUID (used for fallback if name becomes empty).

    Returns:
        Sanitized string safe for folder name.
    """
    if not name or not isinstance(name, str):
        name = ""
    s = _ILLEGAL_CHARS.sub("_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_. ")
    if not s:
        s = f"project_{project_id[:8]}" if project_id else "project_unknown"
    return s


def build_trash_folder_name(
    project_name: str, project_id: str, deleted_at_utc: datetime
) -> str:
    """
    Build trash folder name: {sanitized_name}_{YYYY-MM-DDThh-mm-ss}Z.

    Args:
        project_name: Project name (will be sanitized).
        project_id: Project UUID (for fallback if name empty).
        deleted_at_utc: Deletion time in UTC.

    Returns:
        Folder name string, e.g. MyProject_2025-01-29T14-30-00Z.
    """
    sanitized = sanitize_project_name(project_name, project_id)
    # ISO-like with colons replaced by hyphen for FS compatibility
    ts = deleted_at_utc.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{sanitized}_{ts}"


def get_project_id_from_trash_folder(
    trash_dir: Path, trash_folder_name: str
) -> str | None:
    """
    Read project_id from projectid file inside a trashed project folder.

    Supports both JSON format ({"id": "<uuid>", "description": "..."}) and
    legacy plain UUID on a single line.

    Args:
        trash_dir: Trash directory path.
        trash_folder_name: Name of the trashed folder (direct child of trash_dir).

    Returns:
        Project UUID string or None if file missing/invalid.
    """
    path = trash_dir / trash_folder_name / "projectid"
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip() or None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("id"):
                return str(data["id"]).strip()
        except (json.JSONDecodeError, TypeError):
            pass
        return raw
    except OSError:
        return None


def is_probable_project_uuid(name: str) -> bool:
    """
    Return True if ``name`` is a canonical UUID string (file-trash roots use
    trash_dir/<project_id>/).
    """
    try:
        u = uuid.UUID(name)
    except (ValueError, TypeError, AttributeError):
        return False
    return str(u) == name


def resolve_trash_entry_project_id(trash_dir: Path, entry_name: str) -> Optional[str]:
    """
    Resolve a project_id for DB / FAISS cleanup before removing a direct child of
    ``trash_dir``.

    - Whole-project trash folders may contain ``projectid`` at the top level.
    - File-trash roots are ``trash_dir/<uuid>/`` where the directory name is the
      project_id.

    Returns:
        Project UUID string if deterministically resolvable, else None.
    """
    pid = get_project_id_from_trash_folder(trash_dir, entry_name)
    if pid:
        return pid
    if is_probable_project_uuid(entry_name):
        return entry_name
    return None


def collect_project_ids_for_trash_cleanup(trash_dir: Path) -> List[str]:
    """
    Collect unique project_ids for all directory entries under ``trash_dir``
    (whole-project trashed trees and per-project file-trash roots).
    """
    if not trash_dir.exists() or not trash_dir.is_dir():
        return []
    seen: set[str] = set()
    out: List[str] = []
    try:
        for child in trash_dir.iterdir():
            if not child.is_dir():
                continue
            pid = resolve_trash_entry_project_id(trash_dir, child.name)
            if pid and pid not in seen:
                seen.add(pid)
                out.append(pid)
    except OSError:
        return out
    return out


def merge_project_ids_for_clear_trash_db_phase(
    trash_dir: Path, soft_deleted_project_ids: Sequence[str]
) -> List[str]:
    """
    Build the ordered list of project_ids for the DB/FAISS phase of ``clear_trash``.

    Includes every project_id resolvable from on-disk trash (same as
    :func:`collect_project_ids_for_trash_cleanup`), then appends **DB-only orphans**:
    rows with ``projects.deleted = 1`` whose id is not already covered by a resolvable
    trash entry (soft-deleted in DB but nothing under ``trash_dir`` maps to that id).

    Order: disk-derived ids first (stable), then orphans — so resolvable trash keeps
    the existing DB-before-disk contract relative to ``ClearTrashCommand``.

    Args:
        trash_dir: Trash root (may be missing; treated as no on-disk entries).
        soft_deleted_project_ids: ``id`` values from ``projects`` with ``deleted = 1``.

    Returns:
        Deduplicated project_ids for ``_clear_project_data_impl`` / FAISS cleanup.
    """
    disk_ids = collect_project_ids_for_trash_cleanup(trash_dir)
    seen: set[str] = set(disk_ids)
    out: List[str] = list(disk_ids)
    for pid in soft_deleted_project_ids:
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def ensure_unique_trash_path(trash_dir: Path, base_name: str) -> Path:
    """
    Return a path under trash_dir that does not exist yet.

    If trash_dir / base_name exists, appends _1, _2, ... until unique.

    Args:
        trash_dir: Base trash directory.
        base_name: Desired folder name (e.g. from build_trash_folder_name).

    Returns:
        Path to a unique directory under trash_dir.
    """
    dest = trash_dir / base_name
    if not dest.exists():
        return dest
    suffix = 1
    while True:
        candidate = trash_dir / f"{base_name}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1
