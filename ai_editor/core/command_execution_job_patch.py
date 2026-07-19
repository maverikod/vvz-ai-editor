"""
Patch for CommandExecutionJob to support progress tracking.

This module patches CommandExecutionJob to create and pass ProgressTracker
through context, allowing commands to update progress and logs.

Also reconciles queue terminal status with MCP ``CommandResult``: if the command
returns ``success: false`` (e.g. ``ErrorResult``), the job must not stay
``completed`` — ``mcp_proxy_adapter`` otherwise always records ``completed``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .progress_tracker import ProgressTracker  # noqa: F401

logger = logging.getLogger(__name__)


# Flag to track if patch has been applied
_patch_applied = False


def _mcp_failure_message(
    payload: Dict[str, Any], cmd_result: Optional[Dict[str, Any]]
) -> str:
    for block in (cmd_result, payload):
        if not isinstance(block, dict):
            continue
        err = block.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if block.get("message"):
            return str(block["message"])
    return "Command failed"


def _extract_mcp_payload_from_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract MCP envelope from queue job state across queue-manager variants.

    Known shapes:
    - {"result": {"job_id": ..., "command": ..., "result": {...}, "status": ...}}
    - {"mcp_result": {...}}
    - direct envelope in state itself
    """
    direct_result = state.get("result")
    if isinstance(direct_result, dict) and (
        "command" in direct_result or "result" in direct_result
    ):
        return direct_result
    mcp_result = state.get("mcp_result")
    if isinstance(mcp_result, dict):
        return mcp_result
    if "command" in state or (
        "result" in state and isinstance(state.get("result"), dict)
    ):
        return state
    return None


