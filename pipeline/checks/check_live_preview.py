"""Full-surface live check for ``universal_file_preview`` on the deployed server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Every assertion below comes from a real mTLS JSON-RPC call to the deployed
ai-editor server. Nothing is mocked, stubbed or replayed, and the check never
skips: an unreachable server is a RED check.

Preview has by far the widest surface of the three session-lifecycle commands:
eleven declared parameters and eleven declared error cases, split across two
addressing modes. The matrix below drives three fixtures in one real Code
Analysis session -- a parseable Python draft, a deliberately broken one that
opens in line-based fallback, and a draft with an extension no preview handler
knows -- and exercises every parameter present AND absent, both addressing
modes, and all eleven error cases.

This check asserts the MEASURED behaviour of the deployed server, not the
documentation, and reports every divergence between the two as a FINDING:
``selector`` is documented as a "list of int indices" but reads integers as
short_ids, so the documented index ``0`` is rejected with
``INVALID_SELECTOR_FORM``; ``selector`` is declared ``type: string`` in the
parameter table while the command's own JSON schema declares
``oneOf[string, array]``; ``preview_lines`` below its lower bound is rejected
with ``HANDLER_ERROR`` ("unexpected failure inside preview orchestration")
rather than the declared ``VALIDATION_ERROR``; an empty ``session_id`` is
silently treated as an omitted one and falls through to the one-shot path;
and one-shot preview of a file that really exists fails with ``HANDLER_ERROR``
wrapping an upstream HTTP 500 from Code Analysis, so the documented one-shot
download path cannot be exercised end to end on this deployment.

Work is confined to the sandbox project ``editor_test``; every file this check
opens is closed and the CA session deleted in a ``finally`` block.
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

CHECK_NAME = "check-live-preview"
CHECK_DESCRIPTION = (
    "Exercise the entire declared surface of universal_file_preview against "
    "the real deployed server: all eleven parameters in both directions, both "
    "addressing modes, and all eleven declared error cases."
)

COMMAND = "universal_file_preview"
SANDBOX_PROJECT = "99d60878-53d0-42c0-a06e-41e4782b75e7"
# A file that really exists in the sandbox project, for the one-shot path.
EXISTING_FILE = "docs/guide.md"
VALID_SOURCE = "".join(f"def f{i}():\n    return {i}\n" for i in range(6))
BROKEN_SOURCE = "def (:\n    ???\n    still broken\n"
PLAIN_SOURCE = "alpha\nbeta\ngamma\n"


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

    def assert_structural(self, label: str, data: Mapping[str, Any]) -> None:
        """Assert the promised structural-mode shape, property by property."""
        focus = data.get("focus")
        if self.want(isinstance(focus, Mapping), f"{label}: focus must be an object"):
            self.want(isinstance(focus.get("node_kind"), str), f"{label}: focus.node_kind must be a string")
            self.want(isinstance(focus.get("node_ref"), int), f"{label}: focus.node_ref must be int in marked-tree mode")
            self.want(isinstance(focus.get("attributes"), Mapping), f"{label}: focus.attributes must be an object")
        blocks = data.get("blocks")
        if self.want(isinstance(blocks, list), f"{label}: blocks must be a list"):
            for block in blocks:
                self.want(isinstance(block, Mapping), f"{label}: every block must be an object")
                self.want(
                    isinstance(block, Mapping) and isinstance(block.get("node_ref"), int),
                    f"{label}: every block needs an integer node_ref",
                )
        self.want(isinstance(data.get("total_blocks"), int), f"{label}: total_blocks must be an int")
        self.want(isinstance(data.get("mode_notice"), str), f"{label}: mode_notice must be a string")
        self.want("selector_applied" in data, f"{label}: selector_applied must always be present")
        self.want(
            (focus or {}).get("is_invalid") in (None, False) if isinstance(focus, Mapping) else True,
            f"{label}: focus.is_invalid must not be True in structural mode",
        )

    def assert_fallback(self, label: str, data: Mapping[str, Any], *, offset: int, total: int) -> None:
        """Assert the promised plain-text fallback shape and its pagination fields.

        ``is_invalid`` is documented as a focus attribute and is delivered as a
        key of ``focus`` itself, not of ``data``."""
        focus = data.get("focus")
        if not self.want(isinstance(focus, Mapping), f"{label}: focus must be an object"):
            return
        self.want(focus.get("is_invalid") is True, f"{label}: focus.is_invalid must be True in fallback mode")
        self.want(focus.get("node_ref") == "", f"{label}: focus.node_ref must be an empty string when invalid")
        self.want(isinstance(focus.get("text"), str), f"{label}: focus.text must be a string")
        attributes = focus.get("attributes")
        if not self.want(isinstance(attributes, Mapping), f"{label}: focus.attributes must be an object"):
            return
        self.want(isinstance(attributes.get("parse_error"), str), f"{label}: attributes.parse_error must be a string")
        self.want(
            attributes.get("preview_total_lines") == total,
            f"{label}: preview_total_lines was {attributes.get('preview_total_lines')!r}, expected {total}",
        )
        self.want(
            attributes.get("preview_line_offset") == offset,
            f"{label}: preview_line_offset was {attributes.get('preview_line_offset')!r}, expected {offset}",
        )
        self.want(
            attributes.get("preview_lines_returned") == total - offset,
            f"{label}: preview_lines_returned was {attributes.get('preview_lines_returned')!r}",
        )
        self.want(attributes.get("preview_has_more") is False, f"{label}: preview_has_more must be False here")


def _open(client: LiveClient, session_id: str, name: str, content: str, log: List[str], **extra: Any) -> None:
    """Fixture: create a fresh in-session draft. Never committed."""
    envelope = client.call(
        "universal_file_open",
        {
            "project_id": SANDBOX_PROJECT,
            "file_path": name,
            "session_id": session_id,
            "create": True,
            "initial_content": content,
            **extra,
        },
    )
    if not is_success(envelope):
        log.append(f"  FIXTURE open {name} failed: {error_code(envelope)!r} {error_message(envelope)!r}")


def _structural_matrix(probe: _Probe, base: Dict[str, Any]) -> None:
    """Every parameter of the structural (parseable) addressing mode."""
    data = probe.expect_success("baseline, every optional parameter absent", base)
    if not data:
        return
    probe.assert_structural("baseline", data)
    probe.want(data.get("total_blocks") == 6, f"baseline: total_blocks was {data.get('total_blocks')!r}, expected 6")
    probe.want(data.get("selector_applied") is None, "baseline: selector_applied must be null when omitted")
    blocks = data.get("blocks") or []
    node_ref = str(blocks[0]["node_ref"]) if blocks else "1"

    drilled = probe.expect_success("node_ref present", {**base, "node_ref": node_ref})
    if drilled:
        probe.assert_structural("node_ref", drilled)
        probe.want(
            str((drilled.get("focus") or {}).get("node_ref")) == node_ref,
            "node_ref: focus must be the requested node",
        )
    for label, selector in (
        ("selector slice", "0:2"),
        ("selector negative slice", "-2:"),
        ("selector list of node_ref strings", [node_ref]),
    ):
        data = probe.expect_success(label, {**base, "selector": selector})
        if data:
            probe.assert_structural(label, data)
            probe.want(data.get("selector_applied") is not None, f"{label}: selector_applied must echo the selector")
            probe.want(len(data.get("blocks") or []) <= 2, f"{label}: selector must cap the returned blocks")
    for label, params in (
        ("preview_lines lower bound (1)", {"preview_lines": 1}),
        ("preview_lines zero", {"preview_lines": 0}),
        ("value_preview_len lower bound (1)", {"value_preview_len": 1}),
        ("full_text_max_lines disabled (0)", {"full_text_max_lines": 0}),
        ("max_chars small (10)", {"max_chars": 10}),
        ("preview_offset default (0)", {"preview_offset": 0}),
    ):
        data = probe.expect_success(label, {**base, **params})
        if data:
            probe.assert_structural(label, data)

    # Documented as a list of int indices; measured as a list of short_ids.
    envelope = probe.expect_error(
        "selector list of int indices (documented form)", {**base, "selector": [0, 1]}, "INVALID_SELECTOR_FORM"
    )
    probe.findings.append(
        "DOCUMENTED FORM REJECTED: selector is documented as 'list of int indices', but an integer "
        f"in that list is read as a short_id, so [0, 1] is rejected: {error_message(envelope)!r}."
    )
    probe.expect_error("selector malformed", {**base, "selector": "not-a-slice"}, "INVALID_SELECTOR_FORM")
    probe.expect_error("node_ref unknown", {**base, "node_ref": "999999"}, "UNKNOWN_NODE_REF")
    envelope = probe.expect_error("preview_lines below bound (-1)", {**base, "preview_lines": -1}, "HANDLER_ERROR")
    probe.findings.append(
        "WRONG ERROR CLASS: preview_lines=-1 is a parameter-validation failure but is reported as "
        f"HANDLER_ERROR ({error_message(envelope)!r}), the code documented as 'unexpected failure "
        "inside preview orchestration'; VALIDATION_ERROR is the declared case for this."
    )
    probe.expect_error("preview_offset > 0 on a parseable file", {**base, "preview_offset": 2}, "REQUIRES_IDENTIFIER_ADDRESSING")
    envelope = probe.expect_error("tree_id together with session_id", {**base, "tree_id": str(uuid.uuid4())}, "CONFLICTING_PARAMETERS")
    details = (envelope.get("result") or {}).get("error", {}).get("data")
    probe.want(
        isinstance(details, Mapping) and {"session_id", "tree_id", "session_tree_id"} <= set(details),
        "CONFLICTING_PARAMETERS: error data must name session_id, tree_id and session_tree_id",
    )


def _fallback_matrix(probe: _Probe, base: Dict[str, Any]) -> None:
    """The line-based fallback mode reached through a file with parse errors."""
    total = len(BROKEN_SOURCE.splitlines())
    data = probe.expect_success("invalid file, baseline", base)
    if data:
        probe.assert_fallback("invalid baseline", data, offset=0, total=total)
    data = probe.expect_success("invalid file, preview_offset=1", {**base, "preview_offset": 1})
    if data:
        probe.assert_fallback("invalid preview_offset=1", data, offset=1, total=total)
    data = probe.expect_success("invalid file, max_chars=8", {**base, "max_chars": 8})
    if data:
        focus = data.get("focus") or {}
        probe.want(focus.get("is_invalid") is True, "invalid max_chars: focus.is_invalid must stay True")
        probe.want(
            len(focus.get("text") or "") <= 9,
            "invalid max_chars=8: focus.text must be capped (a truncation marker may be appended)",
        )
    data = probe.expect_success("invalid file, preview_lines=1", {**base, "preview_lines": 1})
    if data:
        attributes = (data.get("focus") or {}).get("attributes") or {}
        for field, expected in (("preview_lines_returned", 1), ("preview_has_more", True), ("preview_next_offset", 1)):
            probe.want(
                attributes.get(field) == expected,
                f"invalid preview_lines=1: {field} was {attributes.get(field)!r}, expected {expected!r}",
            )
    probe.expect_error("invalid file with node_ref", {**base, "node_ref": "0"}, "REQUIRES_LINE_ADDRESSING")
    probe.expect_error("invalid file with selector", {**base, "selector": "0:1"}, "REQUIRES_LINE_ADDRESSING")


def _negative_matrix(probe: _Probe, base: Dict[str, Any], unknown_ext: str, session_id: str) -> None:
    """Session identity, one-shot routing, omitted/empty/wrong-typed parameters."""
    probe.expect_error(
        "unknown extension in the workspace",
        {"project_id": SANDBOX_PROJECT, "file_path": unknown_ext, "session_id": session_id},
        "UNKNOWN_EXTENSION",
    )
    probe.expect_error("unknown session", {**base, "session_id": str(uuid.uuid4())}, "SESSION_NOT_FOUND")
    one_shot = {"project_id": SANDBOX_PROJECT, "file_path": base["file_path"]}
    envelope = probe.expect_error("empty session_id", {**base, "session_id": ""}, "OPEN_FILE_USE_WORKSPACE_PREVIEW")
    probe.findings.append(
        "EMPTY VALUE ACCEPTED: an empty session_id is treated as an omitted session_id and falls "
        f"through to the one-shot path ({error_code(envelope)!r}) instead of failing SessionGuard."
    )
    probe.expect_error("session_id absent for an open file", one_shot, "OPEN_FILE_USE_WORKSPACE_PREVIEW")
    probe.expect_error(
        "tree_id alone for an open file",
        {**one_shot, "tree_id": str(uuid.uuid4())},
        "OPEN_FILE_USE_WORKSPACE_PREVIEW",
    )
    probe.expect_error(
        "one-shot preview of a missing file",
        {"project_id": SANDBOX_PROJECT, "file_path": f"no_such_{uuid.uuid4().hex[:8]}.py"},
        "UPSTREAM_ERROR",
    )
    envelope = probe.call("one-shot preview of an EXISTING file", {**one_shot, "file_path": EXISTING_FILE})
    if is_success(envelope):
        probe.assert_structural("one-shot existing", data_of(envelope))
    else:
        probe.want(
            error_code(envelope) == "HANDLER_ERROR",
            f"one-shot existing: expected HANDLER_ERROR, got {error_code(envelope)!r}",
        )
        probe.findings.append(
            f"BROKEN ONE-SHOT PATH: preview of the existing file {EXISTING_FILE!r} without a "
            f"session_id fails with HANDLER_ERROR: {error_message(envelope)!r}. The upstream Code "
            "Analysis download_without_lock returns HTTP 500, so the documented one-shot preview "
            "path cannot be exercised end to end on this deployment."
        )
    for name in ("file_path", "project_id"):
        probe.expect_error(f"empty {name!r}", {**base, name: ""}, "VALIDATION_ERROR")
        probe.expect_error(f"omit required {name!r}", {k: v for k, v in base.items() if k != name}, -32603)
    probe.expect_error("unknown parameter", {**base, "not_a_parameter": 1}, -32603)
    # Every declared parameter, given the wrong JSON type.
    for name, wrong in (
        ("preview_lines", "many"),
        ("value_preview_len", "x"),
        ("full_text_max_lines", "x"),
        ("max_chars", "x"),
        ("preview_offset", "x"),
        ("node_ref", 1),
        ("tree_id", 1),
        ("selector", 1),
    ):
        probe.expect_error(f"{name} with the wrong type ({type(wrong).__name__})", {**base, name: wrong}, -32603)


def _selector_type_finding(probe: _Probe, schema: Any) -> None:
    """The parameter table and the command's own JSON schema disagree on selector.

    Both halves come from the same live ``help(cmdname=...)`` reply."""
    declared = schema.parameters.get("selector")
    published = data_of(probe.client.call("help", {"cmdname": COMMAND})).get("schema") or {}
    forms = ((published.get("properties") or {}).get("selector") or {}).get("oneOf")
    if declared is not None and declared.type == "string" and isinstance(forms, list):
        kinds = [form.get("type") for form in forms if isinstance(form, Mapping)]
        probe.findings.append(
            "SCHEMA DISAGREEMENT: the parameter table declares selector type='string' while the "
            f"command's own JSON schema declares oneOf{kinds}; the array form really works, so the "
            "parameter table under-declares the parameter."
        )


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    probe = _Probe(client, coverage)
    unique = uuid.uuid4().hex[:8]
    good, broken, unknown_ext = (
        f"live_preview_{unique}.py",
        f"live_preview_broken_{unique}.py",
        f"live_preview_{unique}.zzz",
    )
    with CaSession.acquire("ai-editor live check-live-preview") as session:
        try:
            _open(client, session.session_id, good, VALID_SOURCE, probe.log)
            _open(client, session.session_id, broken, BROKEN_SOURCE, probe.log)
            _open(client, session.session_id, unknown_ext, PLAIN_SOURCE, probe.log, format_group="text")
            base = {"project_id": SANDBOX_PROJECT, "file_path": good, "session_id": session.session_id}
            _structural_matrix(probe, base)
            _fallback_matrix(probe, {**base, "file_path": broken})
            _negative_matrix(probe, base, unknown_ext, session.session_id)
            _selector_type_finding(probe, schema)
        finally:
            for name in (good, broken, unknown_ext):
                envelope = client.call(
                    "universal_file_close",
                    {"project_id": SANDBOX_PROJECT, "session_id": session.session_id, "file_path": name},
                )
                probe.log.append(
                    f"  cleanup close {name}: {'ok' if is_success(envelope) else error_code(envelope)!r}"
                )

    report = coverage.report()
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


def check_live_preview(endpoint: Optional[Any] = None) -> CheckResult:
    """Run the whole ``universal_file_preview`` matrix against the deployed server."""
    return run_live_check(_body, endpoint)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_preview)
