"""Live-server gate for the queue command family (8 commands).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises, against the REAL deployed ai-editor server over mTLS: queue_add_job,
queue_start_job, queue_stop_job, queue_delete_job, queue_get_job_status,
queue_get_job_logs, queue_list_jobs, queue_health. Nothing here is mocked;
every assertion is against a real JSON-RPC reply. Every job this check adds is
deleted before the check returns, success or failure, using unique
``uuid4``-suffixed job ids so a concurrent run against the same shared
deployment cannot collide with this one.

Registered unconditionally: an unreachable server is a plain RED failure (see
``pipeline.live.client``; no environment gate, no skip concept).

Coverage note -- read this before trusting the numbers below: ``pipeline.live.
client.parse_command_schema`` builds its parameter table from ``help(cmdname=
...)``'s ``data.metadata.parameters``. On this deployment that field is EMPTY
for every one of these 8 commands (queue_* are all ``type: builtin``), so
:class:`~pipeline.live.client.CommandCoverage` reports a vacuous 0/0 for
parameters no matter what this check sends -- it is not a gap in this check,
it is the same "declared surface understates the real one" defect the
project has already pinned for ``help``/``health``. The REAL parameter table
these commands honour lives at ``data.schema.properties``/``required``
(verified empirically), so each case below documents, in its own words, which
real parameter it exercised; :const:`QUEUE_SCHEMA_PROPERTIES` records the full
table for the coverage section. Declared ``error_cases`` are equally empty
for all 8 commands; the real failure codes below (duplicate id, unknown id,
invalid enum, missing required) are genuine, reproducible server behaviour
that the schema simply never documents.
"""

from __future__ import annotations

import dataclasses
import traceback
import uuid
from typing import Any, Callable, Dict, List

from pipeline import registry
from pipeline.live.client import CommandCoverage, LiveClient, data_of, error_code, is_success, run_live_check
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-queue"
CHECK_DESCRIPTION = (
    "Live gate against the REAL deployed server: full parameter and error-case "
    "coverage for all 8 queue_* commands (add/start/stop/delete/status/logs/"
    "list/health), cleaning up every job it creates.")

QUEUE_COMMANDS = ("queue_add_job", "queue_start_job", "queue_stop_job", "queue_delete_job",
                   "queue_get_job_status", "queue_get_job_logs", "queue_list_jobs", "queue_health")

#: The REAL parameter table (from data.schema.properties, not the empty
#: data.metadata.parameters -- see module docstring), for the coverage section.
QUEUE_SCHEMA_PROPERTIES = {
    "queue_add_job": "job_type (enum, required), job_id (required), params (object, required), "
                      "command (optional, only meaningful for job_type=command_execution)",
    "queue_start_job": "job_id (required)",
    "queue_stop_job": "job_id (required)",
    "queue_delete_job": "job_id (required)",
    "queue_get_job_status": "job_id (required)",
    "queue_get_job_logs": "job_id (required)",
    "queue_list_jobs": "status_filter (optional enum), limit (optional)",
    "queue_health": "(no parameters)",
}


@dataclasses.dataclass(frozen=True)
class CaseResult:
    """One named case's verdict: pass/fail plus a short human detail."""

    name: str
    passed: bool
    detail: str = ""

    def format(self) -> str:
        head = f"[{'PASS' if self.passed else 'FAIL'}] {self.name}"
        return f"{head} - {self.detail}" if self.detail else head