def _extract_command_result(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract inner command result dict from MCP envelope.

    In some adapters payload["result"] is the command result directly,
    in others payload may itself be the command result.
    """
    inner = payload.get("result")
    if isinstance(inner, dict):
        return inner
    if payload.get("success") is not None:
        return payload
    return None


def _is_already_reconciled_failed(state: Dict[str, Any]) -> bool:
    """True when reconcile already promoted this job to terminal failed."""
    outer = str(state.get("status", "")).strip().lower()
    if outer not in {"failed", "error"}:
        return False
    payload = _extract_mcp_payload_from_state(state)
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status", "")).strip().lower() == "failed"


def _failure_kind(
    payload: Dict[str, Any], cmd_result: Optional[Dict[str, Any]]
) -> Optional[str]:
    """Classify one stored terminal envelope without executing its command."""
    if payload.get("success") is False or (
        cmd_result is not None and cmd_result.get("success") is False
    ):
        return "failure"

    statuses = {
        str(block.get("status", "")).strip().lower()
        for block in (payload, cmd_result)
        if isinstance(block, dict)
    }
    if statuses & {"failed", "error", "timeout", "timed_out", "unknown"}:
        return "terminal_failure"
    if any(
        isinstance(block, dict) and block.get("error")
        for block in (payload, cmd_result)
    ):
        return "failure"
    if cmd_result is None and "result" in payload and payload.get("result") is None:
        return "unknown_result"
    return None


def reconcile_command_execution_job_status_after_mcp_result(job: Any) -> None:
    """
    If the stored MCP payload reports failure, set queue job status to ``failed``.

    ``CommandExecutionJob`` always wraps the command dict in
    ``{job_id, command, result: <to_dict()>, status: "completed"}``; this fixes
    ``queue_get_job_status`` when the inner command returned ``ErrorResult``.
    """
    try:
        from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob
    except ImportError:
        return
    if not isinstance(job, CommandExecutionJob):
        return
    try:
        state = job.get_status()
    except Exception:
        logger.debug(
            "reconcile: get_status failed for job %s", getattr(job, "job_id", "?")
        )
        return
    if not isinstance(state, dict):
        return
    if _is_already_reconciled_failed(state):
        return
    payload = _extract_mcp_payload_from_state(state)
    if not isinstance(payload, dict):
        return

    cmd_result = _extract_command_result(payload)
    failure_kind = _failure_kind(payload, cmd_result)
    if failure_kind is None:
        return

    desc = _mcp_failure_message(payload, cmd_result)
    job_id = getattr(job, "job_id", "?")
    cmd_name = payload.get("command")
    detail = payload
    job_log = getattr(job, "logger", None) or logger
    job_log.error(
        "[QUEUE_JOB_FAILED] job_id=%s command=%s: %s",
        job_id,
        cmd_name,
        desc,
    )
    job_log.error("[QUEUE_JOB_FAILED] job_id=%s mcp_result=%s", job_id, detail)

    # Keep the original envelope as evidence. Only terminal job status changes;
    # no command lookup or replacement execution is part of reconciliation.
    out = dict(payload)
    out["job_id"] = getattr(job, "job_id", "") or job_id
    out["status"] = "failed"
    out["reconciliation"] = {"kind": failure_kind, "original_job_id": job_id}
    try:
        job.set_mcp_result(out, "failed")
    except Exception as e:
        logger.warning(
            "reconcile: set_mcp_result(failed) failed for job %s: %s",
            getattr(job, "job_id", "?"),
            e,
        )
        return
    try:
        job.set_description(desc[:2000])
    except Exception:
        pass


def _patch_command_execution_set_mcp_result(CommandExecutionJob: Any) -> None:
    """
    Reconcile inner command failure after every ``set_mcp_result`` call.

    In spawn-mode workers, ``command_execution_job_patch`` is auto-imported from
    inside ``CommandExecutionJob.run()`` *after* that run has already started on
    the unpatched method. Wrapping ``set_mcp_result`` ensures reconcile still runs
    when the adapter stores the completed envelope with ``success: false`` inside.
    """
    if hasattr(CommandExecutionJob.set_mcp_result, "_reconcile_after_mcp_result"):
        return

    original_set_mcp_result = CommandExecutionJob.set_mcp_result

    def patched_set_mcp_result(
        self: Any, result: Dict[str, Any], status: Optional[str] = None
    ) -> None:
        original_set_mcp_result(self, result, status)
        if getattr(self, "_reconcile_after_mcp_result", False):
            return
        self._reconcile_after_mcp_result = True
        try:
            reconcile_command_execution_job_status_after_mcp_result(self)
        finally:
            self._reconcile_after_mcp_result = False

    patched_set_mcp_result._reconcile_after_mcp_result = True
    CommandExecutionJob.set_mcp_result = patched_set_mcp_result


def patch_command_execution_job():
    """
    Patch CommandExecutionJob to support progress tracking.

    This function modifies CommandExecutionJob.run() to create a ProgressTracker
    and pass it through context before executing the command.
    """
    global _patch_applied

    try:
        from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob
    except ImportError as e:
        logger.warning(f"Failed to patch CommandExecutionJob: {e}")
        return

    _patch_command_execution_set_mcp_result(CommandExecutionJob)

    if hasattr(CommandExecutionJob.run, "_progress_tracker_patched"):
        _patch_applied = True
        return

    try:
        from ..core.progress_tracker import ProgressTracker

        original_run = CommandExecutionJob.run

        def patched_run(self):
            """Patched run method that creates and passes ProgressTracker."""
            # Queue jobs run in dedicated child processes; no local DB to reinitialize.

            # Get context from mcp_params
            context = self.mcp_params.get("context", {}) or {}
            if not isinstance(context, dict):
                context = {}

            # Create ProgressTracker with methods from job
            progress_tracker = ProgressTracker(
                set_progress_fn=self.set_progress,
                set_description_fn=self.set_description,
                set_status_fn=self.set_status,
                log_fn=lambda msg: self.logger.info(msg),
            )

            # Add ProgressTracker to context
            context["progress_tracker"] = progress_tracker

            # Update mcp_params with modified context
            self.mcp_params["context"] = context

            # Call original run (adapter no longer overwrites progress/description
            # before await, so command-driven progress is visible in queue_get_job_status)
            original_run(self)
            reconcile_command_execution_job_status_after_mcp_result(self)

        patched_run._progress_tracker_patched = True
        CommandExecutionJob.run = patched_run
        _patch_applied = True
        logger.debug("Successfully patched CommandExecutionJob for progress tracking")

    except Exception as e:
        logger.error(f"Error patching CommandExecutionJob: {e}", exc_info=True)


# Auto-patch on import
patch_command_execution_job()
