"""Tests for the adapter-native queue handling and never-empty error messages.

Covers bug 84d93cca: universal_file_open OPEN_ERROR empty message / CAS timeout.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterator, Optional
from unittest.mock import MagicMock

import httpx
import pytest

from ai_editor.core.upstream.code_analysis_client import (
    CodeAnalysisClient,
    describe_exception,
)
from ai_editor.core.upstream.code_analysis_file_transfer import (
    _FILE_ID_CACHE,
    _cached_file_id,
    _set_cached_file_id,
    invalidate_cached_file_id,
    is_file_id_not_found_error,
    resolve_file_id_for_path,
)


@pytest.fixture(autouse=True)
def _clear_file_id_cache() -> Iterator[None]:
    """Reset the process-wide file_id cache before and after every test."""
    _FILE_ID_CACHE.clear()
    yield
    _FILE_ID_CACHE.clear()


def _make_client() -> CodeAnalysisClient:
    """Build a CodeAnalysisClient without touching real config/network."""
    client = CodeAnalysisClient.__new__(CodeAnalysisClient)
    client._config_path = None
    client._section = {"server_id": "code-analysis-server", "timeout": 300.0}
    client._rpc = None
    client._loop = None
    client._server_id = "code-analysis-server"
    return client


class TestDescribeException:
    """describe_exception must never return an empty string."""

    def test_empty_str_exception_uses_class_name(self) -> None:
        """httpx.ReadTimeout("") has an empty str(); the class name must survive."""
        exc = httpx.ReadTimeout("")
        assert str(exc) == ""
        result = describe_exception(exc)
        assert result
        assert "ReadTimeout" in result

    def test_empty_str_exception_with_context_included(self) -> None:
        """Context is folded in when str(exc) is empty."""
        exc = httpx.ReadTimeout("")
        result = describe_exception(exc, context="universal_file_open")
        assert "ReadTimeout" in result
        assert "universal_file_open" in result

    def test_non_empty_str_exception_preserved(self) -> None:
        """A normal exception's message is preserved verbatim, class-prefixed."""
        exc = RuntimeError("upstream exploded")
        result = describe_exception(exc, context="ignored-when-str-nonempty")
        assert "RuntimeError" in result
        assert "upstream exploded" in result
        assert "ignored-when-str-nonempty" not in result

    def test_never_returns_empty_string(self) -> None:
        """Guarantee: the returned string is always non-empty and non-blank."""
        for exc in (
            httpx.ReadTimeout(""),
            httpx.ConnectTimeout(""),
            Exception(),
            ValueError(),
        ):
            result = describe_exception(exc)
            assert isinstance(result, str)
            assert result.strip() != ""


