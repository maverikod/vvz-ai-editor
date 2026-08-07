"""Live full-surface check for ``info``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``info`` is documentation, not a data operation: its declared surface is
zero parameters and one declared error case (``COMMAND_ERROR``). "Full
surface" for a documentation command means asserting that what it DOCUMENTS
matches what the server ACTUALLY exposes, not just that the call returns
200-shaped JSON. Concretely, this check:

* Asserts the response's top-level shape (every key the guide promises,
  with the right type), against the REAL deployed server, not the doc text.
* Cross-checks ``info``'s own ``registered_commands`` list against the
  server's real command catalog from ``help()`` (32 commands on 1.0.84) and
  asserts EVERY registered command is now documented by name (fixed:
  ``registered_commands`` used to list only the 9 "thin-server" domain
  commands; see ``ai_editor/commands/editor_info_content.py``'s
  ``ALL_REGISTERED_COMMANDS``).
* Confirms every command ``info`` DOES list is a real, currently-registered
  command name (no stale/renamed entries), which passes today.
* Confirms via ``help(cmdname="info")`` that the schema itself declares zero
  parameters -- an unknown extra parameter is rejected with ``-32602``
  ("Allowed parameters: []"), which is a DIFFERENT generic code from the
  ``VALIDATION_ERROR`` string pattern used by the ``universal_file_*``
  commands for the same kind of rejection; recorded as an observed fact, not
  assumed to be uniform across the API. ``info``/``health`` are built by
  ``ai_editor`` itself (not the ``mcp_proxy_adapter`` framework); ``help``
  itself lives in the framework and is out of this project's scope.
* Notes the declared ``COMMAND_ERROR`` error case has no known public-API
  trigger (no way to make a zero-parameter command fail through user input
  alone); left untested and named via the coverage report.

Registration is unconditional, like ``check-live-core``: there is no
environment gate and no skip concept anywhere in this file.
:func:`pipeline.live.client.run_live_check` FAILS the check outright when the
server cannot be reached -- the deployment is this project's own service, so
an unreachable server is this check being RED, not opting out.
"""

from __future__ import annotations

import dataclasses
import traceback
from typing import Callable, List

from pipeline import registry
from pipeline.live.client import (
    CommandCoverage,
    LiveClient,
    data_of,
    error_code,
    is_success,
    run_live_check,
)
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-info"
CHECK_DESCRIPTION = (
    "Live full-surface check for info against the REAL deployed server: "
    "response shape, cross-checked against the real help() command catalog "
    "-- FAILS by name on every registered command info does not document -- "
    "plus its zero-parameter schema and the -32602 unknown-parameter path.")

COMMAND = "info"
_EXPECTED_TOP_LEVEL_TYPES = {
    "guide_version": str,
    "architecture": str,
    "summary": str,
    "markdown": str,
    "lifecycle": list,
    "registered_commands": list,
    "format_groups": dict,
    "examples": dict,
    "docs": dict,
}


@dataclasses.dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    detail: str = ""

    def format(self) -> str:
        head = f"[{'PASS' if self.passed else 'FAIL'}] {self.name}"
        return f"{head} - {self.detail}" if self.detail else head


