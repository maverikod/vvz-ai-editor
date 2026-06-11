"""
Unified path normalization module.

Provides a single method for normalizing file paths with project information.
All path normalization should use this module for consistency.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .exceptions import ProjectNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class NormalizedPath:
    """
    Normalized file path with project information.

    Attributes:
        absolute_path: Absolute normalized path as string
        project_root: Path to project root directory
        project_id: Project ID (UUID4 string)
        relative_path: Relative path from project root
    """

    absolute_path: str
    project_root: Path
    project_id: str
    relative_path: str


def _normalize_path_simple_internal(path: str | Path) -> str:
    """
    Internal function for simple path normalization.

    Normalizes a path to absolute resolved string without project information.
    This is used internally and should not be called directly from outside this module.
    Use normalize_path_simple() for public API.

    Args:
        path: Path to normalize

    Returns:
        Normalized absolute path as string
    """
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = path_obj.expanduser().resolve()
    else:
        path_obj = path_obj.resolve()
    return str(path_obj)


def normalize_file_path(
    file_path: str | Path,
    watch_dirs: Optional[List[str | Path]] = None,
    project_root: Optional[Path] = None,
) -> NormalizedPath:
    """
    Normalize file path and determine project information.

    This is the unified method for path normalization. It:
    1. Normalizes the path to absolute
    2. Finds the project root containing the file
    3. Validates project_id from projectid file
    4. Returns normalized path with project information

    Args:
        file_path: File path to normalize (can be relative or absolute)
        watch_dirs: Optional list of watched directories for project discovery.
                   If not provided and project_root is None, will try to find
                   project from file path alone.
        project_root: Optional project root path. If provided, will use this
                     instead of discovering from watch_dirs.

    Returns:
        NormalizedPath with absolute_path, project_root, project_id, and relative_path

    Raises:
        MultipleProjectIdError: If multiple projectid files found in path
        ProjectNotFoundError: If project not found for the file path
        FileNotFoundError: If file path does not exist
    """
    # Normalize to absolute path
    absolute_path = _normalize_path_simple_internal(file_path)
    absolute_path_obj = Path(absolute_path)

    # Check if file exists
    if not absolute_path_obj.exists():
        raise FileNotFoundError(f"File not found: {absolute_path}")

    # If project_root is provided, use it directly
    if project_root is not None:
        project_root_path = Path(project_root).resolve()
        try:
            from .project_resolution import load_project_info

            project_info = load_project_info(project_root_path)
            # Verify file is within project root
            try:
                relative_path = absolute_path_obj.relative_to(project_root_path)
            except ValueError:
                raise ProjectNotFoundError(
                    message=f"File {absolute_path} is not within project root {project_root_path}",
                    project_id=project_info.project_id,
                )

            return NormalizedPath(
                absolute_path=absolute_path,
                project_root=project_root_path,
                project_id=project_info.project_id,
                relative_path=str(relative_path),
            )
        except Exception as e:
            logger.warning(f"Failed to load project info from {project_root_path}: {e}")
            raise ProjectNotFoundError(
                message=f"Failed to load project info from {project_root_path}: {e}",
            ) from e

    # Discover project from watch_dirs
    if watch_dirs is None:
        watch_dirs = []

    if not watch_dirs:
        logger.warning(
            f"No watch_dirs provided and no project_root, cannot determine project for {absolute_path}"
        )
        raise ProjectNotFoundError(
            message=f"Cannot determine project for file {absolute_path}: no watch_dirs or project_root provided",
        )

    # Find project root for this file
    from .project_resolution import find_project_root_for_path

    resolved_info = find_project_root_for_path(absolute_path, watch_dirs)
    if resolved_info is None:
        raise ProjectNotFoundError(
            message=f"Project not found for file {absolute_path}",
        )

    # Calculate relative path from project root
    try:
        relative_path = absolute_path_obj.relative_to(resolved_info.root_path)
    except ValueError:
        # This should not happen if find_project_root_for_path worked correctly
        logger.error(
            f"File {absolute_path} is not within project root {resolved_info.root_path}"
        )
        raise ProjectNotFoundError(
            message=f"File {absolute_path} is not within project root {resolved_info.root_path}",
            project_id=resolved_info.project_id,
        )

    return NormalizedPath(
        absolute_path=absolute_path,
        project_root=resolved_info.root_path,
        project_id=resolved_info.project_id,
        relative_path=str(relative_path),
    )


def file_lookup_paths_for_project(
    file_path: Union[str, Path],
    project_root: Union[str, Path],
) -> Tuple[List[str], List[str]]:
    """
    Keys for matching DB ``files.path`` / relative columns when resolving a user path.

    Returns:
        (absolute_path_keys, relative_path_keys) — use either set for lookups.
    """
    root = Path(project_root).resolve()
    p = Path(file_path)
    if p.is_absolute():
        resolved = p.resolve()
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            rel = Path(file_path)
    else:
        resolved = (root / p).resolve()
        rel = p
    abs_keys = [str(resolved)]
    rel_norm = str(rel).replace("\\", "/")
    rel_keys: List[str] = [rel_norm]
    alt = str(rel)
    if alt not in rel_keys:
        rel_keys.append(alt)
    return abs_keys, rel_keys


def normalize_path_simple(path: str | Path) -> str:
    """
    Simple path normalization without project information.

    This is a convenience function for cases where only path normalization
    is needed without project discovery. For full normalization with
    project information, use normalize_file_path().

    Args:
        path: Path to normalize

    Returns:
        Normalized absolute path as string
    """
    return _normalize_path_simple_internal(path)
