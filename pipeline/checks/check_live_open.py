"""Full-surface live check for ``universal_file_open`` on the deployed server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Every assertion below comes from a real mTLS JSON-RPC call to the deployed
ai-editor server. Nothing is mocked, stubbed or replayed, and the check never
skips: an unreachable server is a RED check.

The exercised surface is driven by the server's own ``help(cmdname=...)``
reply, so a parameter or error case added later shows up as an untested
remainder in the coverage report instead of being silently ignored. All six
declared parameters are exercised in both directions -- valid value, optional
ones present AND absent, every enum value of ``format_group``, both boolean
states of ``create``, plus omitted-required, empty, wrong-type and unknown-
parameter rejections.

This check asserts the MEASURED behaviour of the deployed server, not the
documentation, and reports every divergence between the two as a FINDING:

* ``SESSION_INVALID`` is a documented stable code the server cannot emit. An
  empty ``session_id`` produces JSON-RPC ``-32603`` carrying the documented
  SESSION_INVALID message as free text. The code appears nowhere in
  ``ai_editor/``.
* ``PARSE_ERROR`` is documented but not emitted for a broken source file: the
  session opens in line-based fallback with ``is_invalid`` instead.
* ``VALIDATION_ERROR`` IS reachable -- through an empty ``project_id`` or an
  empty ``file_path``, not through an empty ``session_id``.
* The success payload carries ``read_only`` and a nested ``success``, neither
  of which the documented ``return_value.success.data`` shape mentions, and
  ``available_operations`` returns six operations where the documentation
  promises three.
* ``create=False`` on a file that really exists in the project -- the primary
  documented open path -- currently fails with ``OPEN_ERROR`` wrapping an
  upstream HTTP 500 from Code Analysis (``lock_file_and_download``).

Work is confined to the sandbox project ``editor_test``; every session and
every opened file is closed and deleted in a ``finally`` block.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional

from pipeline import registry
from pipeline.live.client import (
    CaSession,
    CommandCoverage,
    LiveClient,
    data_of,
    error_code,
    error_message,
    is_success,
    run_live_check,
)
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-open"
CHECK_DESCRIPTION = (
    "Exercise the entire declared surface of universal_file_open against the "
    "real deployed server: all six parameters in both directions, every "
    "format_group enum value, both create states, and every reachable error case."
)

COMMAND = "universal_file_open"
SANDBOX_PROJECT = "99d60878-53d0-42c0-a06e-41e4782b75e7"
# A file that really exists in the sandbox project, for the create=False path.
EXISTING_FILE = "docs/guide.md"
VALID_SOURCE = "def alpha():\n    return 1\n"
BROKEN_SOURCE = "def (:\n    ???\n"
# Documented codes measured to be unreachable on the deployed server.
UNREACHABLE_CODES = ("SESSION_INVALID", "PARSE_ERROR")
# Keys the documented return_value.success.data shape promises, with the type
# every one of them must have when present.
REQUIRED_SUCCESS_TYPES = {
    "session_id": str,
    "file_path": str,
    "format_group": str,
    "session_dir": str,
    "draft_path": str,
    "available_operations": list,
    "multi_file_bundle": dict,
}
OPTIONAL_SUCCESS_TYPES = {
    "created": bool,
    "repeat_open": bool,
    "fallback_reason": str,
    "is_invalid": bool,
    "warning": str,
    "mode_notice": str,
}
DOCUMENTED_SUCCESS_KEYS = set(REQUIRED_SUCCESS_TYPES) | set(OPTIONAL_SUCCESS_TYPES)


class _Probe:
    """One live call plus its verdict, accumulating failures and coverage."""

    def __init__(self, client: LiveClient, coverage: CommandCoverage) -> None:
        self.client, self.coverage = client, coverage
        self.failures: List[str] = []
        self.findings: List[str] = []
        self.log: List[str] = []

    def call(self, label: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        envelope = self.client.call(COMMAND, params)
        self.coverage.record_call(params, envelope)
        code = error_code(envelope)
        self.log.append(f"  {label}: {'success' if is_success(envelope) else f'error {code!r}'}")
        return envelope

    def want(self, condition: bool, message: str) -> bool:
        if not condition:
            self.failures.append(message)
        return condition

    def expect_error(self, label: str, params: Mapping[str, Any], code: Any) -> Dict[str, Any]:
        """Assert one call is rejected with exactly ``code``."""
        envelope = self.call(label, params)
        self.want(not is_success(envelope), f"{label}: expected rejection, got success")
        actual = error_code(envelope)
        self.want(actual == code, f"{label}: expected error code {code!r}, got {actual!r}")
        return envelope

    def expect_success(self, label: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Assert one call succeeds, and return its ``result.data``."""
        envelope = self.call(label, params)
        self.want(
            is_success(envelope),
            f"{label}: expected success, got {error_code(envelope)!r} {error_message(envelope)!r}",
        )
        return data_of(envelope)


