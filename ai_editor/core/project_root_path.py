"""
Minimal project root resolution via code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def resolve_projects_root_path_row_to_absolute_str(
    *,
    project_id: str,
    root_path_stored: str,
    watch_dir_id: Optional[str] = None,
    project_name: Optional[str] = None,
    database: Any = None,
    require_exists: bool = True,
) -> str:
    from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client

    _ = (root_path_stored, watch_dir_id, project_name, database, require_exists)
    return str(get_code_analysis_client().get_project_root(project_id))


def resolve_project_root_absolute_str(
    *,
    project_id: str,
    root_path_stored: str,
    watch_dir_id: Optional[str] = None,
    project_name: Optional[str] = None,
    database: Any = None,
    require_exists: bool = True,
) -> str:
    return resolve_projects_root_path_row_to_absolute_str(
        project_id=project_id,
        root_path_stored=root_path_stored,
        watch_dir_id=watch_dir_id,
        project_name=project_name,
        database=database,
        require_exists=require_exists,
    )
