"""Live-server gate for the framework command family (11 commands).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises, against the REAL deployed ai-editor server over mTLS: help, health,
config, reload, settings, load, unload, plugins, transport_management,
proxy_registration, roletest. Nothing here is mocked.

Risk decisions (read before touching this file): ``reload``, ``load``,
``unload``, ``transport_management``, and ``proxy_registration`` can disturb a
running server. Each was independently verified by reading the exact
installed ``mcp-proxy-adapter==8.10.20`` source before being called live:

- ``reload`` with no ``config_path`` (its only real parameter, and this check
  never supplies one) only recounts already-registered commands under a lock;
  it does not rescan, reload config, or restart anything. Called for real.
- ``transport_management``'s three actions (``get_info``/``validate``/
  ``reload``) are ALL read-only queries against in-memory state; its own
  ``reload`` action is a stub that returns current info plus a hardcoded
  timestamp (asserted below) -- not a real reload. Called for real.
- ``proxy_registration`` is an explicitly TEST-ONLY in-memory registry,
  isolated from real MCP-Proxy registration. Called for real, full round
  trip, and unregistered again before this check returns.
- ``load`` dynamically imports and registers arbitrary Python code from its
  ``source`` parameter into the running process. Only the missing-required-
  parameter error path is exercised; no source value is ever supplied. A
  positive load is LEFT DELIBERATELY UNTESTED -- too risky to automate.
- ``unload`` is source-verified BROKEN on this deployed version (its
  ``registry.unload_command`` method does not exist on ``CommandRegistry``
  at all), so every call fails before reaching any removal logic regardless
  of target. Called for real with a bogus target only, which safely proves
  exactly that.

Registered unconditionally: an unreachable server is a plain RED failure (see
``pipeline.live.client``; no environment gate, no skip concept).

Coverage note -- read before trusting the numbers below: ``CommandCoverage``
reads ``help(cmdname=...)``'s ``data.metadata.parameters``, EMPTY for all 11
commands (the same declared-surface defect already pinned for ``help``/
``health``; ``_case_help`` asserts it directly). None of these commands'
real parameters (``config``'s operation/path/value, ``settings``'s operation/
key/value, ``roletest``'s action, ``transport_management``'s action,
``proxy_registration``'s operation and friends, ``unload``'s command_name)
appear in ``schema.properties`` either -- reading the installed
``mcp-proxy-adapter==8.10.20`` command source was the only way to find them;
see ``FRAMEWORK_REAL_SURFACE`` below.
"""

from __future__ import annotations

import dataclasses
import traceback
import uuid
from typing import Any, Callable, Dict, List

from pipeline import registry
from pipeline.live.client import CommandCoverage, LiveClient, data_of, error_code, is_success, result_of, run_live_check
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-framework"
CHECK_DESCRIPTION = (
    "Live gate against the REAL deployed server: full parameter and error-case "
    "coverage for all 11 framework commands (help, health, config, reload, "
    "settings, load, unload, plugins, transport_management, proxy_registration, "
    "roletest), pinning every success-wraps-failure and declared-surface defect "
    "found along the way; a real 'load' and any real 'unload' target are left "
    "deliberately untested as too risky to automate.")

FRAMEWORK_COMMANDS = ("help", "health", "config", "reload", "settings", "load", "unload",
                       "plugins", "transport_management", "proxy_registration", "roletest")


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


def _coverages(client: LiveClient) -> Dict[str, CommandCoverage]:
    return {name: CommandCoverage(client.command_schema(name)) for name in FRAMEWORK_COMMANDS}


def _call(client: LiveClient, cov: Dict[str, CommandCoverage], command: str,
          params: Dict[str, Any]) -> Dict[str, Any]:
    envelope = client.call(command, params)
    cov[command].record_call(params, envelope)
    return envelope


