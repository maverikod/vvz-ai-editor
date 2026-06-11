"""Unit tests for editor_workspace_paths (C-005, C-006, C-007, C-008, C-018).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.core.editor_workspace_paths import (
    FileWorkspaceLayout,
    ensure_session_directory,
    file_workspace_layout,
    resolve_workspace_root,
)
from ai_editor.core.exceptions import ValidationError


def test_file_workspace_layout_paths(tmp_path: Path) -> None:
    """Assert C-005 session_dir, C-006 file_subtree_dir, C-007 origin_path."""
    root = tmp_path / "ws"
    root.mkdir()
    layout = file_workspace_layout(
        root,
        ca_session_id="sess-1",
        project_id="p1",
        file_path="src/pkg/mod.py",
    )
    assert layout.session_dir.resolve() == (root / "sess-1").resolve()
    assert (
        layout.file_subtree_dir.resolve()
        == (root / "sess-1" / "files" / "p1" / "src" / "pkg").resolve()
    )
    assert (
        layout.origin_path.resolve() == (layout.file_subtree_dir / "mod.py").resolve()
    )
    assert layout.origin_path.name == "mod.py"
    assert layout.origin_path.parent == layout.file_subtree_dir


def test_file_workspace_layout_no_edit_subdir(tmp_path: Path) -> None:
    """Assert resolver does not expose Edit Subdirectory (C-008)."""
    root = tmp_path / "ws"
    root.mkdir()
    layout = file_workspace_layout(
        root,
        ca_session_id="sess-1",
        project_id="p1",
        file_path="mod.py",
    )
    assert isinstance(layout, FileWorkspaceLayout)
    assert not hasattr(layout, "edit_subdir")
    assert layout.file_subtree_dir != layout.origin_path
    assert layout.file_subtree_dir.is_dir() is False


def test_ensure_session_directory(tmp_path: Path) -> None:
    """ensure_session_directory creates Editor Session Directory (C-005)."""
    root = tmp_path / "ws"
    root.mkdir()
    path = ensure_session_directory(root, "sess-2")
    assert path.is_dir()
    assert path.resolve() == (root / "sess-2").resolve()


def test_resolve_workspace_root_ok(tmp_path: Path) -> None:
    """resolve_workspace_root reads ai_editor.storage.workspace_root (C-018)."""
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"ai_editor": {"storage": {"workspace_root": "data/ws"}}}),
        encoding="utf-8",
    )
    assert resolve_workspace_root(config_path=cfg) == (tmp_path / "data/ws").resolve()


def test_resolve_workspace_root_missing_key(tmp_path: Path) -> None:
    """Missing workspace_root raises ValidationError (C-018)."""
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"ai_editor": {"storage": {}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as exc_info:
        resolve_workspace_root(config_path=cfg)
    assert exc_info.value.field == "ai_editor.storage.workspace_root"
    assert "workspace_root" in str(exc_info.value).lower()
