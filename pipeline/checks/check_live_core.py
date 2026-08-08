"""Live-server core gate: the deployed server answers, and answers correctly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

First check built on ``pipeline/live/client.py``, and the end-to-end proof that
the live harness works: it opens a real mTLS connection to the REAL deployed
ai-editor server (``192.168.254.26:15000`` by default, from wherever the check
runs), calls ``health`` and ``help``, and asserts the deployed version and the
registered command count. Nothing is mocked and no response is fabricated. A
server that does not answer makes this check RED with the reason -- the
deployment is this project's own service, so silence means it must be brought
back up, not that the check does not apply.

The expected version is read from the project's own ``pyproject.toml`` rather
than hard-coded, so a version bump does not silently invalidate the gate;
``AI_EDITOR_LIVE_EXPECTED_VERSION`` and ``AI_EDITOR_LIVE_EXPECTED_COMMANDS``
override both expectations for a deployment under test.

Coverage note (laws.live_api_contract_coverage): this check owns ``health`` and
``help`` only. It closes with a schema-driven :class:`CommandCoverage` report
for ``health`` and for ``universal_file_open``, naming every parameter and
error case the server DECLARES that no case here exercises -- the per-command
live checks own those. Coverage is read from the server's own
``help(cmdname=...)`` schema, so a parameter or error case added later cannot
be silently left untested.
"""

from __future__ import annotations

import dataclasses
import os
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List

from pipeline import registry
from pipeline.live.client import (
    CommandCoverage,
    LiveClient,
    data_of,
    is_success,
    run_live_check,
)
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-core"
CHECK_DESCRIPTION = (
    "Live gate against the REAL deployed server: health and help answer over "
    "mTLS, the deployed version matches the project version, and the "
    "registered command count agrees between health and the help catalog."
)

ENV_EXPECTED_VERSION = "AI_EDITOR_LIVE_EXPECTED_VERSION"
ENV_EXPECTED_COMMANDS = "AI_EDITOR_LIVE_EXPECTED_COMMANDS"
DEFAULT_EXPECTED_COMMANDS = 32
SCHEMA_SAMPLE_COMMAND = "universal_file_open"
_HEALTH_COMPONENTS = ("system", "process", "commands", "proxy_registration",
                      "queue_dependencies")