def _case_help(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    catalog = _call(client, cov, "help", {})
    _require(is_success(catalog), f"help() failed: {catalog!r}")
    _require(isinstance(data_of(catalog).get("commands"), dict) and data_of(catalog)["commands"],
            f"help() catalog missing/empty 'commands': {data_of(catalog)!r}")
    detail = _call(client, cov, "help", {"cmdname": "health"})
    _require(is_success(detail) and "schema" in data_of(detail), f"help(cmdname='health') malformed: {detail!r}")
    unknown = _call(client, cov, "help", {"cmdname": "does_not_exist"})
    _require(is_success(unknown), "DEFECT CHECK: help(cmdname=unknown) must still report success=True "
                                   f"(it does on this deployment; verify still holds): {unknown!r}")
    _require("error" in data_of(unknown), f"expected the failure hidden in data.error: {unknown!r}")
    schema = client.command_schema("help")
    _require(not schema.parameters,
             "DEFECT CHECK: help's declared metadata.parameters should be empty even though "
             f"cmdname demonstrably works (verify still holds): {schema.parameters}")
    return ("catalog+detail ok; DEFECTS confirmed: (1) cmdname='does_not_exist' -> success=True "
            "with data.error hidden inside (a failure reported as success); (2) help declares "
            "ZERO parameters in metadata.parameters although cmdname works and is documented in "
            "data.schema.properties instead")


def _case_health(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "health", {})
    _require(is_success(envelope), f"health() failed: {envelope!r}")
    _require(data_of(envelope).get("status") == "ok", f"expected status=ok: {envelope!r}")
    rejected = _call(client, cov, "health", {"bogus_extra_param": 1})
    _require(not is_success(rejected), "health with an undeclared extra parameter should be rejected")
    _require(error_code(rejected) == -32602, f"expected -32602, got {error_code(rejected)!r}")
    _require("Allowed parameters: []" in str((result_of(rejected).get("error") or {}).get("message")),
            f"expected the 'Allowed parameters: []' message confirming zero declared params: {rejected!r}")
    return "health() ok; extra-param rejection confirms health truly declares zero parameters"


def _case_config(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    scoped = _call(client, cov, "config", {"operation": "get", "path": "server.port"})
    _require(is_success(scoped), f"config(get, path) failed: {scoped!r}")
    _require(data_of(scoped).get("config", {}).get("server.port") is not None,
            f"expected server.port in scoped config: {scoped!r}")
    default_op = _call(client, cov, "config", {})
    _require(is_success(default_op) and data_of(default_op).get("operation") == "get",
            f"config() with no operation should default to 'get': {default_op!r}")
    set_missing = _call(client, cov, "config", {"operation": "set"})
    _require(not is_success(set_missing), "config(set) with no path/value should fail")
    _require(error_code(set_missing) == -32603, f"expected -32603, got {error_code(set_missing)!r}")
    bogus_op = _call(client, cov, "config", {"operation": "not_a_real_operation"})
    _require(not is_success(bogus_op), "config with an unknown operation should fail")
    _require(error_code(bogus_op) == -32603, f"expected -32603, got {error_code(bogus_op)!r}")
    return "get(path)/get(default)/set(missing args, no mutation)/invalid-operation all as expected"


def _case_settings(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    all_settings = _call(client, cov, "settings", {})
    _require(result_of(all_settings).get("success") is True and "all_settings" in result_of(all_settings),
            f"settings() should default to get_all: {all_settings!r}")
    _require("data" not in result_of(all_settings),
            "DEFECT CHECK: settings' payload is NOT nested under 'data' like other commands "
            f"(verify still holds): {all_settings!r}")
    got = _call(client, cov, "settings", {"operation": "get", "key": "__live_check_probe__"})
    _require(result_of(got).get("success") is True, f"settings(get, key) failed: {got!r}")
    get_missing = _call(client, cov, "settings", {"operation": "get"})
    _require(result_of(get_missing).get("success") is False, f"settings(get) with no key should fail: {get_missing!r}")
    set_missing = _call(client, cov, "settings", {"operation": "set"})
    _require(result_of(set_missing).get("success") is False,
            f"settings(set) with no key should fail (no mutation): {set_missing!r}")
    reloaded = _call(client, cov, "settings", {"operation": "reload"})
    _require(result_of(reloaded).get("success") is True, f"settings(reload) failed: {reloaded!r}")
    bogus = _call(client, cov, "settings", {"operation": "not_a_real_operation"})
    _require(result_of(bogus).get("success") is False, f"settings with an unknown operation should fail: {bogus!r}")
    return ("get_all/get(key)/get(missing key)/set(missing key, no mutation)/reload/unknown-operation "
            "all as expected; DEFECT confirmed: payload sits directly on result, not under result.data")


def _case_plugins(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "plugins", {})
    _require(is_success(envelope), f"plugins() (envelope level) failed: {envelope!r}")
    data = data_of(envelope)
    _require({"success", "plugins_server", "plugins", "total_plugins"} <= set(data),
            f"plugins() data missing expected keys: {data!r}")
    return f"plugins() ok, inner success={data.get('success')!r} ({data.get('error', 'no error')})"


def _case_roletest(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    default = _call(client, cov, "roletest", {})
    _require(is_success(default), f"roletest() failed: {default!r}")
    with_action = _call(client, cov, "roletest", {"action": "write"})
    _require(is_success(with_action), f"roletest(action=write) failed: {with_action!r}")
    _require(data_of(with_action) == {},
            "DEFECT CHECK: roletest's user_role/permissions/action/allowed fields never reach the "
            f"envelope (RoleTestCommandResult sets attributes directly, not via data=); got: {with_action!r}")
    return "roletest() ok for two actions; DEFECT confirmed: response body carries no fields at all"


def _case_transport_management(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    info = _call(client, cov, "transport_management", {})
    _require(is_success(info), f"transport_management() (get_info default) failed: {info!r}")
    _require("transport_info" in data_of(info), f"missing transport_info: {info!r}")
    validated = _call(client, cov, "transport_management", {"action": "validate"})
    _require(is_success(validated), f"transport_management(validate) (envelope) failed: {validated!r}")
    _require("error" in data_of(validated).get("transport_info", {}),
            "DEFECT CHECK: action=validate hits a missing TransportManager.validate_config attribute "
            f"and still reports envelope success=True: {validated!r}")
    reloaded = _call(client, cov, "transport_management", {"action": "reload"})
    _require(is_success(reloaded), f"transport_management(reload) failed: {reloaded!r}")
    stamp = data_of(reloaded).get("transport_info", {}).get("reload", {}).get("timestamp")
    _require(stamp == "2025-08-15T12:00:00Z",
            f"DEFECT CHECK: action=reload is a stub with a hardcoded timestamp, expected "
            f"'2025-08-15T12:00:00Z', got {stamp!r} -- if this ever varies, reload stopped being a stub")
    bogus = _call(client, cov, "transport_management", {"action": "not_a_real_action"})
    _require(is_success(bogus), f"transport_management(bogus action) (envelope) failed: {bogus!r}")
    _require("Unknown action" in str(data_of(bogus).get("transport_info", {}).get("error", "")),
            f"expected an 'Unknown action' message embedded in transport_info: {bogus!r}")
    return ("get_info/validate/reload/bogus-action all envelope-success=True; DEFECTS confirmed: "
            "validate's internal AttributeError and reload's hardcoded stub timestamp both hide "
            "behind success=True, and reload performs no real reload")


def _msg(envelope: Dict[str, Any]) -> str:
    """proxy_registration puts its human message as a sibling of 'data', not inside it."""
    return str(result_of(envelope).get("message", ""))


def _case_proxy_registration(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    server_id = f"live-check-{uuid.uuid4().hex[:10]}"
    reg_missing = _call(client, cov, "proxy_registration", {"operation": "register"})
    _require(is_success(reg_missing), f"proxy_registration(register, missing) (envelope) failed: {reg_missing!r}")
    _require("Missing required parameters" in _msg(reg_missing), f"expected a missing-parameters message: {reg_missing!r}")
    reg = _call(client, cov, "proxy_registration",
                {"operation": "register", "server_id": server_id, "server_url": "https://example.invalid:1"})
    _require(is_success(reg), f"proxy_registration(register) failed: {reg!r}")
    server_key = data_of(reg).get("server_key")
    _require(isinstance(server_key, str) and server_key.startswith(server_id),
            f"expected a server_key derived from {server_id!r}: {reg!r}")
    try:
        discovered = _call(client, cov, "proxy_registration", {"operation": "discover"})
        _require(is_success(discovered), f"proxy_registration(discover) failed: {discovered!r}")
        keys = [p.get("server_key") for p in data_of(discovered).get("details", {}).get("proxies", [])]
        _require(server_key in keys, f"registered probe {server_key} not found via discover: {keys}")
        hb_missing = _call(client, cov, "proxy_registration", {"operation": "heartbeat"})
        _require("Missing required parameter" in _msg(hb_missing), f"expected missing server_key message: {hb_missing!r}")
        hb = _call(client, cov, "proxy_registration", {"operation": "heartbeat", "server_key": server_key})
        _require(is_success(hb) and data_of(hb).get("details", {}).get("status") == "healthy",
                f"proxy_registration(heartbeat) failed: {hb!r}")
        bogus = _call(client, cov, "proxy_registration", {"operation": "not_a_real_operation"})
        _require("Unknown operation" in _msg(bogus), f"expected unknown-operation message: {bogus!r}")
        un_missing = _call(client, cov, "proxy_registration", {"operation": "unregister"})
        _require("Missing required parameter" in _msg(un_missing), f"expected missing server_id message: {un_missing!r}")
    finally:
        un = client.call("proxy_registration", {"operation": "unregister", "server_id": server_id})
        cov["proxy_registration"].record_call({"operation": "unregister", "server_id": server_id}, un)
        _require(data_of(un).get("details", {}).get("unregistered") is True,
                f"cleanup unregister of {server_id} failed: {un!r}")
    return (f"full register->discover->heartbeat->unregister round trip for {server_key} plus every "
            "missing-parameter/unknown-operation path; DEFECT confirmed: every failure mode still "
            "reports envelope success=True (domain failure is only visible in data.message)")


def _case_reload(client: LiveClient, cov: Dict[str, CommandCoverage], expected_total: int) -> str:
    envelope = _call(client, cov, "reload", {})
    _require(is_success(envelope), f"reload() failed: {envelope!r}")
    data = data_of(envelope) or result_of(envelope)
    _require(data.get("config_reloaded") is False, f"no config_path was sent, expected config_reloaded=False: {data!r}")
    _require(data.get("total_commands") == expected_total,
            f"reload()'s total_commands ({data.get('total_commands')}) should match health's "
            f"registered_count ({expected_total})")
    _require(data.get("server_restart_required") is True and "restart required" in str(data.get("message", "")),
            f"DEFECT CHECK: message always claims a restart is required even though nothing changed: {data!r}")
    return (f"reload() recounted {data.get('total_commands')} commands, matching health; DEFECT confirmed: "
            "'server restart required' is reported unconditionally, even with config_reloaded=False")


def _case_load(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "load", {})
    _require(not is_success(envelope), "load() with no source should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}; a real 'source' value is deliberately never sent (see module docstring)"


def _case_unload(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    no_target = _call(client, cov, "unload", {})
    _require(not is_success(no_target), "unload() with no command_name should fail")
    _require(error_code(no_target) == -32603, f"expected -32603, got {error_code(no_target)!r}")
    message = str((result_of(no_target).get("error") or {}).get("message", ""))
    _require("missing 1 required positional argument" in message,
            f"DEFECT CHECK: schema declares zero required params, yet the real Python TypeError "
            f"leaks through verbatim: {message!r}")
    bogus = _call(client, cov, "unload", {"command_name": "definitely_not_a_loaded_command_xyz"})
    _require(not is_success(bogus), "unload() with any target should fail on this deployment")
    _require("has no attribute 'unload_command'" in str((result_of(bogus).get("error") or {}).get("message", "")),
            f"DEFECT CHECK: registry.unload_command does not exist -- unload can never succeed: {bogus!r}")
    return ("DEFECTS confirmed: (1) unload's schema declares no required params but execute() needs "
            "command_name positionally, leaking a raw Python TypeError; (2) unload is unconditionally "
            "broken on this deployment (CommandRegistry has no unload_command method) -- no target, "
            "real or bogus, can ever succeed, so no real command was ever at risk of being unloaded")


#: The REAL parameter surface each command actually honours (verified by reading
#: the exact installed mcp-proxy-adapter==8.10.20 command source), for the
#: coverage section -- none of it is in help(cmdname=...)'s declared schema.
FRAMEWORK_REAL_SURFACE = {
    "help": "cmdname (in data.schema.properties only, NOT in metadata.parameters)",
    "health": "(genuinely no parameters -- the one command family member where "
              "declared and real agree)",
    "config": "operation (get/set, default 'get'), path, value -- none declared",
    "reload": "config_path (optional, never sent by this check) -- not declared",
    "settings": "operation (get/set/get_all/reload, default 'get_all'), key, value -- none declared",
    "load": "source (required) -- not declared",
    "unload": "command_name (required positionally) -- not declared at all",
    "plugins": "(no real parameters; reads commands.plugins_server from server config)",
    "transport_management": "action (get_info/validate/reload, default 'get_info') -- not declared",
    "proxy_registration": "operation (register/unregister/heartbeat/discover) plus "
                           "operation-specific fields -- none declared",
    "roletest": "action (default 'read') -- not declared",
}


def _coverage_lines(cov: Dict[str, CommandCoverage]) -> List[str]:
    lines = ["-- coverage (help(cmdname=...) declares ZERO parameters in metadata.parameters "
             "for all 11 of these commands -- see module docstring; real surface below is this "
             "check's own record from reading the command source, not the shared harness's) --"]
    for name in FRAMEWORK_COMMANDS:
        lines.append(cov[name].report().format())
        lines.append(f"    real surface: {FRAMEWORK_REAL_SURFACE[name]}")
    return lines


def _body(client: LiveClient) -> CheckResult:
    cov = _coverages(client)
    health_probe = client.call("health", {})
    _require(is_success(health_probe), f"pre-flight health() failed: {health_probe!r}")
    registered = data_of(health_probe)["components"]["commands"]["registered_count"]

    cases = [
        _run_case("help_family", lambda: _case_help(client, cov)),
        _run_case("health_family", lambda: _case_health(client, cov)),
        _run_case("config_family", lambda: _case_config(client, cov)),
        _run_case("settings_family", lambda: _case_settings(client, cov)),
        _run_case("plugins_family", lambda: _case_plugins(client, cov)),
        _run_case("roletest_family", lambda: _case_roletest(client, cov)),
        _run_case("transport_management_family", lambda: _case_transport_management(client, cov)),
        _run_case("proxy_registration_family", lambda: _case_proxy_registration(client, cov)),
        _run_case("reload_family", lambda: _case_reload(client, cov, registered)),
        _run_case("load_family", lambda: _case_load(client, cov)),
        _run_case("unload_family", lambda: _case_unload(client, cov)),
    ]
    def _final_health_recheck() -> str:
        envelope = client.call("health", {})
        cov["health"].record_call({}, envelope)
        _require(is_success(envelope) and data_of(envelope).get("status") == "ok",
                f"post-run health check failed: {envelope!r}")
        return (f"server still healthy: status={data_of(envelope).get('status')!r} "
                f"registered_count={data_of(envelope)['components']['commands']['registered_count']!r}")

    cases.append(_run_case("final_health_recheck", _final_health_recheck))

    lines = [c.format() for c in cases]
    lines += [""] + _coverage_lines(cov)
    lines += ["", "-- deliberately left untested (see reasons) --",
              "  load: never called with a real 'source' -- would dynamically import and register "
              "arbitrary code into the shared running process; too risky to automate (see module docstring)",
              "  unload: never called with the name of a real registered command -- pointless anyway, "
              "since the underlying registry.unload_command method does not exist and every call fails "
              "identically regardless of target (see module docstring); command_name is exercised, but "
              "only via a bogus value",
              "  health: its one declared error case, COMMAND_ERROR, has no known reliable trigger from "
              "the outside (it guards an unexpected internal failure in the health handler itself)",
              "  settings: operation='set' is exercised only via its missing-key error path; a real "
              "key/value set was left untested to avoid mutating a process-global settings dict shared "
              "with concurrent work on this deployment",
              "  config: operation='set' is exercised only via its missing-path/value error path, for "
              "the same reason -- a real set persists to the server's configuration file via config.save()"]
    output = "\n".join(lines)
    failed = [c.name for c in cases if not c.passed]
    if failed:
        return CheckResult.fail(message=f"{len(failed)}/{len(cases)} case(s) failed: " + ", ".join(failed),
                                 output=output)
    return CheckResult.ok(message=f"{len(cases)}/{len(cases)} case(s) passed", output=output)


def check_live_framework() -> CheckResult:
    """Run every framework case against the deployed server; RED if unreachable."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_framework)
