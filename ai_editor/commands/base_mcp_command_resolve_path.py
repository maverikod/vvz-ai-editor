"""
Resolve file path from project_id and relative path for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

from ..core.exceptions import ValidationError
from ..core.upstream.code_analysis_client import get_code_analysis_client


def resolve_under_project_root(
    project_root: Path,
    relative_file_path: str,
    *,
    require_exists: bool = True,
    must_be_file: bool | None = None,
) -> Path:
    """Resolve ``relative_file_path`` under ``project_root`` with traversal checks."""
    raw = (relative_file_path or "").strip()
    if not raw:
        raise ValidationError(
            "file_path must be a non-empty relative path",
            field="file_path",
            details={},
        )
    rel = Path(raw)
    if rel.is_absolute():
        raise ValidationError(
            "Absolute file_path is not allowed; use a project-relative path.",
            field="file_path",
            details={"file_path": relative_file_path},
        )
    if any(part == ".." for part in rel.parts):
        raise ValidationError(
            "Path traversal (..) is not allowed in file_path.",
            field="file_path",
            details={"file_path": relative_file_path},
        )
    root = project_root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise ValidationError(
            "Resolved path escapes project root.",
            field="file_path",
            details={
                "file_path": relative_file_path,
                "resolved": str(candidate),
                "root": str(root),
            },
        ) from e
    if require_exists and not candidate.exists():
        raise ValidationError(
            f"Path does not exist: {candidate}",
            field="file_path",
            details={
                "relative_file_path": relative_file_path,
                "absolute_path": str(candidate),
            },
        )
    if require_exists and must_be_file is True and not candidate.is_file():
        raise ValidationError(
            f"Not a file: {candidate}",
            field="file_path",
            details={"absolute_path": str(candidate)},
        )
    if require_exists and must_be_file is False and not candidate.is_dir():
        raise ValidationError(
            f"Not a directory: {candidate}",
            field="file_path",
            details={"absolute_path": str(candidate)},
        )
    return candidate


def resolve_file_path_from_project(
    _database: object,
    project_id: str,
    relative_file_path: str,
    *,
    require_exists: bool = True,
) -> Path:
    """Resolve absolute file path from project_id and relative path via CA."""
    client = get_code_analysis_client()
    root = client.get_project_root(project_id)
    return resolve_under_project_root(
        root,
        relative_file_path,
        require_exists=require_exists,
        must_be_file=True if require_exists else None,
    )
