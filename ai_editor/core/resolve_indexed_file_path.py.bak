"""
Resolve absolute filesystem paths for indexed files using DB fields only.

Layout (when watcher fills watch_dir_paths and project.name):
  watch_dir_paths.absolute_path / projects.name / files.relative_path

Fallbacks: projects.root_path / relative_path, then legacy files.path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def _normalize_relative_key(rel: str) -> str:
    s = (rel or "").strip().replace("\\", "/")
    while s.startswith("/"):
        s = s[1:]
    return s


def _first_existing_file(*candidates: Path) -> Optional[Path]:
    seen: set[str] = set()
    for raw in candidates:
        if raw is None:
            continue
        try:
            resolved = raw.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved
    return None


def resolve_indexed_file_path(file_row: Mapping[str, Any]) -> Optional[Path]:
    """
    Recompute absolute path from a file row (include joined project/watch columns).

    Tries, in order, the first path that exists and is a regular file:
    1. watch_absolute_path / project_name / relative_path
    2. project_root_path / relative_path
    3. files.path (stored absolute path at index time)

    Args:
        file_row: Dict-like row with id, path, optional relative_path, watch_absolute_path,
            project_name, project_root_path.

    Returns:
        Resolved Path, or None if no candidate exists on disk.
    """
    rel = _normalize_relative_key(str(file_row.get("relative_path") or ""))

    watch_abs = file_row.get("watch_absolute_path")
    proj_name = file_row.get("project_name")
    root_path = file_row.get("project_root_path")
    stored = file_row.get("path")

    candidates: list[Path] = []
    if watch_abs and proj_name and rel:
        candidates.append(Path(str(watch_abs)) / str(proj_name) / rel)
    if root_path and rel:
        candidates.append(Path(str(root_path)) / rel)
    if stored:
        candidates.append(Path(str(stored)))

    hit = _first_existing_file(*candidates)
    if hit is None:
        logger.debug(
            "resolve_indexed_file_path: no file on disk for file_id=%s "
            "(had watch+name+rel=%s root+rel=%s stored=%s)",
            file_row.get("id"),
            bool(watch_abs and proj_name and rel),
            bool(root_path and rel),
            bool(stored),
        )
    return hit
