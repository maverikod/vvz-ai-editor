"""Regression test for project venv site-packages resolution (bug 7629cc48).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.code_quality.type_checker import (
    _resolve_project_site_packages,
)


def test_resolves_dot_venv_site_packages(tmp_path: Path) -> None:
    """A project .venv exposes its site-packages for MYPYPATH."""
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    assert _resolve_project_site_packages(tmp_path) == [site]


def test_no_venv_returns_empty(tmp_path: Path) -> None:
    """Projects without a venv change nothing."""
    assert _resolve_project_site_packages(tmp_path) == []
    assert _resolve_project_site_packages(None) == []
