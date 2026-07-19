"""MCP queue regression coverage for lifecycle and diagnostics semantics."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    init_global_queue_manager,
    shutdown_global_queue_manager,
)

import ai_editor.hooks  # noqa: F401


def test_queued_upstream_response_preserves_job_and_final_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deferred CAS response resolves to one result with its proof intact."""
    import ai_editor.core.upstream.code_analysis_client as client_module
    from ai_editor.core.upstream.code_analysis_client import (
        CodeAnalysisClient,
        EditOutcome,
    )

    job_id = "cas-queued-job-001"
    terminal_response = {
        "success": True,
        "data": {
            "job_id": job_id,
            "status": "completed",
            "result": {
                "success": True,
                "kind": "success",
                "edited_files": ["src/example.py"],
                "evidence": {"response_id": "cas-final-response-001"},
            },
        },
    }
    responses = iter(
        [
            {
                "success": True,
                "mode": "queued",
                "data": {"job_id": job_id},
            },
            {
                "success": True,
                "data": {"job_id": job_id, "status": "running"},
            },
            terminal_response,
        ]
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeRpc:
        def __init__(self, **_: Any) -> None:
            pass

        async def execute_command(
            self, *, command: str, params: dict[str, Any]
        ) -> dict[str, Any]:
            calls.append((command, dict(params)))
            return next(responses)

    monkeypatch.setattr(client_module, "JsonRpcClient", FakeRpc)
    monkeypatch.setattr(client_module, "_build_jsonrpc_kwargs", lambda _: {})
    monkeypatch.setattr(client_module, "_QUEUE_POLL_INTERVAL_SECONDS", 0)

    outcome = CodeAnalysisClient(config_path=Path("config.json")).call_with_identity(
        "project_file_edit",
        {"project_id": "project-001", "file_path": "src/example.py"},
    )

    assert calls == [
        (
            "project_file_edit",
            {"project_id": "project-001", "file_path": "src/example.py"},
        ),
        ("queue_get_job_status", {"job_id": job_id}),
        ("queue_get_job_status", {"job_id": job_id}),
    ]
    assert outcome.is_queued is True
    assert outcome.queue_job_id == job_id
    assert outcome.queue_status == "completed"
    assert outcome.outcome is EditOutcome.SUCCESS
    assert outcome.result == terminal_response["data"]["result"]
    assert outcome.response is terminal_response
    assert outcome.response["data"]["job_id"] == outcome.queue_job_id
    assert outcome.response["data"]["result"]["evidence"] == {
        "response_id": "cas-final-response-001"
    }


async def _run_command(command_name: str, **params: Any) -> Dict[str, Any]:
    cmd_cls = registry.get_command(command_name)
    result_obj = await cmd_cls.run(**params)
    return result_obj.to_dict()


def _job_id(prefix: str) -> str:
    return f"qa_queuefix_{int(time.time() * 1000)}_{prefix}"


def _extract_queue_job_id(response: Dict[str, Any]) -> Optional[str]:
    for key in ("job_id", "queue_job_id"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return value
    data = response.get("data")
    if isinstance(data, dict):
        for key in ("job_id", "queue_job_id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    result = response.get("result")
    if isinstance(result, dict):
        for key in ("job_id", "queue_job_id"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    return None


async def _poll_terminal_status(job_id: str, timeout: float = 40.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        status_res = await _run_command("queue_get_job_status", job_id=job_id)
        assert status_res.get("success") is True
        last = status_res["data"]
        if last.get("status") in {"completed", "failed", "stopped", "deleted"}:
            return last
        await asyncio.sleep(0.2)
    return last


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _queue_manager_lifecycle():
    hooks.execute_custom_commands_hooks(registry)
    await shutdown_global_queue_manager()
    await init_global_queue_manager(
        in_memory=True,
        max_concurrent_jobs=2,
        completed_job_retention_seconds=3600,
    )
    try:
        yield
    finally:
        await shutdown_global_queue_manager()


@pytest.mark.asyncio
async def test_health_reports_queue_dependency_versions() -> None:
    health = await _run_command("health")
    assert health.get("success") is True
    deps = health["data"]["components"]["queue_dependencies"]
    assert "versions" in deps
    assert "minimum_required" in deps
    assert "compatibility" in deps
    assert "ai_editor_server" in deps["versions"]
    assert "mcp_proxy_adapter" in deps["versions"]
    assert "queuemgr" in deps["versions"]


@pytest.mark.asyncio
async def test_command_execution_health_completed_diagnostics() -> None:
    job_id = _job_id("health")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={"command": "health", "params": {}},
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert final.get("status") == "completed"
    assert final.get("job_success") is True
    assert final.get("command_execution") is True
    assert final.get("command_name") == "health"
    assert final.get("command_success") is True
    assert final.get("inner_success") is True
    assert final.get("completed_with_error") is False


@pytest.mark.asyncio
async def test_command_execution_inner_failure_retained_and_not_successful() -> None:
    job_id = _job_id("health_invalid")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={
            "command": "health",
            "params": {"invalid_param": True},
        },
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert final.get("status") in {"failed", "completed"}
    assert final.get("job_success") is False
    assert final.get("command_success") is False
    assert final.get("inner_success") is False

    listed = await _run_command(
        "queue_list_jobs", status_filter=final["status"], limit=200
    )
    assert listed.get("success") is True
    assert any(j.get("job_id") == job_id for j in listed["data"]["jobs"])

    logs = await _run_command("queue_get_job_logs", job_id=job_id)
    assert logs.get("success") is True


@pytest.mark.asyncio
async def test_deleted_retention_status_list_logs() -> None:
    job_id = _job_id("deleted_retention")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={"command": "health", "params": {}},
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True
    final = await _poll_terminal_status(job_id)
    assert final.get("status") == "completed"

    deleted = await _run_command("queue_delete_job", job_id=job_id)
    assert deleted.get("success") is True

    after_delete = await _poll_terminal_status(job_id)
    assert after_delete.get("status") == "deleted"

    deleted_list = await _run_command(
        "queue_list_jobs", status_filter="deleted", limit=200
    )
    assert deleted_list.get("success") is True
    assert any(j.get("job_id") == job_id for j in deleted_list["data"]["jobs"])

    logs = await _run_command("queue_get_job_logs", job_id=job_id)
    assert logs.get("success") is True


@pytest.mark.xfail(
    reason=(
        "Upstream queuemgr/mcp-proxy-adapter stop semantics may still keep a "
        "stopped marker while payload/logs look naturally completed."
    ),
    strict=False,
)
@pytest.mark.asyncio
async def test_qa_sleep_stop_interrupts_not_natural_completion() -> None:
    requested_seconds = 60.0
    queued = await _run_command(
        "qa_sleep",
        use_queue=True,
        seconds=requested_seconds,
        tick_seconds=0.5,
    )
    assert queued.get("success") is True
    job_id = _extract_queue_job_id(queued)
    assert job_id, f"Missing queued job id in response: {queued}"

    saw_running = False
    for _ in range(50):
        status_res = await _run_command("queue_get_job_status", job_id=job_id)
        assert status_res.get("success") is True
        if status_res["data"].get("status") == "running":
            saw_running = True
            break
        await asyncio.sleep(0.2)
    assert saw_running is True

    stopped = await _run_command("queue_stop_job", job_id=job_id)
    assert stopped.get("success") is True
    stop_actual = ((stopped.get("data") or {}).get("actual_status")) or stopped.get(
        "actual_status"
    )
    if stop_actual is not None:
        assert stop_actual == "stopped"

    final = await _poll_terminal_status(job_id, timeout=80.0)
    assert final.get("status") == "stopped"
    assert final.get("job_success") is False
    assert final.get("command_success") in (False, None)
    assert final.get("inner_success") in (False, None)

    result_payload = final.get("result") or {}
    inner_payload = (
        result_payload.get("result") if isinstance(result_payload, dict) else {}
    )
    if not isinstance(inner_payload, dict):
        inner_payload = {}
    if inner_payload:
        assert inner_payload.get("success") is not True
        slept_seconds = inner_payload.get("slept_seconds")
        if isinstance(slept_seconds, (int, float)):
            assert float(slept_seconds) < requested_seconds
        status_hint = str(
            inner_payload.get("status")
            or inner_payload.get("reason")
            or inner_payload.get("message")
            or ""
        ).lower()
        assert (
            ("interrupt" in status_hint)
            or ("stop" in status_hint)
            or ("cancel" in status_hint)
        )

    logs = await _run_command("queue_get_job_logs", job_id=job_id)
    assert logs.get("success") is True
    logs_data = logs.get("data") or {}
    combined_logs = "\n".join(
        str(item)
        for item in (
            (logs_data.get("stdout") or [])
            + (logs_data.get("stderr") or [])
            + (logs_data.get("logs") or [])
        )
    ).lower()
    assert "elapsed=60.0s" not in combined_logs
    assert "slept_seconds" not in combined_logs

    stopped_list = await _run_command(
        "queue_list_jobs", status_filter="stopped", limit=200
    )
    assert stopped_list.get("success") is True
    assert any(j.get("job_id") == job_id for j in stopped_list["data"]["jobs"])