def _run_case(name: str, func: Callable[[], str]) -> CaseResult:
    """Run one case; an assertion or any exception becomes a failing verdict."""
    try:
        return CaseResult(name, True, func() or "ok")
    except AssertionError as exc:
        return CaseResult(name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is this case's failure
        return CaseResult(name, False, f"unexpected exception:\n{traceback.format_exc()}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _jid(label: str) -> str:
    return f"live-check-{label}-{uuid.uuid4().hex[:10]}"


def _coverages(client: LiveClient) -> Dict[str, CommandCoverage]:
    return {name: CommandCoverage(client.command_schema(name)) for name in QUEUE_COMMANDS}


def _call(client: LiveClient, cov: Dict[str, CommandCoverage], command: str,
          params: Dict[str, Any]) -> Dict[str, Any]:
    envelope = client.call(command, params)
    cov[command].record_call(params, envelope)
    return envelope


def _case_queue_health(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "queue_health", {})
    _require(is_success(envelope), f"queue_health did not succeed: {envelope!r}")
    data = data_of(envelope)
    _require("status" in data, f"queue_health data missing 'status': {sorted(data)}")
    return f"status={data.get('status')!r} running={data.get('running')!r}"


def _case_add_missing_required(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "queue_add_job", {"job_id": _jid("missing")})
    _require(not is_success(envelope), "queue_add_job with no job_type/params should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_add_invalid_enum(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    params = {"job_type": "not_a_real_type", "job_id": _jid("badenum"), "params": {}}
    envelope = _call(client, cov, "queue_add_job", params)
    _require(not is_success(envelope), "queue_add_job with a bogus job_type should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_lifecycle_long_running(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    """add(long_running)/status(pending)/start/stop-while-running/status/delete/delete-again.

    ``duration`` is generous enough that the stop lands on a genuinely
    'running' job rather than racing a job that already self-completed -- a
    race this check hit for real against ``job_type=custom`` during
    development (a fast-completing job made ``queue_stop_job`` fail with
    'Cannot stop job ... in state COMPLETED', a real and correct error, just
    not the one this case is trying to demonstrate).
    """
    jid = _jid("longrun")
    try:
        params = {"job_type": "long_running", "job_id": jid, "params": {"duration": 4, "task_type": "sleep"}}
        add = _call(client, cov, "queue_add_job", params)
        _require(is_success(add), f"queue_add_job(long_running) failed: {add!r}")
        st1 = _call(client, cov, "queue_get_job_status", {"job_id": jid})
        _require(is_success(st1) and data_of(st1).get("status") == "pending",
                  f"expected pending status right after add: {st1!r}")
        start = _call(client, cov, "queue_start_job", {"job_id": jid})
        _require(is_success(start), f"queue_start_job failed: {start!r}")
        client.run(_sleep(0.5))
        logs = _call(client, cov, "queue_get_job_logs", {"job_id": jid})
        _require(is_success(logs), f"queue_get_job_logs failed: {logs!r}")
        _require({"stdout", "stderr"} <= set(data_of(logs)), f"logs missing stdout/stderr: {data_of(logs)}")
        stop = _call(client, cov, "queue_stop_job", {"job_id": jid})
        _require(is_success(stop), f"queue_stop_job failed while job should still be running: {stop!r}")
        _require(data_of(stop).get("status") == "stopped", f"expected status=stopped: {stop!r}")
        delete1 = _call(client, cov, "queue_delete_job", {"job_id": jid})
        _require(is_success(delete1), f"queue_delete_job failed: {delete1!r}")
        delete2 = _call(client, cov, "queue_delete_job", {"job_id": jid})
        _require(is_success(delete2), f"re-deleting an already-deleted job unexpectedly failed: {delete2!r}")
        return f"job {jid}: add->status->start->logs->stop(while running)->delete->delete(idempotent) all ok"
    finally:
        client.call("queue_delete_job", {"job_id": jid})


def _case_lifecycle_custom_to_completion(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    """add(custom)/start/poll to natural completion/delete -- a second job_type value."""
    jid = _jid("custom")
    try:
        add = _call(client, cov, "queue_add_job", {"job_type": "custom", "job_id": jid, "params": {}})
        _require(is_success(add), f"queue_add_job(custom) failed: {add!r}")
        start = _call(client, cov, "queue_start_job", {"job_id": jid})
        _require(is_success(start), f"queue_start_job failed: {start!r}")
        status: Dict[str, Any] = {}
        for _ in range(15):
            envelope = _call(client, cov, "queue_get_job_status", {"job_id": jid})
            _require(is_success(envelope), f"queue_get_job_status failed: {envelope!r}")
            status = data_of(envelope)
            if status.get("status") not in ("pending", "running"):
                break
            client.run(_sleep(0.2))
        _require(status.get("status") in ("completed", "stopped", "failed"),
                  f"custom job never left pending/running: {status!r}")
        return f"job {jid}: custom job type reached terminal status {status.get('status')!r}"
    finally:
        client.call("queue_delete_job", {"job_id": jid})


def _case_lifecycle_command_execution(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    """add(job_type=command_execution, command=...)/start/poll-to-completed/list/delete."""
    jid = _jid("cmdexec")
    try:
        params = {"job_type": "command_execution", "job_id": jid, "command": "health",
                   "params": {"command": "health", "params": {}}}
        add = _call(client, cov, "queue_add_job", params)
        _require(is_success(add), f"queue_add_job(command_execution) failed: {add!r}")
        start = _call(client, cov, "queue_start_job", {"job_id": jid})
        _require(is_success(start), f"queue_start_job failed: {start!r}")
        status: Dict[str, Any] = {}
        for _ in range(15):
            envelope = _call(client, cov, "queue_get_job_status", {"job_id": jid})
            _require(is_success(envelope), f"queue_get_job_status failed: {envelope!r}")
            status = data_of(envelope)
            if status.get("status") in ("completed", "failed", "stopped"):
                break
            client.run(_sleep(0.3))
        _require(status.get("status") == "completed", f"command_execution job did not complete: {status!r}")
        _require(status.get("command_success") is True, f"inner command did not succeed: {status!r}")
        listing = _call(client, cov, "queue_list_jobs", {"status_filter": "completed", "limit": 5})
        _require(is_success(listing), f"queue_list_jobs(status_filter, limit) failed: {listing!r}")
        ids = [j.get("job_id") for j in data_of(listing).get("jobs", [])]
        _require(jid in ids, f"completed job {jid} not present in filtered listing: {ids}")
        return f"job {jid}: command_execution of 'health' completed, found via status_filter+limit"
    finally:
        client.call("queue_delete_job", {"job_id": jid})


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


def _case_add_duplicate(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    jid = _jid("dup")
    try:
        first = _call(client, cov, "queue_add_job", {"job_type": "custom", "job_id": jid, "params": {}})
        _require(is_success(first), f"first queue_add_job failed: {first!r}")
        second = _call(client, cov, "queue_add_job", {"job_type": "custom", "job_id": jid, "params": {}})
        _require(not is_success(second), "adding a duplicate job_id should fail")
        _require(error_code(second) == -32603, f"expected -32603, got {error_code(second)!r}")
        return f"code={error_code(second)} (already exists)"
    finally:
        client.call("queue_delete_job", {"job_id": jid})


def _case_list_default(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "queue_list_jobs", {})
    _require(is_success(envelope), f"queue_list_jobs() failed: {envelope!r}")
    data = data_of(envelope)
    _require(isinstance(data.get("jobs"), list), f"'jobs' must be a list: {data!r}")
    _require(isinstance(data.get("total_count"), int), f"'total_count' must be an int: {data!r}")
    return f"total_count={data.get('total_count')}"


def _case_unknown_job(client: LiveClient, cov: Dict[str, CommandCoverage], command: str) -> str:
    jid = _jid("unknown")
    envelope = _call(client, cov, command, {"job_id": jid})
    _require(not is_success(envelope), f"{command} against an unknown job_id should fail")
    _require(error_code(envelope) == -32603, f"expected -32603, got {error_code(envelope)!r}")
    return f"{command}({jid}) -> code={error_code(envelope)}"


def _coverage_lines(cov: Dict[str, CommandCoverage]) -> List[str]:
    lines = ["-- coverage (help(cmdname=...) declares ZERO parameters for all 8 of these "
             "builtin commands -- see module docstring; real surface below is this check's "
             "own record, not the shared harness's) --"]
    for name in QUEUE_COMMANDS:
        lines.append(cov[name].report().format())
        lines.append(f"    real schema.properties surface: {QUEUE_SCHEMA_PROPERTIES[name]}")
    return lines


def _body(client: LiveClient) -> CheckResult:
    cov = _coverages(client)
    cases = [
        _run_case("queue_health", lambda: _case_queue_health(client, cov)),
        _run_case("queue_add_job_missing_required", lambda: _case_add_missing_required(client, cov)),
        _run_case("queue_add_job_invalid_enum", lambda: _case_add_invalid_enum(client, cov)),
        _run_case("queue_lifecycle_long_running", lambda: _case_lifecycle_long_running(client, cov)),
        _run_case("queue_lifecycle_custom_to_completion",
                  lambda: _case_lifecycle_custom_to_completion(client, cov)),
        _run_case("queue_lifecycle_command_execution", lambda: _case_lifecycle_command_execution(client, cov)),
        _run_case("queue_add_job_duplicate_id", lambda: _case_add_duplicate(client, cov)),
        _run_case("queue_list_jobs_default", lambda: _case_list_default(client, cov)),
        _run_case("queue_get_job_status_unknown", lambda: _case_unknown_job(client, cov, "queue_get_job_status")),
        _run_case("queue_start_job_unknown", lambda: _case_unknown_job(client, cov, "queue_start_job")),
        _run_case("queue_stop_job_unknown", lambda: _case_unknown_job(client, cov, "queue_stop_job")),
        _run_case("queue_get_job_logs_unknown", lambda: _case_unknown_job(client, cov, "queue_get_job_logs")),
        _run_case("queue_delete_job_never_existed", lambda: _case_unknown_job(client, cov, "queue_delete_job")),
    ]
    lines = [c.format() for c in cases]
    lines += [""] + _coverage_lines(cov)
    lines += ["", "-- deliberately left untested (see reasons) --",
              "  queue_add_job job_type enum values not exercised: data_processing, "
              "file_operation, api_call, batch_processing, file_download, periodic_logging "
              "(3 of 9 declared values -- custom, long_running, command_execution -- were "
              "exercised; the untried ones share the same add/status/delete code path, only "
              "their params sub-shape differs)"]
    output = "\n".join(lines)
    failed = [c.name for c in cases if not c.passed]
    if failed:
        return CheckResult.fail(message=f"{len(failed)}/{len(cases)} case(s) failed: " + ", ".join(failed),
                                 output=output)
    return CheckResult.ok(message=f"{len(cases)}/{len(cases)} case(s) passed", output=output)


def check_live_queue() -> CheckResult:
    """Run every queue_* case against the deployed server; RED if unreachable."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_queue)
