"""Live full-surface acceptance check for ``universal_file_edit``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Drives the REAL deployed ai-editor server over mTLS: nothing is mocked,
stubbed or replayed. Every case creates a real Code Analysis session, opens a
real draft in the ``editor_test`` sandbox project (never the live ai-editor
project -- this command mutates), sends real edit batches, and probes the
Code Analysis host with ``transfer_download_begin`` for the target file's
real size and SHA-256. The declared surface comes from
``help(cmdname="universal_file_edit")`` on the server itself and the
exercised surface accumulates in a :class:`CommandCoverage`, so a parameter
or error case added later surfaces as an untested remainder, not a silent
pass. Asserted per ``laws.live_api_contract_coverage``: every declared
parameter in both directions, every operation type across all three format
groups plus the ``is_invalid`` parse-error fallback, the exact stable error
code of every negative case, and the response shape property by property.
Two invariants outrank the rest and are re-asserted after every case: a
rejected batch leaves the draft byte-identical (no half-applied operation),
and the file on the Code Analysis host never changes. Cases asserting the
DOCUMENTED contract that fail on the deployed 1.0.84 keep asserting it on
purpose: this check is their reproduction gate. Cleanup is unconditional and
an unreachable server is RED, never a skip.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pipeline import registry
from pipeline.live.client import (CA_ENV_PREFIX, DEFAULT_CA_HOST, DEFAULT_CA_PORT,
                                  CommandCoverage, LiveClient, LiveEndpoint, data_of,
                                  error_code, error_of, is_success)
from pipeline.registry import CheckResult

CHECK_NAME = "live-edit"
CHECK_DESCRIPTION = "Live full-surface check for universal_file_edit on the deployed server."
COMMAND = "universal_file_edit"

# Destructive commands run ONLY against the editor_test sandbox project.
PROJECT_ID = "99d60878-53d0-42c0-a06e-41e4782b75e7"
SANDBOX_DIR = "pipeline_live_edit"

PY_SRC = ('"""Probe module."""\n\n\ndef alpha() -> int:\n    """Return one."""\n    return 1\n'
          '\n\ndef beta() -> int:\n    """Return two."""\n    return 2\n')
JSON_SRC = '{\n  "name": "probe",\n  "timeout": 30\n}\n'
TXT_SRC = "line one\nline two\nline three\n"
BROKEN_SRC = "def broken(:\n    this is not python\n  ???\n"
ALPHA_LINES = ["def alpha() -> int:", '    """Return one."""', "    return 11"]
GAMMA_LINES = ["", "", "def gamma() -> int:", '    """Return three."""', "    return 3"]


class _Sandbox:
    """Owns every live resource a case needs and guarantees its removal."""

    def __init__(self) -> None:
        self.ed = LiveClient()
        self.ca = LiveClient(LiveEndpoint.from_env(prefix=CA_ENV_PREFIX,
                                                   default_host=DEFAULT_CA_HOST,
                                                   default_port=DEFAULT_CA_PORT))
        self.run, self.root = uuid.uuid4().hex[:8], self._project_root()
        self.sessions: List[str] = []
        self.paths: List[str] = []

    def _project_root(self) -> str:
        """Absolute sandbox root, resolved from the server rather than hard-coded."""
        items = data_of(self.ca.call("list_project_files",
                                     {"project_id": PROJECT_ID, "page_size": 1})).get("items")
        if not items:
            raise RuntimeError(f"sandbox project {PROJECT_ID} lists no files")
        path, rel = str(items[0]["path"]), str(items[0]["relative_path"])
        if not path.endswith(rel):
            raise RuntimeError(f"cannot derive project root from {path!r}/{rel!r}")
        return path[: -len(rel)].rstrip("/")

    def session(self) -> str:
        """Create a real CA session and remember it for teardown."""
        env = self.ca.call("session_create", {"comment": f"pipeline {CHECK_NAME} {self.run}"})
        sid = data_of(env).get("session_id")
        if not is_success(env) or not isinstance(sid, str) or not sid:
            raise RuntimeError(f"CA session_create failed: {error_of(env) or env!r}")
        self.sessions.append(sid)
        return sid

    def path(self, name: str) -> str:
        """A unique sandbox-relative path, remembered for removal."""
        self.paths.append(f"{SANDBOX_DIR}/{self.run}_{name}")
        return self.paths[-1]

    def draft(self, name: str, content: str) -> Tuple[str, str, Dict[str, Any]]:
        """Create a session plus a fresh draft; return (session_id, path, open data)."""
        sid, rel = self.session(), self.path(name)
        env = self.ed.call("universal_file_open", {"project_id": PROJECT_ID, "file_path": rel,
                                                   "session_id": sid, "create": True,
                                                   "initial_content": content})
        if not is_success(env):
            raise RuntimeError(f"universal_file_open {rel} failed: {error_of(env)!r}")
        return sid, rel, data_of(env)

    def exported(self, sid: str, rel: str) -> str:
        """The draft's canonical export as a diff vs origin (empty when identical)."""
        env = self.ed.call("universal_file_write", {"project_id": PROJECT_ID, "file_path": rel,
                                                    "session_id": sid, "write_mode": "preview"})
        return str(data_of(env).get("diff", "")) if is_success(env) else f"<{error_code(env)}>"

    def disk(self, rel: str) -> Optional[Tuple[Any, Any]]:
        """(size_bytes, sha256) of the real file on the Code Analysis host, else None."""
        env = self.ca.call("transfer_download_begin", {"source_path": f"{self.root}/{rel}",
                                                       "filename": "probe",
                                                       "compression": "identity"})
        got = data_of(env)
        return (got.get("size_bytes"), got.get("checksum_value")) if is_success(env) else None

    def dispose(self) -> None:
        """Close every draft, delete every CA session, remove every sandbox file."""
        calls = [(self.ed, "universal_file_close", {"project_id": PROJECT_ID, "session_id": s})
                 for s in self.sessions]
        calls += [(self.ca, "session_delete", {"session_id": s, "force": True})
                  for s in self.sessions]
        calls += [(self.ca, "fs_remove", {"project_id": PROJECT_ID, "file_path": f,
                                          "backup": False}) for f in self.paths]
        for client, command, params in calls:
            try:
                client.call(command, params)
            except Exception:  # noqa: BLE001 - teardown must never mask a verdict
                pass
        self.ed.close()
        self.ca.close()