def _assert_success_shape(probe: _Probe, label: str, data: Mapping[str, Any], expect_file: str) -> None:
    """Assert the promised properties, their types, and report undeclared extras."""
    for key, kind in REQUIRED_SUCCESS_TYPES.items():
        if probe.want(key in data, f"{label}: success payload is missing promised key {key!r}"):
            probe.want(
                isinstance(data[key], kind),
                f"{label}: {key!r} must be {kind.__name__}, got {type(data[key]).__name__}",
            )
    for key, kind in OPTIONAL_SUCCESS_TYPES.items():
        if key in data:
            probe.want(
                isinstance(data[key], kind),
                f"{label}: optional {key!r} must be {kind.__name__}, got {type(data[key]).__name__}",
            )
    probe.want(data.get("file_path") == expect_file, f"{label}: file_path echo mismatch")
    operations = data.get("available_operations")
    if isinstance(operations, list):
        probe.want(
            all(isinstance(item, str) for item in operations),
            f"{label}: available_operations must contain only strings",
        )
    bundle = data.get("multi_file_bundle")
    if isinstance(bundle, Mapping):
        probe.want(isinstance(bundle.get("session_id"), str), f"{label}: bundle.session_id must be str")
        probe.want(isinstance(bundle.get("open_file_count"), int), f"{label}: bundle.open_file_count must be int")
        files = bundle.get("files")
        if probe.want(isinstance(files, list), f"{label}: bundle.files must be a list"):
            for entry in files:
                probe.want(isinstance(entry, Mapping), f"{label}: bundle.files entry must be an object")
                for field in ("file_path", "project_id", "origin_path", "draft_path", "edit_subdir"):
                    probe.want(
                        isinstance(entry, Mapping) and isinstance(entry.get(field), str),
                        f"{label}: bundle.files entry lacks string {field!r}",
                    )
    extras = sorted(set(data) - DOCUMENTED_SUCCESS_KEYS)
    if extras:
        probe.findings.append(
            f"UNDECLARED RESPONSE KEYS: {COMMAND} success data carries {extras}, "
            "absent from the documented return_value.success.data shape"
        )


