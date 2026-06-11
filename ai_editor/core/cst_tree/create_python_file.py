"""
Create a new Python file on disk using the same CST pipeline as ``cst_create_file``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..file_handlers.path_utils import (
    ensure_parent_directories,
    normalize_trailing_newline,
)
from .tree_builder import create_tree_from_code
from .tree_saver import save_tree_to_file


def create_new_python_file_from_source(
    *,
    absolute_path: Path,
    project_id: str,
    root_dir: Path,
    source_code: str,
    database: Any,
    create_parent_dirs: bool = True,
    backup: bool = False,
    commit_message: Optional[str] = None,
    validate: bool = True,
) -> Dict[str, Any]:
    """
    Create a new ``.py`` file (must not exist) via CST tree build and atomic save.

    Same steps as ``cst_create_file`` when ``source_code`` is provided:
    ``create_tree_from_code`` → ``save_tree_to_file`` (validation, DB sync, optional backup).

    Returns:
        Dict with ``success``, ``tree_id``, ``save_result``, etc.; ``error_code`` on failure.
    """
    target = absolute_path.resolve()
    root_dir = root_dir.resolve()

    if target.exists():
        return {
            "success": False,
            "error": f"File already exists: {target}",
            "error_code": "FILE_EXISTS",
            "file_path": str(target),
        }

    parent_err = ensure_parent_directories(
        target, create_parent_dirs=create_parent_dirs
    )
    if parent_err:
        return {
            "success": False,
            "error": parent_err,
            "error_code": "PARENT_DIR_MISSING",
            "file_path": str(target),
        }

    final_source = normalize_trailing_newline(source_code)
    if not final_source.strip():
        return {
            "success": False,
            "error": "source_code must not be empty",
            "error_code": "VALIDATION_ERROR",
            "file_path": str(target),
        }

    try:
        tree = create_tree_from_code(
            file_path=str(target),
            source_code=final_source,
            register_in_memory=True,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "error_code": "CST_CREATE_ERROR",
            "file_path": str(target),
        }

    save_result = save_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(target),
        root_dir=root_dir,
        project_id=project_id,
        database=database,
        validate=validate,
        backup=backup,
        commit_message=commit_message,
    )
    if not save_result.get("success"):
        return {
            "success": False,
            "error": save_result.get("error", "Failed to save tree"),
            "error_code": save_result.get("error_code", "CST_SAVE_ERROR"),
            "file_path": str(target),
            "save_result": save_result,
        }

    out: Dict[str, Any] = {
        "success": True,
        "tree_id": tree.tree_id,
        "file_path": str(target),
        "save_result": save_result,
        "created": True,
    }
    if target.exists():
        out["file_size_bytes"] = target.stat().st_size
        out["file_lines"] = len(target.read_text(encoding="utf-8").splitlines())
    return out
