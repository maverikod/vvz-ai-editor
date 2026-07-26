"""Unit tests for workspace_session_cleanup (C-025).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    get_session,
    lookup_ca_session_id,
)
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


def test_zombie_cleanup_purges_multi_file_bundle(tmp_path: Path) -> None:
    """Dead CA session cleanup must clear every file in a multi-file bundle."""
    src_a = tmp_path / "a.py"
    src_b = tmp_path / "b.py"
    src_a.write_text("x = 1\n", encoding="utf-8")
    src_b.write_text("y = 2\n", encoding="utf-8")
    descriptor_a = resolve_format_group(src_a)
    descriptor_b = resolve_format_group(src_b)

    create_session(
        src_a.resolve(),
        descriptor_a,
        "a.py",
        ca_session_id="test-ca-multi",
        project_id="proj-1",
    )
    create_session(
        src_b.resolve(),
        descriptor_b,
        "b.py",
        ca_session_id="test-ca-multi",
        project_id="proj-1",
    )

    root = tmp_path / "workspace"
    (root / "test-ca-multi").mkdir(parents=True)

    assert cleanup_zombie_ca_session("test-ca-multi", workspace_root=root) is True

    with pytest.raises(ValueError, match="SESSION_NOT_FOUND"):
        get_session("test-ca-multi", file_path="a.py")
    with pytest.raises(ValueError, match="SESSION_NOT_FOUND"):
        get_session("test-ca-multi", file_path="b.py")
    assert lookup_ca_session_id("proj-1", "a.py") is None
    assert lookup_ca_session_id("proj-1", "b.py") is None
    assert not (root / "test-ca-multi").exists()


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