def _run_case(name: str, func: Callable[[], str]) -> CaseResult:
    try:
        return CaseResult(name, True, func() or "ok")
    except AssertionError as exc:
        return CaseResult(name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is this case's failure
        return CaseResult(name, False, f"unexpected exception:\n{traceback.format_exc()}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _build_cases(client: LiveClient, coverage: CommandCoverage) -> List[tuple]:
    def info(params: dict) -> dict:
        env = client.call(COMMAND, params)
        coverage.record_call(params, env)
        return env

    def case_response_shape() -> str:
        env = info({})
        d = data_of(env)
        _require(is_success(env), f"expected success: {env!r}")
        missing = [k for k in _EXPECTED_TOP_LEVEL_TYPES if k not in d]
        _require(not missing, f"missing documented key(s): {missing}")
        wrong_type = [k for k, t in _EXPECTED_TOP_LEVEL_TYPES.items()
                      if k in d and not isinstance(d[k], t)]
        _require(not wrong_type,
                  f"wrong type for: {[(k, type(d[k]).__name__) for k in wrong_type]}")
        _require(bool(d["markdown"].strip()), "markdown must be non-empty")
        _require(bool(d["lifecycle"]), "lifecycle must be non-empty")
        _require(bool(d["registered_commands"]), "registered_commands must be non-empty")
        return (f"all {len(_EXPECTED_TOP_LEVEL_TYPES)} documented top-level keys present "
                "with the documented type")

    def case_registered_commands_are_all_real() -> str:
        info_env = info({})
        catalog_env = client.call("help", {})
        _require(is_success(info_env) and is_success(catalog_env), "setup calls must succeed")
        listed = data_of(info_env)["registered_commands"]
        real = set(data_of(catalog_env)["commands"])
        stale = [c for c in listed if c not in real]
        _require(not stale, f"info lists command(s) that do not exist on the server: {stale}")
        return f"all {len(listed)} command(s) info documents are real, currently-registered commands"

    def case_info_documents_every_registered_command() -> str:
        info_env = info({})
        catalog_env = client.call("help", {})
        _require(is_success(info_env) and is_success(catalog_env), "setup calls must succeed")
        listed = set(data_of(info_env)["registered_commands"])
        real = set(data_of(catalog_env)["commands"])
        missing = sorted(real - listed)
        _require(not missing,
                  f"{len(missing)}/{len(real)} registered command(s) are NOT documented by "
                  f"info's own registered_commands table: {missing}")
        return f"info documents every one of the {len(real)} currently-registered commands"

    def case_schema_declares_zero_parameters() -> str:
        schema = client.command_schema(COMMAND)
        _require(schema.parameters == {}, f"parameters={schema.parameters!r}")
        _require(list(schema.error_cases) == ["COMMAND_ERROR"],
                  f"error_cases={list(schema.error_cases)!r}")
        return "help(cmdname='info') declares zero parameters and exactly ['COMMAND_ERROR']"

    def case_unknown_extra_parameter_rejected_32602() -> str:
        env = info({"bogus": 1})
        _require(not is_success(env), f"expected failure: {env!r}")
        code = error_code(env)
        _require(code == -32602, f"code={code!r}")
        return ("unknown extra parameter -> generic -32602 'Allowed parameters: []' -- "
                "note this differs from the -32603 'unknown parameter' pattern used by the "
                "universal_file_* commands for the same kind of rejection")

    return [
        ("response_shape", case_response_shape),
        ("registered_commands_are_all_real", case_registered_commands_are_all_real),
        ("info_documents_every_registered_command", case_info_documents_every_registered_command),
        ("schema_declares_zero_parameters", case_schema_declares_zero_parameters),
        ("unknown_extra_parameter_rejected_32602", case_unknown_extra_parameter_rejected_32602),
    ]


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    cases = _build_cases(client, coverage)
    results = [_run_case(name, func) for name, func in cases]

    output = [r.format() for r in results]
    report = coverage.report()
    output.append(report.format())
    if not report.complete:
        output.append("NOTE: COMMAND_ERROR has no known public-API trigger for a zero-parameter "
                       "command -- left untested, named here.")
    output.append(schema.format_declared_surface())
    failed = [r.name for r in results if not r.passed]
    body_text = "\n".join(output)
    if failed:
        return CheckResult.fail(
            message=f"{len(failed)}/{len(results)} info case(s) failed: " + ", ".join(failed),
            output=body_text)
    return CheckResult.ok(
        message=f"{len(results)}/{len(results)} info case(s) passed against "
                f"{client.endpoint.describe()}; coverage: {report.format().splitlines()[0]}",
        output=body_text)


def check_live_info() -> CheckResult:
    """Entry point: run the live info cases against the real deployed server.
    An unreachable server FAILS the check (see run_live_check) -- there is no
    skip concept and no registration gate: the check always exists."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_info)