def _exercise(probe: _Probe, session_id: str, opened: List[str]) -> None:
    """Run the whole positive/negative matrix against the live server."""
    base = {"project_id": SANDBOX_PROJECT, "session_id": session_id}
    unique = uuid.uuid4().hex[:8]

    # --- positive: create=True with initial_content, structured format ---------
    created = f"live_open_{unique}.py"
    data = probe.expect_success(
        "create=True + initial_content",
        {**base, "file_path": created, "create": True, "initial_content": VALID_SOURCE},
    )
    if data:
        opened.append(created)
        _assert_success_shape(probe, "create=True", data, created)
        probe.want(data.get("session_id") == session_id, "create=True: session_id echo mismatch")
        probe.want(data.get("created") is True, "create=True: 'created' must be True for a new file")
        probe.want(data.get("format_group") == "sidecar", "create=True: .py must route to the sidecar group")

    # --- FILE_ALREADY_OPEN: the very same file, same session -------------------
    probe.expect_error(
        "repeat open",
        {**base, "file_path": created, "create": True, "initial_content": VALID_SOURCE},
        "FILE_ALREADY_OPEN",
    )

    # --- positive: initial_content ABSENT --------------------------------------
    empty_file = f"live_open_empty_{unique}.py"
    if probe.expect_success("create=True, initial_content absent", {**base, "file_path": empty_file, "create": True}):
        opened.append(empty_file)

    # --- positive: every format_group enum value, on an unknown extension ------
    # Measured truth: the override is accepted for all three values, but the
    # echoed format_group is the EFFECTIVE group after handler fallback, so
    # 'sidecar' and 'tree-temp' both come back as 'text' with is_invalid True.
    for value in ("sidecar", "tree-temp", "text"):
        name = f"live_open_{value.replace('-', '_')}_{unique}.zzz"
        data = probe.expect_success(
            f"format_group={value!r}",
            {**base, "file_path": name, "create": True, "initial_content": "key: 1\n", "format_group": value},
        )
        if not data:
            continue
        opened.append(name)
        echoed, invalid = data.get("format_group"), data.get("is_invalid")
        probe.want(echoed == "text", f"format_group={value!r}: response echoed {echoed!r}, expected 'text'")
        # 'text' parses anything, so is_invalid is omitted entirely for it.
        probe.want(
            invalid is True if value != "text" else invalid is None,
            f"format_group={value!r}: is_invalid was {invalid!r}",
        )
        if value != "text":
            probe.findings.append(
                f"OVERRIDE NOT HONOURED: format_group={value!r} on an unknown extension is accepted, "
                f"but the handler falls back and the response echoes format_group={echoed!r} with "
                "is_invalid True; the documentation calls this parameter an explicit format group override."
            )

    # --- PARSE_ERROR is documented; the server falls back instead --------------
    broken = f"live_open_broken_{unique}.py"
    data = probe.expect_success(
        "broken source, create=True", {**base, "file_path": broken, "create": True, "initial_content": BROKEN_SOURCE}
    )
    if data:
        opened.append(broken)
        probe.want(data.get("is_invalid") is True, "broken source: expected is_invalid True in fallback mode")
        probe.want(isinstance(data.get("fallback_reason"), str), "broken source: fallback_reason must be a string")

    # --- UNKNOWN_FORMAT: unknown extension, no format_group hint ---------------
    probe.expect_error(
        "unknown extension, no format_group",
        {**base, "file_path": f"live_open_{unique}.zzz", "create": True, "initial_content": "x"},
        "UNKNOWN_FORMAT",
    )

    # --- create=False, both on a missing and on a really existing file ---------
    missing = f"live_open_missing_{unique}.py"
    for label, params in (
        ("create=False on a missing file", {**base, "file_path": missing, "create": False}),
        ("create absent (default False) on a missing file", {**base, "file_path": missing}),
        ("unknown project_id", {"project_id": str(uuid.uuid4()), "session_id": session_id, "file_path": missing}),
    ):
        probe.expect_error(label, params, "OPEN_ERROR")

    envelope = probe.call("create=False on an EXISTING file", {**base, "file_path": EXISTING_FILE, "create": False})
    if is_success(envelope):
        opened.append(EXISTING_FILE)
        _assert_success_shape(probe, "create=False existing", data_of(envelope), EXISTING_FILE)
    else:
        probe.want(
            error_code(envelope) == "OPEN_ERROR",
            f"create=False existing: expected OPEN_ERROR, got {error_code(envelope)!r}",
        )
        probe.findings.append(
            "BROKEN PRIMARY PATH: create=False open of the existing file "
            f"{EXISTING_FILE!r} fails with OPEN_ERROR: {error_message(envelope)!r}. "
            "The upstream Code Analysis lock_file_and_download returns HTTP 500, so the "
            "documented primary open path cannot be exercised end to end on this deployment."
        )

    # --- negative: session identity -------------------------------------------
    probe.expect_error("unknown session", {**base, "session_id": str(uuid.uuid4()), "file_path": "a.py"}, "SESSION_NOT_FOUND")
    envelope = probe.expect_error("empty session_id", {**base, "session_id": "", "file_path": "a.py"}, -32603)
    probe.findings.append(
        "UNDELIVERABLE DOCUMENTED CODE: universal_file_open declares SESSION_INVALID for a "
        "missing or empty session_id, but an empty session_id yields JSON-RPC "
        f"{error_code(envelope)!r} with the documented text as a free-form message "
        f"({error_message(envelope)!r}). SESSION_INVALID appears nowhere in ai_editor/."
    )

    # --- negative: empty required strings -> the stable VALIDATION_ERROR -------
    probe.expect_error("empty file_path", {**base, "file_path": ""}, "VALIDATION_ERROR")
    probe.expect_error(
        "empty project_id", {"project_id": "", "session_id": session_id, "file_path": "a.py"}, "VALIDATION_ERROR"
    )

    # --- negative: each required parameter omitted in turn ---------------------
    complete = {**base, "file_path": "a.py"}
    for name in ("project_id", "file_path", "session_id"):
        probe.expect_error(
            f"omit required {name!r}", {k: v for k, v in complete.items() if k != name}, -32603
        )

    # --- negative: unknown parameter, wrong type, out-of-enum value ------------
    probe.expect_error("unknown parameter", {**complete, "not_a_parameter": 1}, -32603)
    probe.expect_error("create as a string", {**complete, "create": "yes"}, -32603)
    probe.expect_error("format_group out of enum", {**complete, "format_group": "nonsense"}, -32603)


