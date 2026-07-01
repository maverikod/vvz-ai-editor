"""Unit tests for code_analysis_file_transfer path/file_id resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_editor.core.upstream.code_analysis_file_transfer import (
    candidate_rel_paths_for_project,
    ensure_file_id_for_path,
    list_project_file_rows_for_path,
    read_project_file_bytes_via_lines,
    resolve_file_id_for_path,
)
from ai_editor.core.host_filesystem import HostFileOperationError


def _client_with_calls(mapping: dict[str, Any]) -> MagicMock:
    client = MagicMock()

    def _call(command: str, params: dict[str, Any] | None = None) -> Any:
        key = (command, tuple(sorted((params or {}).items())))
        if key in mapping:
            return mapping[key]
        cmd_only = mapping.get(command)
        if cmd_only is not None:
            return cmd_only
        raise AssertionError(f"unexpected call: {command} {params}")

    client.call.side_effect = _call
    return client


def test_resolve_file_id_uses_file_pattern_not_first_page() -> None:
    client = _client_with_calls(
        {
            (
                "list_project_files",
                (
                    ("file_pattern", "src/deep/module.py"),
                    ("project_id", "proj-1"),
                ),
            ): {
                "files": [
                    {
                        "relative_path": ".env",
                        "file_id": "wrong-id",
                    },
                    {
                        "relative_path": "src/deep/module.py",
                        "file_id": "good-id",
                    },
                ]
            }
        }
    )
    assert resolve_file_id_for_path(client, "proj-1", "src/deep/module.py") == "good-id"
    client.call.assert_called_once_with(
        "list_project_files",
        {"project_id": "proj-1", "file_pattern": "src/deep/module.py"},
    )


def test_resolve_file_id_missing_when_row_has_null_file_id() -> None:
    client = _client_with_calls(
        {
            (
                "list_project_files",
                (
                    ("file_pattern", "README.md"),
                    ("project_id", "proj-1"),
                ),
            ): {"files": [{"relative_path": "README.md", "file_id": None}]}
        }
    )
    with pytest.raises(RuntimeError, match="file not found in project index"):
        resolve_file_id_for_path(client, "proj-1", "README.md")


def test_read_project_file_bytes_via_lines_joins_and_trailing_newline() -> None:
    client = MagicMock()

    def _call(command: str, params: dict[str, Any] | None = None) -> Any:
        assert command == "get_file_lines"
        assert params is not None
        if params["start_line"] == 1 and params["end_line"] == 1:
            return {"lines": ["alpha"], "total_lines": 2}
        if params["start_line"] == 1 and params["end_line"] == 2:
            return {"lines": ["alpha", "beta"], "total_lines": 2}
        raise AssertionError(params)

    client.call.side_effect = _call
    assert (
        read_project_file_bytes_via_lines(client, "proj-1", "notes.txt")
        == b"alpha\nbeta\n"
    )


def test_ensure_file_id_registers_unindexed_disk_file() -> None:
    client = _client_with_calls({})

    def _call(command: str, params: dict[str, Any] | None = None) -> Any:
        if command == "list_project_files":
            return {
                "files": [{"relative_path": params["file_pattern"], "file_id": None}]
            }
        if command == "get_file_lines":
            return {"lines": ["hello"], "total_lines": 1}
        if command == "project_file_transfer_upload_save":
            return {"file_id": "new-file-id"}
        raise AssertionError(command)

    client.call.side_effect = _call
    client.run_in_isolated_loop.return_value = MagicMock(transfer_id="tr-1")

    fid = ensure_file_id_for_path(client, "proj-1", "notes.txt", session_id="sess-1")
    assert fid == "new-file-id"


def test_ensure_file_id_registers_disk_present_index_missing_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "gateway.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    client = MagicMock()
    client.get_project.return_value = {"id": "proj-1", "name": "lmrs"}
    client.get_project_root.return_value = tmp_path

    calls: list[tuple[str, dict[str, Any]]] = []

    def _call(command: str, params: dict[str, Any] | None = None) -> Any:
        payload = dict(params or {})
        calls.append((command, payload))
        if command == "list_project_files":
            return {"files": []}
        if command == "project_file_transfer_upload_save":
            assert payload["file_path"] == "gateway.py"
            return {"file_id": "fid-disk"}
        raise AssertionError(f"unexpected call: {command} {payload}")

    client.call.side_effect = _call
    client.run_in_isolated_loop.return_value = MagicMock(transfer_id="tr-disk")

    fid = ensure_file_id_for_path(
        client,
        "proj-1",
        "lmrs/gateway.py",
        session_id="sess-1",
    )

    assert fid == "fid-disk"
    assert any(
        command == "project_file_transfer_upload_save"
        and params["file_path"] == "gateway.py"
        for command, params in calls
    )


def test_ensure_file_id_disk_fallback_permission_error_is_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "gateway.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    client = MagicMock()
    client.get_project.return_value = {"id": "proj-1", "name": "lmrs"}
    client.get_project_root.return_value = tmp_path
    client.call.return_value = {"files": []}

    def _deny(self: Path) -> bytes:
        if self == target:
            raise PermissionError(13, "Permission denied", str(target))
        return b""

    monkeypatch.setattr(Path, "read_bytes", _deny)

    with pytest.raises(HostFileOperationError) as exc_info:
        ensure_file_id_for_path(
            client,
            "proj-1",
            "lmrs/gateway.py",
            session_id="sess-1",
        )

    assert exc_info.value.code == "HOST_FILE_OPERATION_ERROR"
    assert exc_info.value.details["reason"] == "permission_denied"
    assert exc_info.value.details["method_name"] == (
        "ensure_file_id_for_path:read_bytes"
    )


def test_candidate_rel_paths_strips_project_name_prefix() -> None:
    client = MagicMock()
    client.get_project.return_value = {"id": "proj-1", "name": "lmrs"}

    assert candidate_rel_paths_for_project(
        client,
        "proj-1",
        "lmrs/gateway.py",
    ) == ["lmrs/gateway.py", "gateway.py"]


def test_resolve_file_id_recovers_from_project_name_prefixed_path() -> None:
    client = _client_with_calls(
        {
            (
                "list_project_files",
                (
                    ("file_pattern", "lmrs/gateway.py"),
                    ("project_id", "proj-1"),
                ),
            ): {"files": []},
            (
                "list_project_files",
                (
                    ("file_pattern", "gateway.py"),
                    ("project_id", "proj-1"),
                ),
            ): {"files": [{"relative_path": "gateway.py", "file_id": "fid-gw"}]},
        }
    )
    client.get_project.return_value = {"id": "proj-1", "name": "lmrs"}

    assert resolve_file_id_for_path(client, "proj-1", "lmrs/gateway.py") == "fid-gw"


def test_ensure_file_id_registers_with_canonical_stripped_path() -> None:
    client = MagicMock()
    client.get_project.return_value = {"id": "proj-1", "name": "lmrs"}

    calls: list[tuple[str, dict[str, Any]]] = []

    def _call(command: str, params: dict[str, Any] | None = None) -> Any:
        payload = dict(params or {})
        calls.append((command, payload))
        if command == "list_project_files":
            if payload["file_pattern"] == "lmrs/gateway.py":
                return {"files": []}
            if payload["file_pattern"] == "gateway.py":
                return {"files": [{"relative_path": "gateway.py", "file_id": None}]}
        if command == "get_file_lines":
            assert payload["file_path"] == "gateway.py"
            return {"lines": ["print('ok')"], "total_lines": 1}
        if command == "project_file_transfer_upload_save":
            assert payload["file_path"] == "gateway.py"
            return {"file_id": "fid-gw"}
        raise AssertionError(f"unexpected call: {command} {payload}")

    client.call.side_effect = _call
    client.run_in_isolated_loop.return_value = MagicMock(transfer_id="tr-1")

    fid = ensure_file_id_for_path(
        client,
        "proj-1",
        "lmrs/gateway.py",
        session_id="sess-1",
    )

    assert fid == "fid-gw"
    assert any(
        command == "project_file_transfer_upload_save"
        and params["file_path"] == "gateway.py"
        for command, params in calls
    )


def test_list_project_file_rows_filters_exact_path() -> None:
    client = _client_with_calls(
        {
            (
                "list_project_files",
                (
                    ("file_pattern", "pkg/mod.py"),
                    ("project_id", "proj-1"),
                ),
            ): {
                "files": [
                    {"relative_path": "pkg/mod.py", "file_id": "a"},
                    {"relative_path": "pkg/mod.py.tree", "file_id": "b"},
                ]
            }
        }
    )
    rows = list_project_file_rows_for_path(client, "proj-1", "pkg/mod.py")
    assert len(rows) == 1
    assert rows[0]["file_id"] == "a"
