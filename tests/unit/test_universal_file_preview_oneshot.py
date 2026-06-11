"""Unit tests for one-shot universal_file_preview (C-011, C-023)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


@pytest.fixture(autouse=True)
def _clear_bundle_index() -> None:
    import ai_editor.commands.universal_file_edit.session as session_mod

    session_mod._session_bundles.clear()
    session_mod._file_open_index.clear()


def test_oneshot_download_without_lock_no_bundle() -> None:
    """One-shot path calls download_without_lock when file not in bundle index."""
    from ai_editor.commands.universal_file_preview_runtime import run_preview_execute

    command = MagicMock()
    command._resolve_project_root = MagicMock(return_value=Path("/tmp/proj"))
    mock_client = MagicMock()
    mock_client.download_without_lock.return_value = b"print('hi')\n"
    with (
        patch(
            "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
            return_value=mock_client,
        ),
        patch(
            "ai_editor.commands.universal_file_preview_runtime._run_preview_on_abs_path",
            return_value=SuccessResult(data={"session_origin": "none", "focus": {}}),
        ) as mock_preview,
    ):
        result = run_preview_execute(
            command,
            project_id="p1",
            file_path="a.py",
        )
    assert isinstance(result, SuccessResult)
    mock_client.download_without_lock.assert_called_once_with(
        project_id="p1", file_path="a.py"
    )
    mock_client.session_open_file.assert_not_called()
    mock_preview.assert_called_once()


def test_open_file_rejects_oneshot() -> None:
    """Open bundle present → OPEN_FILE_USE_WORKSPACE_PREVIEW, no download."""
    import ai_editor.commands.universal_file_edit.session as session_mod
    from ai_editor.commands.universal_file_preview_runtime import run_preview_execute

    session_mod._file_open_index[("p1", "a.py")] = "ca-sid-1"
    command = MagicMock()
    mock_client = MagicMock()
    with patch(
        "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
        return_value=mock_client,
    ):
        result = run_preview_execute(
            command,
            project_id="p1",
            file_path="a.py",
        )
    assert isinstance(result, ErrorResult)
    assert result.code == "OPEN_FILE_USE_WORKSPACE_PREVIEW"
    mock_client.download_without_lock.assert_not_called()