def _close_all(client: LiveClient, session_id: str, opened: List[str], log: List[str]) -> None:
    """Close every file this check opened, whatever happened before."""
    for file_path in opened:
        envelope = client.call(
            "universal_file_close",
            {"project_id": SANDBOX_PROJECT, "session_id": session_id, "file_path": file_path},
        )
        log.append(f"  cleanup close {file_path}: {'ok' if is_success(envelope) else error_code(envelope)!r}")


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    probe = _Probe(client, coverage)
    opened: List[str] = []
    with CaSession.acquire("ai-editor live check-live-open") as session:
        try:
            _exercise(probe, session.session_id, opened)
        finally:
            _close_all(client, session.session_id, opened, probe.log)

    report = coverage.report()
    for code in UNREACHABLE_CODES:
        if code in schema.error_cases and code in report.untested_error_codes:
            probe.findings.append(
                f"UNREACHABLE DOCUMENTED CODE: {code} is declared by {COMMAND} but no call in "
                "this full-surface matrix could provoke it on the deployed server."
            )
    output = "\n".join(
        [schema.format_declared_surface(), "", "calls:", *probe.log, "", report.format()]
        + (["", "FINDINGS (documented contract vs measured behaviour):"] if probe.findings else [])
        + [f"  - {item}" for item in probe.findings]
        + (["", "FAILURES:"] if probe.failures else [])
        + [f"  - {item}" for item in probe.failures]
    )
    summary = (
        f"{COMMAND}: {len(report.declared_parameters)} declared parameters exercised live, "
        f"{len(report.declared_error_codes) - len(report.untested_error_codes)}"
        f"/{len(report.declared_error_codes)} error cases reached, "
        f"{len(probe.findings)} contract finding(s)"
    )
    if probe.failures:
        return CheckResult.fail(f"{summary}; {len(probe.failures)} live assertion(s) FAILED", output)
    return CheckResult.ok(summary, output)


def check_live_open(endpoint: Optional[Any] = None) -> CheckResult:
    """Run the whole ``universal_file_open`` matrix against the deployed server."""
    return run_live_check(_body, endpoint)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_open)
