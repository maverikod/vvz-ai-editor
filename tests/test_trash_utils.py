"""
Unit tests for project trash utilities (sanitize, build_trash_folder_name, ensure_unique_trash_path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from datetime import datetime, timezone

from ai_editor.core.trash_utils import (
    build_trash_folder_name,
    ensure_unique_trash_path,
    sanitize_project_name,
)


class TestSanitizeProjectName:
    """Tests for sanitize_project_name."""

    def test_normal_name_unchanged(self):
        """Normal project name is unchanged."""
        assert sanitize_project_name("MyProject", "abc-123") == "MyProject"

    def test_illegal_chars_replaced(self):
        """Illegal filename characters are replaced by underscore."""
        assert (
            sanitize_project_name('a/b\\c:d*e?f"g<h>i|j', "id") == "a_b_c_d_e_f_g_h_i_j"
        )

    def test_multiple_underscores_collapsed(self):
        """Multiple consecutive underscores are collapsed."""
        assert sanitize_project_name("a___b", "id") == "a_b"

    def test_leading_trailing_stripped(self):
        """Leading and trailing underscores and dots are stripped."""
        assert sanitize_project_name("  _x.  ", "id") == "x"

    def test_empty_after_sanitize_uses_fallback(self):
        """Empty after sanitize uses project_id fallback."""
        assert sanitize_project_name("***???", "12345678-aaaa") == "project_12345678"

    def test_empty_name_uses_fallback(self):
        """Empty name uses project_id fallback."""
        assert sanitize_project_name("", "deadbeef") == "project_deadbeef"

    def test_none_like_uses_fallback(self):
        """Whitespace-only name uses fallback."""
        assert sanitize_project_name("   ", "abc") == "project_abc"


class TestBuildTrashFolderName:
    """Tests for build_trash_folder_name."""

    def test_format(self):
        """Folder name format is {sanitized}_{YYYY-MM-DDThh-mm-ss}Z."""
        dt = datetime(2025, 1, 29, 14, 30, 0, tzinfo=timezone.utc)
        name = build_trash_folder_name("MyProject", "uuid-here", dt)
        assert name == "MyProject_2025-01-29T14-30-00Z"

    def test_sanitized_name_used(self):
        """Project name is sanitized before use."""
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        name = build_trash_folder_name("my/project", "id", dt)
        assert name == "my_project_2025-01-01T00-00-00Z"


class TestEnsureUniqueTrashPath:
    """Tests for ensure_unique_trash_path."""

    def test_returns_base_path_when_not_exists(self, tmp_path):
        """Returns trash_dir / base_name when path does not exist."""
        result = ensure_unique_trash_path(tmp_path, "MyProject_2025-01-29T14-30-00Z")
        assert result == tmp_path / "MyProject_2025-01-29T14-30-00Z"
        assert not result.exists()

    def test_returns_unique_path_when_exists(self, tmp_path):
        """Appends _1 when base path already exists."""
        existing = tmp_path / "MyProject_2025-01-29T14-30-00Z"
        existing.mkdir()
        result = ensure_unique_trash_path(tmp_path, "MyProject_2025-01-29T14-30-00Z")
        assert result == tmp_path / "MyProject_2025-01-29T14-30-00Z_1"
        assert not result.exists()

    def test_increments_until_unique(self, tmp_path):
        """Appends _1, _2, ... until unique."""
        base = "Folder_2025-01-29T12-00-00Z"
        (tmp_path / base).mkdir(exist_ok=True)
        (tmp_path / f"{base}_1").mkdir(exist_ok=True)
        (tmp_path / f"{base}_2").mkdir(exist_ok=True)
        result = ensure_unique_trash_path(tmp_path, base)
        assert result == tmp_path / f"{base}_3"
        assert not result.exists()
