"""Tests for bundled config templates in the ai-editor package."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai_editor.config_templates import (
    CONTAINER_TEMPLATE_NAME,
    copy_bundled_template,
    load_bundled_template,
    read_bundled_template_text,
)


def test_bundled_container_template_loads() -> None:
    data = load_bundled_template()
    assert data["code_analysis_server"]["host"] == "${AI_EDITOR_CODE_ANALYSIS_HOST}"
    assert (
        data["ai_editor"]["storage"]["workspace_root"]
        == "/var/ai-editor/editor_workspaces"
    )


def test_repo_config_matches_bundled_template() -> None:
    repo_copy = Path("config/ai_editor_container.json")
    if not repo_copy.is_file():
        pytest.skip("config/ai_editor_container.json not in checkout")
    assert repo_copy.read_text(encoding="utf-8") == read_bundled_template_text()


def test_container_template_version_matches_package() -> None:
    from importlib.metadata import version

    pkg_ver = version("ai-editor")
    data = load_bundled_template()
    assert data["server_presentation"]["version"] == pkg_ver
    metadata = data["registration"]["metadata"]
    assert metadata["version"] == pkg_ver


def test_copy_bundled_template(tmp_path: Path) -> None:
    dest = copy_bundled_template(tmp_path)
    assert dest == tmp_path / CONTAINER_TEMPLATE_NAME
    assert json.loads(dest.read_text(encoding="utf-8")) == load_bundled_template()


def test_pyproject_declares_config_template_package_data() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"ai_editor.config_templates"' in text
    assert "*.json" in text
    template = Path("ai_editor/config_templates/ai_editor_container.json")
    assert template.is_file()


def test_pyproject_version_matches_template() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert match
    data = load_bundled_template()
    assert data["server_presentation"]["version"] == match.group(1)