class TestCallBlockingUnifiedAndFallback:
    """_call_blocking must prefer execute_command_unified, with a legacy fallback."""

    def test_unified_path_used_with_auto_poll(self) -> None:
        """When execute_command_unified succeeds, it serves the call directly."""
        client = _make_client()
        fake_rpc = MagicMock()

        async def fake_unified(**kwargs: Any) -> Dict[str, Any]:
            assert kwargs["auto_poll"] is True
            assert kwargs["command"] == "list_projects"
            return {"success": True, "data": {"projects": []}}

        fake_rpc.execute_command_unified = fake_unified
        fake_rpc.execute_command = MagicMock(
            side_effect=AssertionError("legacy execute_command must not be called")
        )

        import ai_editor.core.upstream.code_analysis_client as mod

        original_ctor = mod.JsonRpcClient
        try:
            mod.JsonRpcClient = MagicMock(return_value=fake_rpc)  # type: ignore[misc]
            outcome = client._call_blocking("list_projects", {})
        finally:
            mod.JsonRpcClient = original_ctor  # type: ignore[misc]

        assert outcome.result == {"projects": []}
        assert outcome.is_queued is False

    def test_fallback_to_legacy_when_unified_raises(self) -> None:
        """A unified-path failure falls back to legacy execute_command + polling."""
        client = _make_client()
        fake_rpc = MagicMock()

        async def fake_unified(**kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("unified path unavailable in this mTLS topology")

        legacy_calls = []

        async def fake_legacy(
            *, command: str, params: Dict[str, Any]
        ) -> Dict[str, Any]:
            legacy_calls.append(command)
            return {"success": True, "data": {"ok": True}}

        fake_rpc.execute_command_unified = fake_unified
        fake_rpc.execute_command = fake_legacy

        import ai_editor.core.upstream.code_analysis_client as mod

        original_ctor = mod.JsonRpcClient
        try:
            mod.JsonRpcClient = MagicMock(return_value=fake_rpc)  # type: ignore[misc]
            outcome = client._call_blocking("list_projects", {})
        finally:
            mod.JsonRpcClient = original_ctor  # type: ignore[misc]

        assert legacy_calls == ["list_projects"]
        assert outcome.result == {"ok": True}

    def test_fallback_when_unified_missing_attribute_error(self) -> None:
        """An adapter build without execute_command_unified falls back silently."""
        client = _make_client()

        class LegacyOnlyRpc:
            """Stand-in RPC object exposing only the legacy execute_command API."""

            def __init__(self) -> None:
                self.calls: list = []

            async def execute_command(
                self, *, command: str, params: Dict[str, Any]
            ) -> Dict[str, Any]:
                self.calls.append(command)
                return {"success": True, "data": {"ok": True}}

        fake_rpc = LegacyOnlyRpc()

        import ai_editor.core.upstream.code_analysis_client as mod

        original_ctor = mod.JsonRpcClient
        try:
            mod.JsonRpcClient = MagicMock(return_value=fake_rpc)  # type: ignore[misc]
            outcome = client._call_blocking("list_projects", {})
        finally:
            mod.JsonRpcClient = original_ctor  # type: ignore[misc]

        assert fake_rpc.calls == ["list_projects"]
        assert outcome.result == {"ok": True}

    def test_queued_response_still_unwrapped_via_legacy_polling(self) -> None:
        """A legacy queued response is still detected and polled to completion."""
        client = _make_client()
        fake_rpc = MagicMock()
        poll_calls = []

        async def fake_unified(**kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("force legacy fallback")

        async def fake_legacy(
            *, command: str, params: Dict[str, Any]
        ) -> Dict[str, Any]:
            if command == "queue_get_job_status":
                poll_calls.append(params["job_id"])
                return {
                    "success": True,
                    "status": "completed",
                    "data": {"result": {"success": True, "data": {"done": True}}},
                }
            return {
                "success": True,
                "mode": "queued",
                "job_id": "job-123",
                "status": "queued",
            }

        fake_rpc.execute_command_unified = fake_unified
        fake_rpc.execute_command = fake_legacy

        import ai_editor.core.upstream.code_analysis_client as mod

        original_ctor = mod.JsonRpcClient
        try:
            mod.JsonRpcClient = MagicMock(return_value=fake_rpc)  # type: ignore[misc]
            outcome = client._call_blocking("long_running_command", {})
        finally:
            mod.JsonRpcClient = original_ctor  # type: ignore[misc]

        assert outcome.is_queued is True
        assert outcome.queue_job_id == "job-123"
        assert poll_calls == ["job-123"]
        assert outcome.result == {"done": True}


class TestFileIdCache:
    """file_id cache must avoid repeat list_project_files round-trips."""

    def test_cache_hit_avoids_second_list_project_files_call(self) -> None:
        """A second resolve for the same path never calls list_project_files again."""
        client = MagicMock()
        client.call = MagicMock(
            return_value={
                "files": [
                    {
                        "file_id": "11111111-1111-1111-1111-111111111111",
                        "relative_path": "ai_editor/core/upstream/code_analysis_client.py",
                    }
                ]
            }
        )
        client.get_project.return_value = None

        pid = "proj-1"
        rel = "ai_editor/core/upstream/code_analysis_client.py"

        first = resolve_file_id_for_path(client, pid, rel)
        assert first == "11111111-1111-1111-1111-111111111111"
        assert client.call.call_count == 1

        second = resolve_file_id_for_path(client, pid, rel)
        assert second == first
        assert client.call.call_count == 1  # no additional round-trip

    def test_invalidate_triggers_re_resolve(self) -> None:
        """Invalidating a cached entry forces the next lookup back to CA."""
        client = MagicMock()
        client.call = MagicMock(
            return_value={
                "files": [
                    {
                        "file_id": "22222222-2222-2222-2222-222222222222",
                        "relative_path": "some/file.py",
                    }
                ]
            }
        )
        client.get_project.return_value = None

        pid = "proj-1"
        rel = "some/file.py"

        resolve_file_id_for_path(client, pid, rel)
        assert client.call.call_count == 1

        invalidate_cached_file_id(pid, rel)
        assert _cached_file_id(pid, rel) is None

        resolve_file_id_for_path(client, pid, rel)
        assert client.call.call_count == 2

    def test_set_and_get_cached_file_id_round_trip(self) -> None:
        """Directly exercise the cache helpers for a simple set/get round trip."""
        pid, rel, fid = "proj-x", "a/b.py", "33333333-3333-3333-3333-333333333333"
        assert _cached_file_id(pid, rel) is None
        _set_cached_file_id(pid, rel, fid)
        assert _cached_file_id(pid, rel) == fid

    def test_set_cached_file_id_ignores_empty_value(self) -> None:
        """Setting an empty file_id must not poison the cache with a falsy entry."""
        pid, rel = "proj-y", "c/d.py"
        _set_cached_file_id(pid, rel, "")
        assert _cached_file_id(pid, rel) is None


class TestIsFileIdNotFoundError:
    """is_file_id_not_found_error must recognize known upstream error shapes."""

    @pytest.mark.parametrize(
        "message",
        [
            "file not found in project index: 'a/b.py'",
            "FILE_ID NOT FOUND for project x",
            "Unknown file_id abc123",
            "No such file_id in table",
        ],
    )
    def test_recognizes_known_shapes(self, message: str) -> None:
        """Each known upstream error phrasing is recognized as file-id-not-found."""
        assert is_file_id_not_found_error(RuntimeError(message)) is True

    def test_rejects_unrelated_error(self) -> None:
        """An unrelated error message is not misclassified as file-id-not-found."""
        assert is_file_id_not_found_error(RuntimeError("connection refused")) is False


def test_file_id_cache_is_thread_safe_lock_present() -> None:
    """The cache module exposes a real threading.Lock guarding concurrent access."""
    import ai_editor.core.upstream.code_analysis_file_transfer as mod

    assert isinstance(mod._FILE_ID_CACHE_LOCK, type(threading.Lock()))
