"""
Register on-disk project files via code-analysis-server (no local DB).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def collect_file_disk_metadata(path: Path) -> Tuple[int, bool]:
    lines = 0
    has_docstring = False
    if not path.exists() or not path.is_file():
        return lines, has_docstring
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.count("\n") + (1 if text else 0)
        stripped = text.lstrip()
        has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
    except Exception:
        logger.debug("Failed to read file for metadata: %s", path, exc_info=True)
    return lines, has_docstring


def ensure_file_row_for_disk_path(
    _database: Any,
    project_id: str,
    absolute_path: Path | str,
    *,
    last_modified: Optional[float] = None,
    mark_needs_chunking: bool = False,
    tree_checksum: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return file row metadata from CA index when available; else minimal stub."""
    _ = (last_modified, mark_needs_chunking, tree_checksum)
    path = Path(absolute_path)
    try:
        path = path.resolve()
    except OSError:
        path = Path(absolute_path)
    if not path.is_file():
        return None

    pid = str(project_id).strip()
    from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client

    client = get_code_analysis_client()
    try:
        root = client.get_project_root(pid)
        rel = path.relative_to(root).as_posix()
    except Exception as exc:
        logger.debug("Could not resolve relative path for %s: %s", path, exc)
        rel = path.name

    try:
        data = client.call("list_project_files", {"project_id": pid})
        files = data.get("files") if isinstance(data, dict) else None
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                item_rel = str(
                    item.get("relative_path") or item.get("path") or ""
                ).replace("\\", "/")
                if item_rel == rel or item_rel.endswith("/" + rel):
                    fid = str(item.get("file_id") or item.get("id") or "").strip()
                    if fid:
                        return {
                            "id": fid,
                            "project_id": pid,
                            "relative_path": rel,
                            "path": rel,
                            "deleted": False,
                        }
    except Exception as exc:
        logger.debug("list_project_files lookup failed: %s", exc)

    lines, has_docstring = collect_file_disk_metadata(path)
    return {
        "id": None,
        "project_id": pid,
        "relative_path": rel,
        "path": rel,
        "deleted": False,
        "lines": lines,
        "has_docstring": has_docstring,
    }