_UNIVERSAL_FILE_COMMANDS = (
    "universal_file_close", "universal_file_edit", "universal_file_node_at_line",
    "universal_file_open", "universal_file_preview", "universal_file_search",
    "universal_file_write")


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
    """Run one case; an assertion or an exception becomes a failing verdict."""
    try:
        return CaseResult(name, True, func() or "ok")
    except AssertionError as exc:
        return CaseResult(name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is this case's failure
        return CaseResult(name, False, f"unexpected exception:\n{traceback.format_exc()}")


def expected_version() -> str:
    """The version this deployment must report: ``AI_EDITOR_LIVE_EXPECTED_VERSION``
    when set, otherwise the repository-root ``VERSION`` file.

    ``VERSION`` is the single source of truth shared by the server, the client
    and the engine. This used to grep ``[project] version`` out of
    pyproject.toml; that stopped working the moment the three distributions were
    switched to ``dynamic = ["version"]`` reading this same file, and the check
    raised ``no [project] version found`` instead of comparing anything.
    """
    override = os.environ.get(ENV_EXPECTED_VERSION, "").strip()
    if override:
        return override
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    declared = version_file.read_text(encoding="utf-8").strip()
    if not declared:
        raise AssertionError(f"no version declared in {version_file}")
    return declared


def expected_command_count() -> int:
    """How many commands the deployed server must register."""
    raw = os.environ.get(ENV_EXPECTED_COMMANDS, "").strip()
    return int(raw) if raw else DEFAULT_EXPECTED_COMMANDS


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_health(client: LiveClient, state: Dict[str, Any]) -> str:
    """``health`` returns the documented shape, the deployed version, and a count."""
    envelope = client.call("health", {})
    state["health_envelope"] = envelope
    _require(is_success(envelope), f"health did not succeed: {envelope!r}")
    data = data_of(envelope)
    for key in ("status", "version", "uptime", "cst_trees_loaded", "components"):
        _require(key in data, f"health data is missing {key!r}: {sorted(data)}")
    _require(data["status"] == "ok", f"health status is {data['status']!r}, expected 'ok'")
    _require(isinstance(data["version"], str), "health version must be a string")
    wanted = expected_version()
    _require(data["version"] == wanted,
             f"deployed version is {data['version']!r}, expected {wanted!r}")
    _require(isinstance(data["uptime"], (int, float)) and data["uptime"] > 0,
             f"health uptime must be a positive number, got {data['uptime']!r}")
    _require(isinstance(data["cst_trees_loaded"], int),
             f"cst_trees_loaded must be an int, got {type(data['cst_trees_loaded']).__name__}")
    components = data["components"]
    _require(isinstance(components, dict), "health components must be an object")
    for name in _HEALTH_COMPONENTS:
        _require(name in components, f"health components missing {name!r}: {sorted(components)}")
        _require(isinstance(components[name], dict), f"component {name!r} must be an object")
    registered = components["commands"].get("registered_count")
    _require(isinstance(registered, int),
             f"registered_count must be an int, got {registered!r}")
    wanted_count = expected_command_count()
    _require(registered == wanted_count,
             f"server registers {registered} command(s), expected {wanted_count}")
    state["registered_count"] = registered
    return f"version {data['version']}, {registered} registered command(s), status ok"


def _case_help_catalog(client: LiveClient, state: Dict[str, Any]) -> str:
    """``help`` with no parameters returns the full catalog, agreeing with health."""
    envelope = client.call("help", {})
    state["help_envelope"] = envelope
    _require(is_success(envelope), f"help did not succeed: {envelope!r}")
    data = data_of(envelope)
    _require(sorted(data) == ["commands", "help_usage", "tool_info"],
             f"help data keys are {sorted(data)}, expected commands/help_usage/tool_info")
    commands = data["commands"]
    _require(isinstance(commands, dict), "help commands must be an object")
    for name, description in commands.items():
        _require(isinstance(name, str) and bool(name), f"command name {name!r} must be non-empty")
        _require(isinstance(description, str),
                 f"description of {name!r} must be a string, got {type(description).__name__}")
    registered = state.get("registered_count")
    _require(registered is None or len(commands) == registered,
             f"help lists {len(commands)} command(s) but health reports {registered}")
    _require(len(commands) == expected_command_count(),
             f"help lists {len(commands)} command(s), expected {expected_command_count()}")
    missing = [name for name in _UNIVERSAL_FILE_COMMANDS if name not in commands]
    _require(not missing, f"help catalog is missing domain command(s): {missing}")
    return f"{len(commands)} command(s) catalogued, consistent with health"


def _case_schema_helper(client: LiveClient, state: Dict[str, Any]) -> str:
    """``help(cmdname=...)`` yields a parsable parameter table and error-case map."""
    schema = client.command_schema(SCHEMA_SAMPLE_COMMAND)
    state["schema"] = schema
    _require(schema.name == SCHEMA_SAMPLE_COMMAND,
             f"schema reports name {schema.name!r}, expected {SCHEMA_SAMPLE_COMMAND!r}")
    _require(bool(schema.parameters), f"{SCHEMA_SAMPLE_COMMAND} declares no parameters")
    _require(bool(schema.error_cases), f"{SCHEMA_SAMPLE_COMMAND} declares no error cases")
    for name, spec in schema.parameters.items():
        _require(bool(spec.type), f"parameter {name!r} declares no type")
        _require(isinstance(spec.required, bool), f"parameter {name!r} has a non-boolean required")
    for code, case in schema.error_cases.items():
        _require(code == code.upper(), f"error code {code!r} is not a stable upper-case code")
        _require(bool(case.description), f"error case {code!r} declares no description")
    _require(bool(schema.required_parameters()),
             f"{SCHEMA_SAMPLE_COMMAND} declares no required parameter")
    return (f"{len(schema.parameters)} parameter(s), {len(schema.error_cases)} error case(s), "
            f"required: {', '.join(schema.required_parameters())}")


def _coverage_output(client: LiveClient, state: Dict[str, Any]) -> List[str]:
    """Schema-driven coverage for what this check touched, and for what it does not."""
    lines: List[str] = []
    health = CommandCoverage(client.command_schema("health"))
    health.record_call({}, state.get("health_envelope", {}))
    lines.append(health.report().format())
    schema = state.get("schema")
    if schema is not None:
        untouched = CommandCoverage(schema)
        lines.append(untouched.report().format())
        lines.append(f"  (owned by the per-command live checks, not by {CHECK_NAME})")
        lines.append(schema.format_declared_surface())
    return lines


def _body(client: LiveClient) -> CheckResult:
    """Run every case against one open live client and fold one verdict."""
    state: Dict[str, Any] = {}
    cases = (("health_reports_deployed_version_and_command_count", _case_health),
             ("help_catalog_agrees_with_health", _case_help_catalog),
             ("command_schema_helper_parses_declared_surface", _case_schema_helper))
    results = [_run_case(name, lambda f=func: f(client, state)) for name, func in cases]
    output = [result.format() for result in results]
    output.extend(_coverage_output(client, state))
    failed = [result.name for result in results if not result.passed]
    body = "\n".join(output)
    if failed:
        return CheckResult.fail(
            message=f"{len(failed)}/{len(results)} live core case(s) failed: "
                    + ", ".join(failed), output=body)
    return CheckResult.ok(
        message=f"{len(results)}/{len(results)} live core case(s) passed against "
                f"{client.endpoint.describe()}", output=body)


def check_live_core() -> CheckResult:
    """Entry point: run the live core cases against the deployed server."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_core)
