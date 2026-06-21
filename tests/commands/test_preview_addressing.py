"""
Tests for preview addressing mode (identifier vs invalid-source pagination).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

import ai_editor.commands.universal_file_edit.session as session_mod
from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_preview.errors import (
    INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING,
    INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
)
from ai_editor.commands.universal_file_preview.preview_addressing import (
    check_preview_addressing,
    preview_source_is_parseable,
    uses_identifier_addressing,
    uses_line_fallback_addressing,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


def _db_for(tmp: Path, project_id: str = _PROJECT_UUID) -> MagicMock:
    m = MagicMock()
    row = {
        "id": project_id,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "test-project",
    }
    m.select.return_value = [row]
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _ensure_project_root(tmp: Path, project_id: str = _PROJECT_UUID) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(json.dumps({"id": project_id}) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_edit_session_index() -> None:
    session_mod._session_bundles.clear()
    session_mod._file_open_index.clear()


class TestPreviewAddressingHelpers:
    def test_identifier_addressing_node_ref(self) -> None:
        assert uses_identifier_addressing({"node_ref": "abc"}) is True

    def test_identifier_addressing_selector_slice(self) -> None:
        assert uses_identifier_addressing({"selector": "0:3"}) is True

    def test_line_fallback_only_offset(self) -> None:
        assert uses_line_fallback_addressing({"preview_offset": 100}) is True
        assert uses_line_fallback_addressing({"preview_offset": 0}) is False

    def test_check_invalid_json_with_node_ref(self) -> None:
        err = check_preview_addressing(
            parseable=False,
            params={"node_ref": "/a", "file_path": "x.json"},
            file_path="x.json",
        )
        assert err is not None
        assert err.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING

    def test_check_valid_with_preview_offset(self) -> None:
        err = check_preview_addressing(
            parseable=True,
            params={"preview_offset": 500, "file_path": "x.json"},
            file_path="x.json",
        )
        assert err is not None
        assert err.code == INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING


@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("broken.json", '{"a": '),
        ("broken.yaml", "key: [unclosed"),
        ("broken.py", "def f(\n"),
    ],
)
def test_invalid_structured_file_rejects_identifier_addressing(
    tmp_path: Path, rel: str, content: str
) -> None:
    _ensure_project_root(tmp_path)
    path = tmp_path / rel
    path.write_text(content, encoding="utf-8")
    assert preview_source_is_parseable(path) is False
    err = check_preview_addressing(
        parseable=False,
        params={"node_ref": "1", "file_path": rel},
        file_path=rel,
    )
    assert err is not None
    assert err.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING


@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("ok.json", '{"a": 1}\n'),
        ("ok.yaml", "key: value\n"),
        ("ok.py", "def f():\n    return 1\n"),
        ("ok.md", "# Title\n\nbody\n"),
        ("ok.txt", "line one\nline two\n"),
    ],
)
def test_parseable_file_rejects_line_pagination(
    tmp_path: Path, rel: str, content: str
) -> None:
    _ensure_project_root(tmp_path)
    path = tmp_path / rel
    path.write_text(content, encoding="utf-8")
    assert preview_source_is_parseable(path) is True
    err = check_preview_addressing(
        parseable=True,
        params={"preview_offset": 100, "max_chars": 500, "file_path": rel},
        file_path=rel,
    )
    assert err is not None
    assert err.code == INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING


def test_invalid_json_uuid_node_ref_requires_line_addressing(tmp_path: Path) -> None:
    """Sidecar-style UUID node_ref on invalid JSON must not drill structurally."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    broken = '{"key": "value", broken'
    (tmp_path / rel).write_text(broken, encoding="utf-8")
    assert preview_source_is_parseable(tmp_path / rel) is False
    err = check_preview_addressing(
        parseable=False,
        params={
            "node_ref": "3aeb19cf-4a9d-45d6-b3af-a0e4975bf874",
            "file_path": rel,
        },
        file_path=rel,
    )
    assert err is not None
    assert err.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING


@pytest.mark.asyncio
async def test_invalid_json_root_preview_via_command(tmp_path: Path) -> None:
    """Preview API accepts only project_id/file_path; invalid JSON uses line fallback."""
    rel = "broken.json"
    content = '{"x": ' + ("y" * 500)
    mock_client = MagicMock()
    mock_client.download_without_lock.return_value = content.encode("utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_db_for(tmp_path),
        ),
        patch(
            "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
            return_value=mock_client,
        ),
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data.get("focus", {}).get("is_invalid") is True
    assert data.get("mode_notice")
    assert "line-based" in str(data.get("mode_notice")).lower()
    assert "preview_total_chars" in data
    assert "preview_total_lines" in data
    assert data.get("preview_has_more") is False


@pytest.mark.asyncio
async def test_valid_json_root_preview_via_command(tmp_path: Path) -> None:
    """Root preview of parseable JSON returns structural blocks, not line pagination."""
    rel = "ok.json"
    content = '{"items": [1, 2, 3]}\n'
    mock_client = MagicMock()
    mock_client.download_without_lock.return_value = content.encode("utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_db_for(tmp_path),
        ),
        patch(
            "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
            return_value=mock_client,
        ),
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert "preview_chunk" not in data
    assert "blocks" in data
    assert "identifier" in str(data.get("mode_notice")).lower()


def test_preview_source_is_parseable_all_formats(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "b.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "c.txt").write_text("any text", encoding="utf-8")
    assert preview_source_is_parseable(tmp_path / "a.json") is True
    assert preview_source_is_parseable(tmp_path / "b.json") is False
    assert preview_source_is_parseable(tmp_path / "c.txt") is True
