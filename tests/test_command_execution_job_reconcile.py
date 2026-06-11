"""Queue job status must follow MCP command success (ErrorResult → job failed)."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob

from ai_editor.core.command_execution_job_patch import (
    reconcile_command_execution_job_status_after_mcp_result,
)


@pytest.fixture
def command_job() -> CommandExecutionJob:
    return CommandExecutionJob(
        "reconcile-test-job",
        {"command": "noop", "params": {}, "context": {}},
    )


def test_reconcile_logs_error_on_failure(
    command_job: CommandExecutionJob, caplog: pytest.LogCaptureFixture
) -> None:
    envelope = {
        "job_id": command_job.job_id,
        "command": "clear_trash",
        "result": {
            "success": False,
            "error": {"code": -32000, "message": "CLEAR_TRASH_ERROR"},
        },
        "status": "completed",
    }
    caplog.set_level(logging.ERROR)
    with patch.object(command_job, "get_status", return_value={"result": envelope}):
        with patch.object(command_job, "set_mcp_result"):
            with patch.object(command_job, "set_description"):
                reconcile_command_execution_job_status_after_mcp_result(command_job)
    assert "QUEUE_JOB_FAILED" in caplog.text
    assert "CLEAR_TRASH_ERROR" in caplog.text
    assert command_job.job_id in caplog.text


def test_reconcile_sets_failed_when_nested_result_has_success_false(
    command_job: CommandExecutionJob,
) -> None:
    envelope = {
        "job_id": command_job.job_id,
        "command": "clear_trash",
        "result": {
            "success": False,
            "error": {"code": -32000, "message": "CLEAR_TRASH_ERROR"},
        },
        "status": "completed",
    }
    with patch.object(command_job, "get_status", return_value={"result": envelope}):
        with patch.object(command_job, "set_mcp_result") as sm:
            with patch.object(command_job, "set_description"):
                reconcile_command_execution_job_status_after_mcp_result(command_job)
    sm.assert_called_once()
    args, kwargs = sm.call_args
    assert args[1] == "failed"
    assert args[0]["status"] == "failed"
    assert args[0]["result"]["success"] is False


def test_reconcile_noop_when_success(command_job: CommandExecutionJob) -> None:
    envelope = {
        "job_id": command_job.job_id,
        "command": "list_projects",
        "result": {"success": True, "data": {}},
        "status": "completed",
    }
    with patch.object(command_job, "get_status", return_value={"result": envelope}):
        with patch.object(command_job, "set_mcp_result") as sm:
            reconcile_command_execution_job_status_after_mcp_result(command_job)
    sm.assert_not_called()


def test_reconcile_handles_mcp_result_field_shape(
    command_job: CommandExecutionJob,
) -> None:
    envelope = {
        "job_id": command_job.job_id,
        "command": "clear_trash",
        "result": {
            "success": False,
            "error": {"code": -32000, "message": "CLEAR_TRASH_ERROR"},
        },
        "status": "completed",
    }
    with patch.object(command_job, "get_status", return_value={"mcp_result": envelope}):
        with patch.object(command_job, "set_mcp_result") as sm:
            with patch.object(command_job, "set_description"):
                reconcile_command_execution_job_status_after_mcp_result(command_job)
    sm.assert_called_once()
    args, _kwargs = sm.call_args
    assert args[1] == "failed"
    assert args[0]["status"] == "failed"


def test_reconcile_handles_direct_command_result_shape(
    command_job: CommandExecutionJob,
) -> None:
    # Some adapters may store command result directly under state["result"].
    state = {
        "command": "clear_trash",
        "result": {"success": False, "message": "CLEAR_TRASH_ERROR"},
    }
    with patch.object(command_job, "get_status", return_value=state):
        with patch.object(command_job, "set_mcp_result") as sm:
            with patch.object(command_job, "set_description"):
                reconcile_command_execution_job_status_after_mcp_result(command_job)
    sm.assert_called_once()
    args, _kwargs = sm.call_args
    assert args[1] == "failed"
    assert args[0]["result"]["success"] is False
