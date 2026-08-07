"""Scenario matrix for the ``universal_file_close`` live check.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Split out of ``check_live_close`` so each module stays readable and within the
project's file-length limit. Every function here drives the REAL deployed
server through :class:`pipeline.live.client.LiveClient`; see the entry module's
docstring for what the matrix asserts and why.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Sequence

from pipeline.live.client import (
    CaSession,
    CommandCoverage,
    LiveClient,
    data_of,
    error_code,
    error_message,
    is_success,
)

COMMAND = "universal_file_close"
SANDBOX_PROJECT = "99d60878-53d0-42c0-a06e-41e4782b75e7"
# The commit path runs the editor's own Python quality validation, which requires
# module and function docstrings — a fixture without them is rejected at commit
# with VALIDATION_ERROR, which would look like a broken escape hatch.
VALID_SOURCE = (
    '"""Fixture module for the live close check."""\n\n\n'
    'def alpha() -> int:\n    """Return the fixture value.\n\n    Returns:\n        The fixture value.\n    """\n    return 1\n'
)
# The edit replaces the FIRST preview block, which for this fixture is the whole
# function. The commit path runs flake8 and the docstring rule over the result,
# so the replacement must itself be a complete, lint-clean definition -- a bare
# body line here fails validation and looks like a broken escape hatch.
EDITED_BODY = ('def alpha() -> int:\n    """Return the edited fixture value.\n\n'
               '    Returns:\n        The edited fixture value.\n    """\n    return 99\n')
# The one path this check commits to, so proving write_before_close=true really
# writes never leaves a growing pile of files behind: each run overwrites it.
ESCAPE_FIXTURE = "pipeline_live_close/write_before_close_fixture.py"
# Every documented code must be reachable; none is exempt any more.
UNREACHABLE_CODES: tuple = ()
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


_EXPECTED_CLEANUP_CODES = ("SESSION_NOT_FOUND", "MODIFIED_NOT_WRITTEN")


def _cleanup(client: LiveClient, session_id: str, names: Sequence[str], log: List[str]) -> None:
    """Close anything still open, whatever happened before.

    A draft deliberately left dirty answers MODIFIED_NOT_WRITTEN here, which is
    the correct behaviour and not a cleanup anomaly: the file was created inside
    the session and never committed, so nothing of it reaches the sandbox once
    the CA session is disposed.
    """
    for name in names:
        envelope = client.call(
            COMMAND, {"project_id": SANDBOX_PROJECT, "session_id": session_id, "file_path": name}
        )
        if not is_success(envelope) and error_code(envelope) not in _EXPECTED_CLEANUP_CODES:
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
    """An empty declared parameter is rejected, and the session survives intact."""
    for index, override in enumerate(({"project_id": ""}, {"file_path": ""})):
        name = f"live_close_{unique}_e{index}.py"
        key = next(iter(override))
        with CaSession.acquire(f"ai-editor check-live-close empty {key}") as session:
            _open_files(probe.client, session.session_id, [name], probe.log)
            base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
            label = f"empty {key!r}"
            try:
                probe.expect_error(label, {**base, **override}, "VALIDATION_ERROR")
                # The rejected call must not have torn the session down: the
                # very next well-formed close has to find the file still open.
                probe.expect_success(
                    f"{label}: the session survived the rejection",
                    {**base, "file_path": name},
                )
            finally:
                _cleanup(probe.client, session.session_id, [name], probe.log)


def _modify_draft(probe: _Probe, base: Mapping[str, Any], name: str) -> Any:
    """Put a freshly opened draft into a genuinely modified state.

    Returns:
        ``has_changes`` as universal_file_write reports it for the draft, so the
        caller can refuse to assert anything if the fixture never became dirty.
    """
    preview = probe.client.call("universal_file_preview", {**base, "file_path": name})
    blocks = data_of(preview).get("blocks") or []
    # The LAST block is the function; the first is the module docstring. Replacing
    # the docstring with a definition produced a duplicate `alpha` and the commit
    # validators (flake8, ruff, mypy) rejected it -- which read as a broken escape
    # hatch rather than as a bad fixture.
    node_ref = str(blocks[-1]["node_ref"]) if blocks else ""
    edit = probe.client.call(
        "universal_file_edit",
        {
            **base,
            "file_path": name,
            "operations": [
                {"operation": "replace", "node_ref": node_ref, "content": EDITED_BODY}
            ],
        },
    )
    written = probe.client.call(
        "universal_file_write", {**base, "file_path": name, "write_mode": "preview"}
    )
    has_changes = data_of(written).get("has_changes")
    probe.log.append(
        f"  fixture edit updated={data_of(edit).get('updated')!r} "
        f"has_changes={has_changes!r}"
    )
    return has_changes if is_success(edit) else None