class _Report:
    """Accumulates one pass/fail row per asserted case."""

    def __init__(self) -> None:
        self.rows: List[Tuple[str, bool, str]] = []

    def expect(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        return bool(ok)

    def format(self) -> str:
        return "\n".join(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" -- {d}" if d else "")
                         for n, ok, d in self.rows)


def _edit(sandbox: _Sandbox, coverage: CommandCoverage,
          params: Mapping[str, Any]) -> Dict[str, Any]:
    """One real ``universal_file_edit`` call, recorded against the declared surface."""
    envelope = sandbox.ed.call(COMMAND, params)
    coverage.record_call(params, envelope)
    return envelope


def _why(env: Mapping[str, Any]) -> str:
    """Everything a failed assertion needs to be actionable, in one line."""
    return (f"success={is_success(env)} code={error_code(env)!r} "
            f"message={(error_of(env) or {}).get('message', '')[:110]!r} "
            f"data={data_of(env)!r}"[:320])


def _rejected(report: _Report, label: str, envelope: Mapping[str, Any], expected: Any,
              before: str, after: str) -> None:
    """A rejection carries the exact stable code AND leaves the draft untouched.

    ``expected`` is None where the contract fixes no code, so only the
    rejection itself and the draft's integrity are asserted."""
    why = _why(envelope)
    if expected is None:
        report.expect(f"{label}: rejected", not is_success(envelope), why)
    else:
        report.expect(f"{label}: code {expected} and no data payload",
                      error_code(envelope) == expected and data_of(envelope) == {}, why)
    report.expect(f"{label}: draft not half-applied", before == after,
                  f"before={before[:150]!r} after={after[:150]!r}")


def _applied(report: _Report, label: str, envelope: Mapping[str, Any],
             updated: Optional[bool] = None, lines: Optional[int] = None) -> None:
    """A success carries exactly the documented data properties, with their types."""
    payload, why = data_of(envelope), _why(envelope)
    report.expect(f"{label}: success with data.success True",
                  is_success(envelope) and payload.get("success") is True, why)
    if updated is not None:
        report.expect(f"{label}: data.updated is {updated}, no line_count",
                      payload.get("updated") is updated and "line_count" not in payload, why)
    if lines is not None:
        report.expect(f"{label}: data.line_count == {lines} (int), no updated flag",
                      isinstance(payload.get("line_count"), int) and payload["line_count"] == lines
                      and "updated" not in payload, why)


