"""
Project resolution via on-disk ``projectid`` markers.

Thin editor: no database; project identity comes from JSON (or legacy UUID)
in ``<root_dir>/projectid``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from .exceptions import (
    InvalidProjectIdFormatError,
    MultipleProjectIdError,
    ProjectIdError,
)
from .project_discovery import find_project_root
from .uuid_validation import is_valid_uuid4

logger = logging.getLogger(__name__)

WatchDirInput = Union[str, Path]
RootDirInput = Union[str, Path]


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    """Information about project root."""

    root_path: Path
    project_id: str
    description: str


def normalize_root_dir(root_dir: RootDirInput) -> Path:
    """
    Normalize a project root directory to a resolved absolute ``Path``.

    Args:
        root_dir: Root directory path (string or Path).

    Returns:
        Resolved absolute ``Path``.

    Raises:
        FileNotFoundError: If the path does not exist.
        NotADirectoryError: If the path is not a directory.
    """
    path = Path(root_dir).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    return path


def _projectid_path(root_dir: Path) -> Path:
    return root_dir / "projectid"


def _read_projectid_raw(root_dir: Path) -> str:
    projectid_path = _projectid_path(root_dir)
    if not projectid_path.exists() or not projectid_path.is_file():
        raise ProjectIdError(
            message=f"Missing projectid file: {projectid_path}",
            details={"projectid_path": str(projectid_path)},
        )

    try:
        raw = projectid_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProjectIdError(
            message=f"Failed to read projectid file: {projectid_path}: {exc}",
            details={"projectid_path": str(projectid_path)},
        ) from exc

    if not raw:
        raise ProjectIdError(
            message=f"Empty projectid file: {projectid_path}",
            details={"projectid_path": str(projectid_path)},
        )
    return raw


def _parse_projectid_content(raw: str, projectid_path: Path) -> tuple[str, str]:
    project_id: str
    description: str

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        project_id = raw.strip()
        description = f"Project {project_id}"
    else:
        if not isinstance(data, dict):
            raise InvalidProjectIdFormatError(
                message="Invalid projectid JSON: expected object",
                projectid_path=str(projectid_path),
            )
        if "id" not in data:
            raise InvalidProjectIdFormatError(
                message="Missing required field 'id' in projectid file",
                projectid_path=str(projectid_path),
            )
        project_id = str(data["id"]).strip()
        description = str(data.get("description", "") or "")

    if not is_valid_uuid4(project_id):
        raise InvalidProjectIdFormatError(
            message=f"Invalid project_id format: {project_id}",
            projectid_path=str(projectid_path),
        )

    return project_id, description


def load_project_id(root_dir: RootDirInput) -> str:
    """
    Load ``project_id`` from ``<root_dir>/projectid`` and validate its format.

    Args:
        root_dir: Project root directory (contains ``projectid`` file).

    Returns:
        Project id as a string (UUID4).

    Raises:
        ProjectIdError: If file is missing or empty.
        InvalidProjectIdFormatError: If format is invalid or missing required fields.
    """
    return load_project_info(root_dir).project_id


def load_project_info(root_dir: RootDirInput) -> ProjectInfo:
    """
    Load full project information from ``<root_dir>/projectid`` file.

    Expected JSON format::

        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "description": "Human readable description of project"
        }

    Legacy plain UUID strings are also accepted for backward compatibility.

    Args:
        root_dir: Project root directory (contains ``projectid`` file).

    Returns:
        ProjectInfo with root_path, project_id, and description.

    Raises:
        ProjectIdError: If file is missing or empty.
        InvalidProjectIdFormatError: If format is invalid or missing required fields.
    """
    root_path = normalize_root_dir(root_dir)
    raw = _read_projectid_raw(root_path)
    project_id, description = _parse_projectid_content(raw, _projectid_path(root_path))
    return ProjectInfo(
        root_path=root_path,
        project_id=project_id,
        description=description,
    )


def _resolve_watch_dirs(watch_dirs: List[WatchDirInput]) -> List[Path]:
    return [Path(watch_dir).expanduser().resolve() for watch_dir in watch_dirs]


def _containing_watch_dir(file_path: Path, watch_paths: List[Path]) -> Optional[Path]:
    current = file_path.parent if file_path.is_file() else file_path
    current = current.resolve()
    for watch_dir in watch_paths:
        try:
            current.relative_to(watch_dir)
            return watch_dir
        except ValueError:
            continue
    return None


def _valid_project_roots_in_path(
    file_path: Path, watch_paths: List[Path]
) -> List[Path]:
    """
    Return project roots (watch_dir/<child>/ with projectid) on the path to watch_dir.
    """
    file_path = file_path.resolve()
    if not file_path.exists():
        return []

    containing_watch_dir = _containing_watch_dir(file_path, watch_paths)
    if containing_watch_dir is None:
        return []

    found: List[Path] = []
    search_path = (
        file_path.parent.resolve() if file_path.is_file() else file_path.resolve()
    )

    while True:
        try:
            relative_path = search_path.relative_to(containing_watch_dir)
        except ValueError:
            break

        if len(relative_path.parts) == 1:
            projectid_path = search_path / "projectid"
            if projectid_path.is_file():
                found.append(search_path)

        parent = search_path.parent
        if parent == search_path:
            break
        search_path = parent

    return found


def find_project_root_for_path(
    file_path: WatchDirInput,
    watch_dirs: List[WatchDirInput],
) -> Optional[ProjectInfo]:
    """
    Find project root for a file path and return full project information.

    Uses project discovery to find the nearest project root containing the file
    by walking up the directory tree and looking for projectid files.
    Checks for multiple valid project roots in the path and raises error if found.

    Args:
        file_path: Path to file
        watch_dirs: List of watched directories (absolute paths)

    Returns:
        ProjectInfo with root_path, project_id, and description, or None if not found

    Raises:
        MultipleProjectIdError: If multiple projectid-backed project roots found in path
        NestedProjectError: If nested projects detected
    """
    if file_path is None:
        return None

    path_str = str(file_path).strip()
    if not path_str:
        return None

    file_path_obj = Path(file_path).expanduser()
    if not file_path_obj.exists():
        logger.debug("File does not exist for project resolution: %s", file_path_obj)
        return None

    file_path_obj = file_path_obj.resolve()
    watch_paths = _resolve_watch_dirs(list(watch_dirs))

    valid_roots = _valid_project_roots_in_path(file_path_obj, watch_paths)
    if len(valid_roots) > 1:
        projectid_paths = [str(root / "projectid") for root in valid_roots]
        raise MultipleProjectIdError(
            message=(
                f"Multiple projectid files found in path for {file_path_obj}: "
                f"{projectid_paths}"
            ),
            projectid_paths=projectid_paths,
        )

    project_root = find_project_root(file_path_obj, watch_paths)
    if project_root is None:
        return None

    return ProjectInfo(
        root_path=project_root.root_path,
        project_id=project_root.project_id,
        description=project_root.description,
    )
