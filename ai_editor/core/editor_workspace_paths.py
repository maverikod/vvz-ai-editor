"""Editor workspace path resolver (C-005, C-006, C-007, C-018).

Resolves Editor Session Directory and File Subtree paths only.
Edit Subdirectory (C-008) is NOT allocated here — see workspace_layout.allocate_edit_subdir.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_editor.core.exceptions import ValidationError
from ai_editor.core.storage_paths import _resolve_path, load_raw_config


def _normalize_file_path(file_path: str) -> str:
    """Normalize project-relative file_path to posix without leading ./"""
    return Path(file_path.replace("\\", "/")).as_posix().lstrip("./")


def resolve_workspace_root(*, config_path: Path | None = None) -> Path:
    """Load workspace root from config (C-018)."""
    cfg = (config_path or Path("config.json")).resolve()
    if not cfg.is_file():
        raise ValidationError(f"Config not found: {cfg}", field="config_path")
    raw = load_raw_config(cfg)
    config_dir = cfg.parent
    ai_editor_cfg = raw.get("ai_editor") or {}
    storage_cfg = (
        ai_editor_cfg.get("storage") if isinstance(ai_editor_cfg, dict) else {}
    )
    if not isinstance(storage_cfg, dict):
        storage_cfg = {}
    value = storage_cfg.get("workspace_root")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            "workspace_root is required in ai_editor.storage",
            field="ai_editor.storage.workspace_root",
        )
    return _resolve_path(config_dir, value.strip())


def _assert_under_root(root: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays under root."""
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError(
            "path escapes workspace_root",
            field="path",
            details={"path": str(resolved), "root": str(root)},
        ) from exc
    return resolved


@dataclass(frozen=True)
class FileWorkspaceLayout:
    """Resolved workspace paths for one file open (C-005, C-006, C-007 only)."""

    session_dir: Path
    file_subtree_dir: Path
    origin_path: Path


def session_directory(workspace_root: Path, ca_session_id: str) -> Path:
    """Return workspace_root/ca_session_id/ (C-005)."""
    root = workspace_root.resolve()
    sid = str(ca_session_id or "").strip()
    if not sid:
        raise ValidationError("ca_session_id is required", field="ca_session_id")
    return _assert_under_root(root, root / sid)


def file_subtree_directory(
    workspace_root: Path,
    ca_session_id: str,
    project_id: str,
    file_path: str,
) -> Path:
    """Return File Subtree directory for one open file (C-006)."""
    norm = _normalize_file_path(file_path)
    parent = Path(norm).parent
    session_dir = session_directory(workspace_root, ca_session_id)
    base = session_dir / "files" / str(project_id)
    if str(parent) not in ("", "."):
        base = base / parent
    return _assert_under_root(workspace_root.resolve(), base)


def file_workspace_layout(
    workspace_root: Path,
    ca_session_id: str,
    project_id: str,
    file_path: str,
) -> FileWorkspaceLayout:
    """Resolve session_dir, file_subtree_dir, origin_path; does not allocate Edit Subdirectory (C-008)."""
    norm = _normalize_file_path(file_path)
    session_dir = session_directory(workspace_root, ca_session_id)
    subtree = file_subtree_directory(
        workspace_root, ca_session_id, project_id, file_path
    )
    origin_path = _assert_under_root(
        workspace_root.resolve(), subtree / Path(norm).name
    )
    return FileWorkspaceLayout(
        session_dir=session_dir,
        file_subtree_dir=subtree,
        origin_path=origin_path,
    )


def ensure_session_directory(workspace_root: Path, ca_session_id: str) -> Path:
    """mkdir session_dir and return it."""
    path = session_directory(workspace_root, ca_session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_file_subtree(layout: FileWorkspaceLayout) -> FileWorkspaceLayout:
    """mkdir file_subtree_dir only; return layout."""
    layout.file_subtree_dir.mkdir(parents=True, exist_ok=True)
    return layout
