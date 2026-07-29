"""Regression tests for the canonical live pipeline helper."""

from __future__ import annotations

import argparse
import asyncio
import sys
import types
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts import verify_editor_ca_chain as pipeline


def test_available_checks_exposes_metadata_and_known_scenarios() -> None:
    """The unified ``pipeline`` CLI must expose stable check names."""
    checks = pipeline.available_checks()

    assert checks[0] == pipeline.METADATA_CHECK_NAME
    assert "open_queue_autopoll_84d93cca" in checks
    assert "styled_yaml_minimal_diff_b215fbd3" in checks


def test_resolve_requested_checks_rejects_unknown_name() -> None:
    """Unknown ``pipeline <check-name>`` arguments must fail loudly."""

    class Args:
        checks = ["does_not_exist"]

    with pytest.raises(pipeline.PipelineFailure) as exc_info:
        pipeline._resolve_requested_checks(Args())

    assert "Unknown pipeline checks requested" in str(exc_info.value)
    assert exc_info.value.evidence == {
        "unknown": ["does_not_exist"],
        "available": pipeline.available_checks(),
    }


def test_run_pipeline_honors_single_selected_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pipeline <check-name>`` must run only that named check."""
    seen: list[str] = []

    async def fake_run_scenario(
        name: str,
        _fn: object,
        _ca: object,
        _ed: object,
        _args: object,
        _watch_dir_id: str,
    ) -> dict[str, Any]:
        seen.append(name)
        return {"name": name, "status": "passed", "details": {}}

    async def fake_discover_watch_dir_id(_ca: object) -> dict[str, str]:
        return {"watch_dir_id": "watch-1", "source": "fake"}

    monkeypatch.setattr(
        pipeline, "_client", lambda *_args, **_kwargs: SimpleNamespace()
    )

    async def fake_assert_server_reachable(
        _server_name: str, _host: str, _port: int, *, timeout_seconds: float = 3.0
    ) -> None:
        del timeout_seconds
        return None

    monkeypatch.setattr(
        pipeline, "_assert_server_reachable", fake_assert_server_reachable
    )
    monkeypatch.setattr(pipeline, "_discover_watch_dir_id", fake_discover_watch_dir_id)
    monkeypatch.setattr(pipeline, "_run_scenario", fake_run_scenario)

    args = argparse.Namespace(
        checks=["open_queue_autopoll_84d93cca"],
        watch_dir_id="",
        ca_host="ca-host",
        ca_port=15010,
        editor_host="editor-host",
        editor_port=15000,
        mtls_dir=pipeline.REPO_ROOT,
        list=False,
    )

    result = asyncio.run(pipeline.run_pipeline(args))

    assert seen == ["open_queue_autopoll_84d93cca"]
    assert result["requested_checks"] == ["open_queue_autopoll_84d93cca"]
    assert result["summary"] == {"passed": 1, "failed": 0, "total": 1}
    assert result["watch_dir"] == {
        "id": "watch-1",
        "source": "fake",
        "required": True,
    }


def test_call_wraps_connect_error_with_endpoint_context() -> None:
    """Connect failures must surface as concise server/endpoint pipeline errors."""

    class FakeClient:
        async def execute_command(
            self, _command: str, _params: dict[str, Any]
        ) -> dict[str, Any]:
            raise httpx.ConnectError("All connection attempts failed")

    client = pipeline._annotate_client(
        FakeClient(),
        server_name="code-analysis-server",
        host="192.168.254.26",
        port=15010,
    )

    with pytest.raises(pipeline.PipelineFailure) as exc_info:
        asyncio.run(pipeline._call(client, "list_watch_dirs", {}))

    assert str(exc_info.value) == (
        "code-analysis-server unreachable at 192.168.254.26:15010 "
        "during list_watch_dirs"
    )
    assert exc_info.value.evidence == {
        "server": "code-analysis-server",
        "host": "192.168.254.26",
        "port": 15010,
        "command": "list_watch_dirs",
        "transport_error": "ConnectError: All connection attempts failed",
    }


def test_run_pipeline_preflights_required_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full runs must check editor and CA reachability before JSON-RPC calls."""

    seen: list[tuple[str, str, int]] = []

    async def fake_assert_server_reachable(
        server_name: str, host: str, port: int, *, timeout_seconds: float = 3.0
    ) -> None:
        del timeout_seconds
        seen.append((server_name, host, port))

    async def fake_run_scenario(
        name: str,
        _fn: object,
        _ca: object,
        _ed: object,
        _args: object,
        _watch_dir_id: str,
    ) -> dict[str, Any]:
        return {"name": name, "status": "passed", "details": {}}

    async def fake_discover_watch_dir_id(_ca: object) -> dict[str, str]:
        return {"watch_dir_id": "watch-1", "source": "fake"}

    monkeypatch.setattr(
        pipeline, "_client", lambda *_args, **_kwargs: SimpleNamespace()
    )
    monkeypatch.setattr(
        pipeline, "_assert_server_reachable", fake_assert_server_reachable
    )
    monkeypatch.setattr(pipeline, "_discover_watch_dir_id", fake_discover_watch_dir_id)
    monkeypatch.setattr(pipeline, "_run_scenario", fake_run_scenario)

    args = argparse.Namespace(
        checks=["open_queue_autopoll_84d93cca"],
        watch_dir_id="",
        ca_host="ca-host",
        ca_port=15010,
        editor_host="editor-host",
        editor_port=15000,
        mtls_dir=pipeline.REPO_ROOT,
        list=False,
    )

    result = asyncio.run(pipeline.run_pipeline(args))

    assert result["summary"] == {"passed": 1, "failed": 0, "total": 1}
    assert seen == [
        ("ai-editor-server", "editor-host", 15000),
        ("code-analysis-server", "ca-host", 15010),
    ]