def _modified_scenario(probe: _Probe, unique: str) -> None:
    """The MODIFIED_NOT_WRITTEN guard, proven against a really modified draft."""
    name = f"live_close_{unique}_mod.py"
    with CaSession.acquire("ai-editor check-live-close modified") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        _open_files(probe.client, session.session_id, [name], probe.log)
        try:
            has_changes = _modify_draft(probe, base, name)
            if not probe.want(
                has_changes is True,
                "modified fixture: could not put the draft into a modified state; "
                f"has_changes={has_changes!r}",
            ):
                return
            probe.expect_error(
                "close a MODIFIED draft, write_before_close absent",
                {**base, "file_path": name},
                "MODIFIED_NOT_WRITTEN",
            )
            # Refusal means refusal: the session is still open and still dirty,
            # so the edit was neither written nor thrown away.
            still = probe.client.call(
                "universal_file_write",
                {**base, "file_path": name, "write_mode": "preview"},
            )
            probe.want(
                is_success(still) and data_of(still).get("has_changes") is True,
                "after MODIFIED_NOT_WRITTEN the session must still be open with the "
                f"edit intact, got {error_code(still)!r} "
                f"has_changes={data_of(still).get('has_changes')!r}",
            )
        finally:
            _cleanup(probe.client, session.session_id, [name], probe.log)


def _write_before_close_scenario(probe: _Probe) -> None:
    """The declared escape must really commit the pending edit, then close."""
    # A fresh path per run. The previous fixed path made the check fail its own
    # SECOND run: write_before_close really does commit, so the file is in the
    # project index afterwards and `create=True` is then refused with
    # FILE_ALREADY_INDEXED -- the check breaking on its own success.
    name = f"pipeline_live_close/write_before_close_{uuid.uuid4().hex[:8]}.py"
    with CaSession.acquire("ai-editor check-live-close escape") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        _open_files(probe.client, session.session_id, [name], probe.log)
        try:
            has_changes = _modify_draft(probe, base, name)
            if not probe.want(
                has_changes is True,
                "escape fixture: could not put the draft into a modified state; "
                f"has_changes={has_changes!r}",
            ):
                return
            probe.expect_success(
                "close a MODIFIED draft with write_before_close=True",
                {**base, "file_path": name, "write_before_close": True},
            )
        finally:
            _cleanup(probe.client, session.session_id, [name], probe.log)
    # Re-open the committed file in a fresh session: the edit must be ON DISK,
    # which is the whole point of the escape and exactly what used to be lost.
    with CaSession.acquire("ai-editor check-live-close escape verify") as session:
        base = {"project_id": SANDBOX_PROJECT, "session_id": session.session_id}
        opened = probe.client.call(
            "universal_file_open", {**base, "file_path": name}
        )
        try:
            probe.want(
                is_success(opened),
                f"write_before_close must have created the file; open said "
                f"{error_code(opened)!r} {error_message(opened)!r}",
            )
            written = probe.client.call(
                "universal_file_write",
                {**base, "file_path": name, "write_mode": "preview"},
            )
            probe.want(
                is_success(written) and data_of(written).get("has_changes") is False,
                "the committed file must match what write_before_close wrote, got "
                f"has_changes={data_of(written).get('has_changes')!r}",
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
        # A malformed request answers with the DECLARED VALIDATION_ERROR. These four
        # asserted the generic -32603 they used to get: our own ValidationError was
        # unrecognised by the framework's run() and fell through to the catch-all,
        # discarding the declared code. That is fixed centrally in
        # BaseMCPCommand.run(), so the declared contract is now what the server keeps.
        for name in ("project_id", "session_id"):
            probe.expect_error(
                f"omit required {name!r}", {k: v for k, v in base.items() if k != name},
                "VALIDATION_ERROR",
            )
        probe.expect_error("unknown parameter", {**base, "not_a_parameter": 1}, "VALIDATION_ERROR")
        probe.expect_error(
            "write_before_close as a string", {**base, "write_before_close": "yes"}, "VALIDATION_ERROR"
        )
        probe.expect_error("file_path as an integer", {**base, "file_path": 7}, "VALIDATION_ERROR")
        # write_before_close=False stated explicitly, so both boolean states are exercised.
        probe.expect_error(
            "write_before_close=False on an empty session", {**base, "write_before_close": False}, "SESSION_NOT_FOUND"
        )
