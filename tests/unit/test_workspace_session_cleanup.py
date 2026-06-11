"""Unit tests for workspace_session_cleanup (C-025).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import create_session, get_session
from ai_editor.core.workspace_session_cleanup import cleanup_zombie_ca_session


def test_zombie_cleanup_removes_session_directory(tmp_path: Path) -> None:
    """Zombie Editor Session Directory is removed from workspace_root."""
    root = tmp_path / "workspace"
    sid = "zombie-1"
    (root / sid).mkdir(parents=True)
    assert cleanup_zombie_ca_session(sid, workspace_root=root) is True
    assert not (root / sid).exists()


def test_zombie_cleanup_purges_bundle(tmp_path: Path) -> None:
    """In-memory command-layer bundle is cleared for the CA session id."""
    src = tmp_path / "foo.py"
    src.write_text("x = 1\n", encoding="utf-8")
    descriptor = resolve_format_group(src)
    session = create_session(
        src.resolve(),
        descriptor,
        "foo.py",
        ca_session_id="test-ca-1",
    )
    sid = session.session_id
    assert get_session(sid).session_id == sid

    root = tmp_path / "workspace"
    (root / sid).mkdir(parents=True)

    assert cleanup_zombie_ca_session(sid, workspace_root=root) is True

    with pytest.raises(ValueError, match="SESSION_NOT_FOUND"):
        get_session(sid)
    assert not (root / sid).exists()


def test_cleanup_empty_session_id_returns_false(tmp_path: Path) -> None:
    """Empty ca_session_id is rejected without touching disk."""
    root = tmp_path / "workspace"
    root.mkdir()
    assert cleanup_zombie_ca_session("", workspace_root=root) is False
    assert cleanup_zombie_ca_session("   ", workspace_root=root) is False


def test_cleanup_path_escape_returns_false(tmp_path: Path) -> None:
    """Paths that escape workspace_root are rejected."""
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert cleanup_zombie_ca_session("..", workspace_root=root) is False
    assert outside.exists()