def test_client_warns_and_skips_mtls_when_files_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing mTLS files must not crash pipeline bootstrap."""

    seen: dict[str, Any] = {}

    class FakeJsonRpcClient:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setitem(
        sys.modules, "mcp_proxy_adapter", types.ModuleType("mcp_proxy_adapter")
    )
    monkeypatch.setitem(
        sys.modules,
        "mcp_proxy_adapter.client",
        types.ModuleType("mcp_proxy_adapter.client"),
    )
    monkeypatch.setitem(
        sys.modules,
        "mcp_proxy_adapter.client.jsonrpc_client",
        types.ModuleType("mcp_proxy_adapter.client.jsonrpc_client"),
    )
    fake_module = types.ModuleType("mcp_proxy_adapter.client.jsonrpc_client.client")
    fake_module.JsonRpcClient = FakeJsonRpcClient
    monkeypatch.setitem(
        sys.modules, "mcp_proxy_adapter.client.jsonrpc_client.client", fake_module
    )

    with pytest.warns(
        RuntimeWarning, match="mTLS files missing; continuing without client"
    ):
        client = pipeline._client("127.0.0.1", 15000, tmp_path)

    assert isinstance(client, FakeJsonRpcClient)
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 15000
    assert seen["protocol"] == "https"
    assert "cert" not in seen
    assert "key" not in seen
    assert "ca" not in seen


def test_default_mtls_dir_prefers_renamed_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Local tooling must prefer the renamed ``mtls-certificates`` directory."""

    fake_root = tmp_path / "repo"
    renamed = fake_root / "mtls-certificates" / "mtls_certificates"
    legacy = fake_root / "mtls_certificates" / "mtls_certificates"
    legacy.mkdir(parents=True)
    renamed.mkdir(parents=True)
    monkeypatch.setattr(pipeline, "REPO_ROOT", fake_root)

    assert pipeline._default_mtls_dir() == renamed


def test_close_suppress_times_out_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup close must not stall the whole pipeline indefinitely."""

    async def fake_call(
        _client: object,
        _command: str,
        _params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"success": True}

    monkeypatch.setattr(pipeline, "_call", fake_call)
    monkeypatch.setattr(pipeline, "DEFAULT_CLOSE_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(
        pipeline._close_suppress(
            object(),
            "project-1",
            "session-1",
            "verify/file.txt",
        )
    )

    assert result == {"close_error": "TimeoutError(universal_file_close exceeded 0s)"}


class _FakeDownloadClient:
    """Stub JsonRpcClient exposing only the async ``download_file`` helper."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.downloads: list[str] = []

    async def download_file(self, transfer_id: str, dest_path: str) -> None:
        self.downloads.append(transfer_id)
        with open(dest_path, "wb") as handle:
            handle.write(self.payload)


def test_read_file_text_downloads_bytes_via_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readback uses path-based transfer download and preserves EOF newline.

    CAS 1.6.90 removed ``get_file_lines``; the helper must begin a
    ``transfer_download_begin`` with the project-root-resolved absolute
    ``source_path`` and return the exact downloaded bytes as text.
    """
    seen: dict[str, Any] = {}

    async def fake_call(
        _client: object,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen["command"] = command
        seen["params"] = params or {}
        return {"transfer_id": "t-1"}

    monkeypatch.setattr(pipeline, "_call", fake_call)
    monkeypatch.setattr(pipeline, "_PROJECT_ROOTS", {"project-1": "/srv/projects/demo"})
    client = _FakeDownloadClient(b"one\ntwo\n")

    text = asyncio.run(
        pipeline._read_file_text(
            client,
            "project-1",
            "verify/small.txt",
            end_line=5,
        )
    )

    assert text == "one\ntwo\n"
    assert seen["command"] == "transfer_download_begin"
    assert seen["params"] == {
        "source_path": "/srv/projects/demo/verify/small.txt",
        "filename": "small.txt",
        "compression": "identity",
    }
    assert client.downloads == ["t-1"]


def test_read_file_text_resolves_root_via_list_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown project root is resolved through ``list_projects`` once."""
    commands: list[str] = []

    async def fake_call(
        _client: object,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        commands.append(command)
        if command == "list_projects":
            return {
                "projects": [
                    {"project_id": "project-2", "root_path": "/srv/projects/other"}
                ]
            }
        return {"transfer_id": "t-2"}

    monkeypatch.setattr(pipeline, "_call", fake_call)
    monkeypatch.setattr(pipeline, "_PROJECT_ROOTS", {})
    client = _FakeDownloadClient(b"only")

    text = asyncio.run(
        pipeline._read_file_text(
            client,
            "project-2",
            "verify/one.txt",
        )
    )

    assert text == "only"
    assert commands == ["list_projects", "transfer_download_begin"]
    assert pipeline._PROJECT_ROOTS == {"project-2": "/srv/projects/other"}


def test_call_retries_once_on_transport_read_error() -> None:
    """A transient transport ReadError on commit-path calls must reconnect once."""

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0
            self.closed = 0

        async def execute_command(
            self, _command: str, _params: dict[str, Any]
        ) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                raise httpx.ReadError("boom")
            return {"success": True, "data": {"uploaded": True}}

        async def close(self) -> None:
            self.closed += 1

    client = FakeClient()

    result = asyncio.run(
        pipeline._call(
            client,
            "universal_file_write",
            {"write_mode": "commit"},
            retry_on_transport_error=True,
        )
    )

    assert result == {"uploaded": True}
    assert client.calls == 2
    assert client.closed == 1
