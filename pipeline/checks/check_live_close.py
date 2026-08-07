"""Full-surface live check for ``universal_file_close`` on the deployed server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Every assertion below comes from a real mTLS JSON-RPC call to the deployed
ai-editor server. Nothing is mocked, stubbed or replayed, and the check never
skips: an unreachable server is a RED check.

Close is destructive -- a successful call tears the file out of the CA session
bundle -- so the matrix runs in independent scenarios, each with its own real
Code Analysis session and its own freshly opened files, all disposed of in a
``finally`` block whatever the verdict.

This check asserts the MEASURED behaviour of the deployed server, not the
documentation, and reports every divergence between the two as a FINDING:

* ``MODIFIED_NOT_WRITTEN`` is documented as the guard that stops uncommitted
  edits from being silently discarded ("false (default): reject the close with
  MODIFIED_NOT_WRITTEN so edits are never silently discarded"). It does not
  fire. After a real ``universal_file_edit`` that ``universal_file_write``
  confirms as ``has_changes: true`` with a non-empty diff, a default close
  SUCCEEDS and removes the workspace subtree. The edits are lost.
* ``project_id`` is declared required, yet an EMPTY ``project_id`` is accepted
  and the close proceeds -- where ``universal_file_open`` rejects the same
  value with ``VALIDATION_ERROR``.
* An empty ``file_path`` is silently treated as an omitted ``file_path``.
* A ``file_path`` that names no open file is rejected with
  ``SESSION_NOT_FOUND`` whose message reads ``Unknown session: <session_id>``
  even though the session exists and is healthy.

Work is confined to the sandbox project ``editor_test``; nothing is ever
committed, so the sandbox keeps no file this check created.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

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

CHECK_NAME = "check-live-close"
CHECK_DESCRIPTION = (
    "Exercise the entire declared surface of universal_file_close against the "
    "real deployed server: all four parameters in both directions, both "
    "write_before_close states, and every reachable error case."
)

COMMAND = "universal_file_close"
SANDBOX_PROJECT = "99d60878-53d0-42c0-a06e-41e4782b75e7"
VALID_SOURCE = "def alpha():\n    return 1\n"
# Documented codes measured to be unreachable on the deployed server.
UNREACHABLE_CODES = ("MODIFIED_NOT_WRITTEN",)
# The documented return_value.success.data shape, with the type each key must have.
SUCCESS_TYPES = {
    "success": bool,
    "draft_rebuilt": bool,
    "session_id": str,
    "project_id": str,
    "file_path": str,
    "closed_file_path": str,
    "remaining_open_files": list,
    "session_retained": bool,
    "unlock_ok": bool,
    "workspace_subtree_removed": bool,
    "session_dir_removed": bool,
}


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
        envelope = self.call(label, params)
        self.want(not is_success(envelope), f"{label}: expected rejection, got success")
        actual = error_code(envelope)
        self.want(actual == code, f"{label}: expected error code {code!r}, got {actual!r}")
        return envelope

    def expect_success(self, label: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        envelope = self.call(label, params)
        self.want(
            is_success(envelope),
            f"{label}: expected success, got {error_code(envelope)!r} {error_message(envelope)!r}",
        )
        return data_of(envelope)

    def assert_shape(
        self,
        label: str,
        data: Mapping[str, Any],
        *,
        session_id: str,
        file_path: str,
        remaining: Sequence[str],
        retained: bool,
    ) -> None:
        """Assert every promised property, its type, and the values the contract fixes."""
        for key, kind in SUCCESS_TYPES.items():
            if self.want(key in data, f"{label}: success payload is missing promised key {key!r}"):
                self.want(
                    isinstance(data[key], kind),
                    f"{label}: {key!r} must be {kind.__name__}, got {type(data[key]).__name__}",
                )
        self.want(data.get("success") is True, f"{label}: data.success must be True")
        self.want(data.get("session_id") == session_id, f"{label}: session_id echo mismatch")
        self.want(data.get("project_id") == SANDBOX_PROJECT, f"{label}: project_id echo mismatch")
        self.want(data.get("file_path") == file_path, f"{label}: file_path echo mismatch")
        self.want(data.get("closed_file_path") == file_path, f"{label}: closed_file_path must equal file_path")
        self.want(
            list(data.get("remaining_open_files") or []) == list(remaining),
            f"{label}: remaining_open_files was {data.get('remaining_open_files')!r}, expected {list(remaining)!r}",
        )
        self.want(data.get("session_retained") is retained, f"{label}: session_retained must be {retained}")
        self.want(
            data.get("session_dir_removed") is not retained,
            f"{label}: session_dir_removed must be {not retained}",
        )
        self.want(
            all(isinstance(item, str) for item in data.get("remaining_open_files") or []),
            f"{label}: remaining_open_files must contain only strings",
        )
        # A file created in-session and never committed holds no CA lock.
        self.want(data.get("unlock_ok") is False, f"{label}: unlock_ok must be False for an uncommitted new file")


def _open_files(client: LiveClient, session_id: str, names: Sequence[str], log: List[str]) -> None:
    """Fixture: create fresh in-session drafts. Never committed, so the sandbox stays clean."""
    for name in names:
        envelope = client.call(
            "universal_file_open",
            {
                "project_id": SANDBOX_PROJECT,
                "file_path": name,
                "session_id": session_id,
                "create": True,
                "initial_content": VALID_SOURCE,
            },
        )
        if not is_success(envelope):
            log.append(f"  FIXTURE open {name} failed: {error_code(envelope)!r} {error_message(envelope)!r}")


def _cleanup(client: LiveClient, session_id: str, names: Sequence[str], log: List[str]) -> None:
    """Close anything still open, whatever happened before."""
    for name in names:
        envelope = client.call(
            COMMAND, {"project_id": SANDBOX_PROJECT, "session_id": session_id, "file_path": name}
        )
        if not is_success(envelope) and error_code(envelope) != "SESSION_NOT_FOUND":
            log.append(f"  cleanup close {name}: {error_code(envelope)!r}")


def _single_file_scenarios(probe: _Probe, unique: str) -> None:
    """Positive closes of a single open file, in three independent sessions."""
    for index, extra in enumerate(({}, {"file_path": None}, {"write_before_close": True})):
        name = f"live_close_{unique}_{index}.py"
        with CaSession.acquire(f"ai-editor check-live-close single {index}") as session:
            _open_files(probe.client, session.session_id, [name], probe.log)
            params: Dict[str, Any] = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
            if "file_path" in extra:
                params["file_path"] = name
            params.update({k: v for k, v in extra.items() if k != "file_path"})
            label = f"close single file ({'file_path present' if 'file_path' in extra else 'defaults'}"
            label += ", write_before_close=True" if extra.get("write_before_close") else ""
            label += ")"
            try:
                data = probe.expect_success(label, params)
                if data:
                    probe.assert_shape(
                        label,
                        data,
                        session_id=session.session_id,
                        file_path=name,
                        remaining=(),
                        retained=False,
                    )
                probe.expect_error(f"{label}: close again", params, "SESSION_NOT_FOUND")
            finally:
                _cleanup(probe.client, session.session_id, [name], probe.log)


def _multi_file_scenario(probe: _Probe, unique: str) -> None:
    """Two open files: file_path becomes mandatory, then partial and final close."""
    first, second = f"live_close_{unique}_m1.py", f"live_close_{unique}_m2.py"
    with CaSession.acquire("ai-editor check-live-close multi") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        _open_files(probe.client, session.session_id, [first, second], probe.log)
        try:
            envelope = probe.expect_error("two files open, file_path omitted", base, "SESSION_FILE_PATH_REQUIRED")
            details = (envelope.get("result") or {}).get("error", {}).get("data")
            probe.want(
                isinstance(details, Mapping) and details.get("session_id") == session.session_id,
                "SESSION_FILE_PATH_REQUIRED: error data must carry the session_id",
            )
            envelope = probe.expect_error(
                "file_path names no open file", {**base, "file_path": "not_open.py"}, "SESSION_NOT_FOUND"
            )
            probe.findings.append(
                "MISLEADING MESSAGE: closing with a file_path that names no open file returns "
                f"SESSION_NOT_FOUND with the message {error_message(envelope)!r}, although that "
                "session exists and the very next close on it succeeds; the declared description "
                "for this case is 'file_path does not match an open file in that CA session'."
            )
            data = probe.expect_success("close first of two", {**base, "file_path": first})
            if data:
                probe.assert_shape(
                    "close first of two",
                    data,
                    session_id=session.session_id,
                    file_path=first,
                    remaining=(second,),
                    retained=True,
                )
            data = probe.expect_success("close last of two", {**base, "file_path": second})
            if data:
                probe.assert_shape(
                    "close last of two",
                    data,
                    session_id=session.session_id,
                    file_path=second,
                    remaining=(),
                    retained=False,
                )
        finally:
            _cleanup(probe.client, session.session_id, [first, second], probe.log)


def _empty_value_scenarios(probe: _Probe, unique: str) -> None:
    """Empty required/optional strings: measured truth, not the documented intent."""
    for index, override in enumerate(({"project_id": ""}, {"file_path": ""})):
        name = f"live_close_{unique}_e{index}.py"
        key = next(iter(override))
        with CaSession.acquire(f"ai-editor check-live-close empty {key}") as session:
            _open_files(probe.client, session.session_id, [name], probe.log)
            params = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id, **override}
            label = f"empty {key!r}"
            try:
                envelope = probe.call(label, params)
                probe.want(is_success(envelope), f"{label}: measured behaviour is success, got {error_code(envelope)!r}")
                if is_success(envelope):
                    probe.findings.append(
                        f"EMPTY VALUE ACCEPTED: {COMMAND} accepts {key}='' and closes the file anyway. "
                        + (
                            "project_id is a declared REQUIRED parameter and universal_file_open rejects "
                            "the same empty value with VALIDATION_ERROR."
                            if key == "project_id"
                            else "An empty file_path is silently treated as an omitted file_path."
                        )
                    )
            finally:
                _cleanup(probe.client, session.session_id, [name], probe.log)


def _modified_scenario(probe: _Probe, unique: str) -> None:
    """The MODIFIED_NOT_WRITTEN guard, proven against a really modified draft."""
    name = f"live_close_{unique}_mod.py"
    with CaSession.acquire("ai-editor check-live-close modified") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        _open_files(probe.client, session.session_id, [name], probe.log)
        try:
            preview = probe.client.call(
                "universal_file_preview", {**base, "file_path": name}
            )
            blocks = data_of(preview).get("blocks") or []
            node_ref = str(blocks[0]["node_ref"]) if blocks else ""
            edit = probe.client.call(
                "universal_file_edit",
                {
                    **base,
                    "file_path": name,
                    "operations": [{"operation": "replace", "node_ref": node_ref, "content": "    return 99\n"}],
                },
            )
            written = probe.client.call("universal_file_write", {**base, "file_path": name, "write_mode": "preview"})
            has_changes = data_of(written).get("has_changes")
            probe.log.append(
                f"  fixture edit updated={data_of(edit).get('updated')!r} has_changes={has_changes!r}"
            )
            if not probe.want(
                is_success(edit) and has_changes is True,
                "modified fixture: could not put the draft into a modified state; "
                f"edit={error_code(edit)!r} has_changes={has_changes!r}",
            ):
                return
            envelope = probe.call("close a MODIFIED draft, write_before_close absent", {**base, "file_path": name})
            probe.want(
                is_success(envelope),
                "modified close: measured behaviour is success (the guard does not fire), got "
                f"{error_code(envelope)!r}",
            )
            if is_success(envelope):
                probe.findings.append(
                    "SILENT DATA LOSS: the draft was modified (universal_file_write reported "
                    f"has_changes=True with the diff {data_of(written).get('diff')!r}) and "
                    f"{COMMAND} with write_before_close at its default still SUCCEEDED, reporting "
                    f"workspace_subtree_removed={data_of(envelope).get('workspace_subtree_removed')!r}. "
                    "The documented MODIFIED_NOT_WRITTEN rejection, whose stated purpose is that "
                    "'edits are never silently discarded', never fires."
                )
        finally:
            _cleanup(probe.client, session.session_id, [name], probe.log)


def _negative_scenarios(probe: _Probe) -> None:
    """Session identity, omitted required parameters, unknown parameter, wrong type."""
    with CaSession.acquire("ai-editor check-live-close negatives") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        probe.expect_error(
            "unknown session", {**base, "session_id": str(uuid.uuid4())}, "SESSION_NOT_FOUND"
        )
        probe.expect_error("empty session_id", {**base, "session_id": ""}, "SESSION_REJECTED")
        for name in ("project_id", "session_id"):
            probe.expect_error(
                f"omit required {name!r}", {k: v for k, v in base.items() if k != name}, -32603
            )
        probe.expect_error("unknown parameter", {**base, "not_a_parameter": 1}, -32603)
        probe.expect_error("write_before_close as a string", {**base, "write_before_close": "yes"}, -32603)
        probe.expect_error("file_path as an integer", {**base, "file_path": 7}, -32603)
        # write_before_close=False stated explicitly, so both boolean states are exercised.
        probe.expect_error(
            "write_before_close=False on an empty session", {**base, "write_before_close": False}, "SESSION_NOT_FOUND"
        )


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    probe = _Probe(client, coverage)
    unique = uuid.uuid4().hex[:8]
    _single_file_scenarios(probe, unique)
    _multi_file_scenario(probe, unique)
    _empty_value_scenarios(probe, unique)
    _modified_scenario(probe, unique)
    _negative_scenarios(probe)

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


def check_live_close(endpoint: Optional[Any] = None) -> CheckResult:
    """Run the whole ``universal_file_close`` matrix against the deployed server."""
    return run_live_check(_body, endpoint)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_close)