def _refs(sandbox: _Sandbox, sid: str, rel: str) -> List[Tuple[Any, str]]:
    """(node_ref, type) for every top-level preview block of the current draft."""
    env = sandbox.ed.call("universal_file_preview", {"project_id": PROJECT_ID, "file_path": rel,
                                                     "session_id": sid})
    return [(b.get("node_ref"), b.get("summary", {}).get("type"))
            for b in data_of(env).get("blocks", [])]


def _ln(kind: str, start: int, **extra: Any) -> Dict[str, Any]:
    """One single-line operation, the shape the text handler documents."""
    return dict({"type": kind, "start_line": start, "end_line": start}, **extra)


def _negatives(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report, base: Dict[str, Any],
               sid: str, rel: str, cases: Sequence[Tuple[str, Any, Any]]) -> None:
    """Run rejection cases, re-reading the draft around each one."""
    for label, operations, expected in cases:
        before = sandbox.exported(sid, rel)
        _rejected(report, label, _edit(sandbox, coverage, dict(base, operations=operations)),
                  expected, before, sandbox.exported(sid, rel))


def _case_sidecar(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Python (.py) -> format_group ``sidecar``: replace, insert, delete by node id."""
    sid, rel, opened = sandbox.draft("sidecar.py", PY_SRC)
    report.expect("sidecar: opened as sidecar", opened.get("format_group") == "sidecar",
                  f"format_group={opened.get('format_group')!r}")
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    refs = _refs(sandbox, sid, rel)
    functions = [ref for ref, kind in refs if kind == "function"]
    if not report.expect("sidecar: two function refs from preview", len(functions) == 2, f"{refs!r}"):
        return
    _applied(report, "sidecar replace", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "replace", "node_id": str(functions[0]), "code_lines": ALPHA_LINES}])),
        updated=True)
    _applied(report, "sidecar insert sibling", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "insert", "target_node_id": str(functions[1]), "position": "after",
         "code_lines": GAMMA_LINES}])), updated=True)
    _applied(report, "sidecar delete", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "delete", "node_id": str(functions[1])}])), updated=True)
    diff = sandbox.exported(sid, rel)
    want = ("+    return 11", "-def beta() -> int:", "+def gamma() -> int:")
    report.expect("sidecar draft carries every applied change", all(f in diff for f in want),
                  f"{diff[:300]!r}")
    report.expect("sidecar: edit never touches the file on disk", sandbox.disk(rel) is None,
                  f"CA host reports (size, sha256)={sandbox.disk(rel)!r}")
    _negatives(sandbox, coverage, report, base, sid, rel, (
        ("sidecar unknown type", [{"type": "frobnicate", "node_id": str(functions[0]),
                                   "code_lines": ["x = 1"]}], "INVALID_OPERATION"),
        ("sidecar stale node_id", [{"type": "replace", "node_id": "9" * 6,
                                    "code_lines": ["x = 1"]}], "STALE_NODE_ID"),
        ("sidecar line range refused", [_ln("replace", 1, content="x")], "INVALID_OPERATION"),
        ("sidecar move without ref", [{"type": "move", "position": "last"}],
         "INVALID_OPERATION")))


def _case_tree_temp(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """JSON -> format_group ``tree-temp``: replace, insert, delete by JSON Pointer."""
    sid, rel, opened = sandbox.draft("tree.json", JSON_SRC)
    report.expect("tree-temp: opened as tree-temp", opened.get("format_group") == "tree-temp",
                  f"format_group={opened.get('format_group')!r}")
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    _applied(report, "tree-temp replace", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "replace", "json_pointer": "/timeout", "value": 60}])), updated=True)
    _applied(report, "tree-temp insert", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "insert", "parent_json_pointer": "", "key": "added", "value": "yes"}])),
        updated=True)
    _applied(report, "tree-temp delete", _edit(sandbox, coverage, dict(base, operations=[
        {"type": "delete", "json_pointer": "/name"}])), updated=True)
    _negatives(sandbox, coverage, report, base, sid, rel, (
        ("tree-temp unknown pointer", [{"type": "replace", "json_pointer": "/nope", "value": 1}],
         "INVALID_OPERATION"),))
    # help() names an int short_id in node_ref the PREFERRED marked-tree address.
    scalar = next((r for r, kind in _refs(sandbox, sid, rel) if kind == "scalar"), None)
    envelope = _edit(sandbox, coverage, dict(base, operations=[
        {"type": "replace", "node_ref": str(scalar), "value": 90}]))
    report.expect("tree-temp: preview node_ref accepted by edit", is_success(envelope),
                  f"node_ref={scalar!r} -> {_why(envelope)}")
    report.expect("tree-temp: edit never touches the file on disk", sandbox.disk(rel) is None,
                  f"CA host reports (size, sha256)={sandbox.disk(rel)!r}")


def _case_text(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Plain text -> format_group ``text``: line ranges, node_ref, anchors."""
    sid, rel, opened = sandbox.draft("plain.txt", TXT_SRC)
    report.expect("text: opened as text", opened.get("format_group") == "text",
                  f"format_group={opened.get('format_group')!r}")
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    for label, operations, lines in (
        ("text replace range", [_ln("replace", 2, content="TWO")], 3),
        ("text insert last", [{"type": "insert", "position": "last", "content": "appended"}], 4),
        ("text delete range", [_ln("delete", 1)], 3),
        ("text anchored replace", [_ln("replace", 1, content="SECOND", anchor_head="TWO",
                                       anchor_tail="TWO")], 3),
        ("text replace by node_ref", [{"type": "replace", "node_ref": "1", "content": "F"}], 3),
        ("text empty batch is a no-op", [], 3),
    ):
        _applied(report, label, _edit(sandbox, coverage, dict(base, operations=operations)),
                 lines=lines)
    report.expect("text: edit never touches the file on disk", sandbox.disk(rel) is None,
                  f"CA host reports (size, sha256)={sandbox.disk(rel)!r}")
    _negatives(sandbox, coverage, report, base, sid, rel, (
        ("text line beyond end", [_ln("replace", 99, content="z")], "LINE_OUT_OF_RANGE"),
        ("text line zero", [_ln("replace", 0, content="z")], "LINE_OUT_OF_RANGE"),
        ("text line negative", [_ln("replace", -1, content="z")], "LINE_OUT_OF_RANGE"),
        ("text anchor mismatch", [_ln("replace", 1, content="w", anchor_head="ZZZZZ",
                                      anchor_tail="ZZZZZ")], "ANCHOR_MISMATCH"),
        ("text unknown node_ref slug", [{"type": "replace", "node_ref": "nope", "content": "q"}],
         "UNKNOWN_NODE_REF"),
        ("text unknown node_ref index", [{"type": "replace", "node_ref": "99", "content": "q"}],
         "UNKNOWN_NODE_REF"),
        ("text unknown operation type", [_ln("frobnicate", 1, content="w")],
         "INVALID_OPERATION")))


def _case_fallback(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Parse-error fallback (``is_invalid``): the documented guards must still hold."""
    for label, operations, expected in (
        ("fallback line beyond end", [_ln("replace", 99, content="z = 3")], "LINE_OUT_OF_RANGE"),
        ("fallback anchor mismatch", [_ln("replace", 1, content="w", anchor_head="ZZZZZ",
                                          anchor_tail="ZZZZZ")], "ANCHOR_MISMATCH"),
        ("fallback unknown operation type", [_ln("frobnicate", 1, content="w")],
         "INVALID_OPERATION"),
        ("fallback node op forbidden", [{"type": "replace", "node_id": "1",
                                         "code_lines": ["x = 1"]}], "INVALID_OPERATION"),
        ("fallback unknown node_ref", [{"type": "replace", "node_ref": "nope", "content": "q"}],
         "UNKNOWN_NODE_REF"),
    ):
        sid, rel, opened = sandbox.draft(f"fallback{len(sandbox.paths)}.py", BROKEN_SRC)
        report.expect(f"{label}: opened in fallback", opened.get("is_invalid") is True,
                      f"is_invalid={opened.get('is_invalid')!r}")
        base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
        _negatives(sandbox, coverage, report, base, sid, rel, ((label, operations, expected),))


def _case_scope(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Session scope and the per-parameter negative matrix, on one shared draft."""
    sid, rel, _ = sandbox.draft("scope.txt", TXT_SRC)
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    ops = [_ln("replace", 1, content="X")]
    # project_id is a REQUIRED project UUID: an empty or foreign one must not reach this draft.
    for label, expected, params in (
        ("unknown session", "SESSION_NOT_FOUND", dict(base, operations=ops,
                                                      session_id=str(uuid.uuid4()))),
        ("empty session_id", "SESSION_NOT_FOUND", dict(base, session_id="", operations=ops)),
        ("file_path not open in session", "SESSION_NOT_FOUND",
         dict(base, file_path=f"{SANDBOX_DIR}/never_opened.txt", operations=ops)),
        ("project_id omitted", None, {"file_path": rel, "session_id": sid, "operations": ops}),
        ("session_id omitted", None, {"project_id": PROJECT_ID, "file_path": rel, "operations": ops}),
        ("operations omitted", None, dict(base)),
        ("operations wrong type", None, dict(base, operations="notalist")),
        ("project_id wrong type", None, dict(base, project_id=123, operations=ops)),
        ("file_path wrong type", None, dict(base, file_path=7, operations=ops)),
        ("unknown extra parameter", None, dict(base, operations=ops, bogus=1)),
        ("empty project_id", "VALIDATION_ERROR", dict(base, project_id="", operations=ops)),
        ("foreign project_id", "VALIDATION_ERROR", dict(base, operations=ops,
                                                         project_id=str(uuid.uuid4()))),
    ):
        before = sandbox.exported(sid, rel)
        _rejected(report, label, _edit(sandbox, coverage, params), expected, before,
                  sandbox.exported(sid, rel))
    # file_path is optional while exactly one file is open, required once two are.
    _applied(report, "file_path omitted with one open file",
             _edit(sandbox, coverage, {"project_id": PROJECT_ID, "session_id": sid,
                                       "operations": []}), lines=3)
    opened = sandbox.ed.call("universal_file_open", {
        "project_id": PROJECT_ID, "file_path": sandbox.path("scope_second.txt"),
        "session_id": sid, "create": True, "initial_content": TXT_SRC})
    report.expect("second file opened in the same session", is_success(opened), _why(opened))
    before = sandbox.exported(sid, rel)
    _rejected(report, "multi-file session without file_path",
              _edit(sandbox, coverage, {"project_id": PROJECT_ID, "session_id": sid,
                                        "operations": ops}), "SESSION_FILE_PATH_REQUIRED",
              before, sandbox.exported(sid, rel))


_CASES = (("sidecar_python", _case_sidecar), ("tree_temp_json", _case_tree_temp),
          ("text_lines", _case_text), ("parse_error_fallback", _case_fallback),
          ("session_and_parameter_scope", _case_scope))


def check_live_edit() -> CheckResult:
    """Drive the whole declared surface of ``universal_file_edit``; one verdict."""
    report, sandbox, sections = _Report(), None, []
    try:
        sandbox = _Sandbox()
        coverage = CommandCoverage(sandbox.ed.command_schema(COMMAND))
        sections.append(coverage.schema.format_declared_surface())
        for name, case in _CASES:
            try:
                case(sandbox, coverage, report)
            except Exception as exc:  # noqa: BLE001 - a broken case must not hide the rest
                report.expect(f"{name}: case completed", False, f"{type(exc).__name__}: {exc}")
        sections.append(coverage.report().format())
    except Exception as exc:  # noqa: BLE001 - an unreachable server is RED, never a skip
        report.expect("live server reachable", False, f"{type(exc).__name__}: {exc}")
    finally:
        if sandbox is not None:
            sandbox.dispose()
    output = "\n".join([report.format(), *sections])
    total = len(report.rows)
    failed = sum(1 for row in report.rows if not row[1])
    message = f"{failed or total}/{total} {COMMAND} assertion(s) {'failed' if failed else 'passed'}"
    return (CheckResult.fail if failed else CheckResult.ok)(message=message, output=output)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_edit)
