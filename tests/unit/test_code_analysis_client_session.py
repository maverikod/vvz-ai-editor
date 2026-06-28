"""Unit tests for CodeAnalysisClient.validate_ca_session (C-002, C-014)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def test_validate_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))
    monkeypatch.setattr(client, "call", lambda cmd, params=None: {"locks": []})
    assert client.validate_ca_session("ok") == CaSessionStatus.VALID


def test_validate_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))

    def boom(cmd: str, params: dict[str, Any] | None = None) -> Any:
        raise RuntimeError("SESSION_NOT_FOUND")

    monkeypatch.setattr(client, "call", boom)
    assert client.validate_ca_session("missing") == CaSessionStatus.NOT_FOUND


def test_validate_empty() -> None:
    from ai_editor.core.upstream.code_analysis_client import (
        CaSessionStatus,
        CodeAnalysisClient,
    )

    client = CodeAnalysisClient(config_path=Path("config.json"))
    assert client.validate_ca_session("") == CaSessionStatus.INVALID


def test_upload_session_file_content_uses_file_path_not_file_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """upload_session_file_content must send file_path (not file_id) to CA.

    Regression: the commit path previously sent file_id to project_file_transfer_upload_save,
    but that command only accepts file_path. CA responds with -32600 'command is required'
    when file_id is used without file_path.
    """
    import ai_editor.core.upstream.code_analysis_client as _mod
    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient

    client = CodeAnalysisClient(config_path=Path("config.json"))

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_call(cmd: str, params: dict[str, Any] | None = None) -> Any:
        calls.append((cmd, dict(params or {})))
        if cmd == "project_file_transfer_upload_save":
            return {"file_id": "abc123"}
        return {}

    monkeypatch.setattr(client, "call", fake_call)
    monkeypatch.setattr(
        _mod,
        "upload_bytes_transfer_id",
        lambda _client, _content, filename: "tid-001",
    )

    result = client.upload_session_file_content(
        session_id="sess-1",
        project_id="proj-1",
        file_path="lmrs/contracts.py",
        content=b"# content",
    )

    save_calls = [p for cmd, p in calls if cmd == "project_file_transfer_upload_save"]
    assert save_calls, "project_file_transfer_upload_save was never called"
    params = save_calls[0]
    assert "file_path" in params, "file_path must be sent to project_file_transfer_upload_save"
    assert "file_id" not in params, "file_id must NOT be sent (causes -32600 from CA)"
    assert params["file_path"] == "lmrs/contracts.py"
    assert result == b"# content"


def test_upload_create_and_lock_locks_atomically_on_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create path must lock the new file atomically via the transfer save.

    The brand-new file (not yet in CA's DB) must never be registered without a
    lock: project_file_transfer_upload_save carries lock_mode="full" with
    unlock_after_write=False so the lock is acquired and retained as part of the
    transfer. session_open_file then re-affirms the same session lock.
    """
    import ai_editor.core.upstream.code_analysis_file_transfer as _xfer
    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient

    client = CodeAnalysisClient(config_path=Path("config.json"))

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_call(cmd: str, params: dict[str, Any] | None = None) -> Any:
        calls.append((cmd, dict(params or {})))
        if cmd == "project_file_transfer_upload_save":
            return {"file_id": "fid-1"}
        return {}

    monkeypatch.setattr(client, "call", fake_call)
    monkeypatch.setattr(
        _xfer,
        "upload_bytes_transfer_id",
        lambda _client, _content, filename: "tid-create",
    )

    client.upload_create_and_lock(
        session_id="sess-1",
        project_id="proj-1",
        file_path="lmrs/new.py",
        content=b"x = 1\n",
    )

    save_calls = [p for cmd, p in calls if cmd == "project_file_transfer_upload_save"]
    assert save_calls, "transfer save was never called on create"
    save = save_calls[0]
    assert save.get("lock_mode") == "full", "create transfer must lock atomically"
    assert save.get("unlock_after_write") is False, "lock must be retained after write"
    assert save.get("file_path") == "lmrs/new.py"
    # The session lock is also affirmed explicitly for open/close symmetry.
    assert any(cmd == "session_open_file" for cmd, _ in calls)


def test_upload_create_save_without_lock_mode_omits_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disk-only registration (no lock_mode) must not send lock_mode to CA.

    The non-create path registers an unindexed file purely to obtain its
    file_id; it acquires the lock separately via session_open_file, so the
    transfer save must omit lock_mode to preserve that behavior.
    """
    import ai_editor.core.upstream.code_analysis_file_transfer as _xfer
    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient

    client = CodeAnalysisClient(config_path=Path("config.json"))

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_call(cmd: str, params: dict[str, Any] | None = None) -> Any:
        calls.append((cmd, dict(params or {})))
        return {"file_id": "fid-2"}

    monkeypatch.setattr(client, "call", fake_call)
    monkeypatch.setattr(
        _xfer,
        "upload_bytes_transfer_id",
        lambda _client, _content, filename: "tid-reg",
    )

    _xfer.upload_create_save(
        client,
        session_id="sess-1",
        project_id="proj-1",
        file_path="lmrs/existing.py",
        content=b"y = 2\n",
    )

    save = [p for cmd, p in calls if cmd == "project_file_transfer_upload_save"][0]
    assert "lock_mode" not in save, "registration save must omit lock_mode"


def test_run_async_from_active_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient

    client = CodeAnalysisClient(config_path=Path("config.json"))
    seen: list[str] = []

    def fake_blocking(self: CodeAnalysisClient, command: str, params: dict[str, Any]) -> Any:
        seen.append(command)
        return {"locks": []}

    monkeypatch.setattr(CodeAnalysisClient, "_call_blocking", fake_blocking)

    async def runner() -> None:
        client.call("session_list_file_locks", {"session_id": "sid-1"})

    asyncio.run(runner())
    assert seen == ["session_list_file_locks"]
