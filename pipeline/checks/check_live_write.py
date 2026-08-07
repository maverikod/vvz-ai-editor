"""Live full-surface acceptance check for ``universal_file_write``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Drives the REAL deployed ai-editor server over mTLS: nothing is mocked or
replayed. Every case creates a real Code Analysis session, opens a real draft
in the ``editor_test`` sandbox project (never the live ai-editor project --
this command persists), and reads the file back off the Code Analysis host as
REAL BYTES via ``transfer_download_begin`` plus a real chunk GET, so every
fidelity claim here is a byte comparison, not a "success" flag. The declared
surface comes from ``help(cmdname="universal_file_write")`` on the server and
the exercised surface accumulates in a :class:`CommandCoverage`. Asserted per
``laws.live_api_contract_coverage``: both values of the ``write_mode`` enum
and of ``format_python`` and ``verify_after_upload``, every parameter present
and absent, the negative matrix (omitted, empty, wrong type, unknown extra),
the exact stable error code of every negative case, and the response shape
property by property. Three invariants outrank the rest: preview produces a
diff and changes NOTHING on disk; commit writes exactly the intended bytes
and nothing else; and a commit never loses content the caller did not touch.
Contract cases that fail on 1.0.84 keep asserting it, so the check is their
reproduction gate; an unreachable server is RED.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pipeline import registry
from pipeline.live.client import (CA_ENV_PREFIX, DEFAULT_CA_HOST, DEFAULT_CA_PORT,
                                  CommandCoverage, LiveClient, LiveEndpoint, data_of,
                                  error_code, error_of, is_success)
from pipeline.registry import CheckResult

CHECK_NAME = "live-write"
CHECK_DESCRIPTION = "Live full-surface check for universal_file_write on the deployed server."
COMMAND = "universal_file_write"

# Destructive commands run ONLY against the editor_test sandbox project.
PROJECT_ID = "99d60878-53d0-42c0-a06e-41e4782b75e7"
SANDBOX_DIR = "pipeline_live_write"

TXT_SRC = "alpha\nbeta\ngamma\n"
CRLF_SRC = "alpha\r\nbeta\r\ngamma\r\n"
NOEOL_SRC = "alpha\nbeta\nno trailing newline"
CYRILLIC_SRC = "Привет\nмир\n"  # UTF-8 fixture
BAD_PY_SRC = "def broken(:\n    this is not python\n  ???\n"
BAD_TOML_SRC = "name = 1\nvalue = 2\n[bad\nkeep = 3\n"
BETA_OP = {"type": "replace", "start_line": 2, "end_line": 2, "content": "BETA"}  # line 2
UGLY_PY_SRC = '"""Module."""\n\n\ndef f(a, b):\n    """Add.\n\n    Returns:\n        int: sum.\n' \
              '    """\n    return  a+b\n'
NODOC_PY_SRC = '"""Module."""\n\n\ndef f() -> int:\n    """No return description."""\n    return 1\n'


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
        return self.paths[-1]  # noqa

    def draft(self, name: str, content: str) -> Tuple[str, str, Dict[str, Any]]:
        """Create a session plus a fresh draft; return (session_id, path, open data)."""
        sid, rel = self.session(), self.path(name)
        return sid, rel, self.open(sid, rel, create=True, initial_content=content)

    def open(self, sid: str, rel: str, **extra: Any) -> Dict[str, Any]:
        """Open one file into an existing session, raising when the server refuses."""
        env = self.ed.call("universal_file_open", dict(
            {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}, **extra))
        if not is_success(env):
            raise RuntimeError(f"open {rel} failed: {error_of(env)!r}")
        return data_of(env)

    def edit(self, sid: str, rel: str, ops: Any) -> Dict[str, Any]:
        """Apply an edit batch to a draft; the batch itself is check_live_edit's subject."""
        return self.ed.call("universal_file_edit", {"project_id": PROJECT_ID, "file_path": rel,
                                                    "session_id": sid, "operations": ops})

    def disk(self, rel: str) -> Optional[bytes]:
        """The REAL bytes of the file on the Code Analysis host, or None when absent."""
        import httpx

        env = self.ca.call("transfer_download_begin", {"source_path": f"{self.root}/{rel}",
                                                       "filename": "probe",
                                                       "compression": "identity"})
        if not is_success(env):
            return None
        got, point = data_of(env), self.ca.endpoint
        url = (f"{point.protocol}://{point.host}:{point.port}"
               + got["transport"]["chunk_path_template"].format(transfer_id=got["transfer_id"],
                                                                offset=0, limit=8 << 20))
        context = httpx.create_ssl_context(verify=point.ca_cert, cert=(point.cert, point.key))
        context.check_hostname = False
        with httpx.Client(verify=context, timeout=point.timeout) as client:
            return client.get(url).content

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
        return "\n".join(f"  [{'PASS' if ok else 'FAIL'}] {n}"
                         + (f" -- {d}" if d else "") for n, ok, d in self.rows)


def _write(sandbox: _Sandbox, coverage: CommandCoverage, params: Mapping[str, Any]) -> Dict:
    """One real ``universal_file_write`` call, recorded against the declared surface."""
    env = sandbox.ed.call(COMMAND, params)
    coverage.record_call(params, env)
    return env


def _why(env: Mapping[str, Any]) -> str:
    """Everything a failed assertion needs to be actionable, in one line."""
    return (f"success={is_success(env)} code={error_code(env)!r} "
            f"message={(error_of(env) or {}).get('message', '')[:110]!r} "
            f"data={data_of(env)!r}"[:340])


def _payload(report: _Report, label: str, env: Mapping[str, Any],
             expected: Mapping[str, Any]) -> Dict[str, Any]:
    """Assert a successful write's documented properties, values and types: the table
    below is what ``return_value`` promises on EVERY successful write, whatever the
    mode; the caller pins down the values it knows."""
    got, why = data_of(env), _why(env)
    report.expect(f"{label}: success with data.success True",
                  is_success(env) and got.get("success") is True, why)
    for name, value in expected.items():
        report.expect(f"{label}: data.{name} == {value!r}", got.get(name) == value, why)
    for name, kind in (("phase", str), ("write_mode", str), ("has_changes", bool),
                       ("unchanged", bool), ("uploaded", bool), ("diff", str),
                       ("format_python", bool), ("session_id", str),
                       ("file_path", str), ("project_id", str)):
        report.expect(f"{label}: data.{name} present, {kind.__name__}",
                      isinstance(got.get(name), kind), why)
    return got


def _diff_shape(report: _Report, label: str, got: Mapping[str, Any], status: str,
                applied: bool) -> None:
    """``preview_diff`` is a documented nested object; assert it property by property."""
    block = got.get("preview_diff")
    if not report.expect(f"{label}: preview_diff is an object",
                         isinstance(block, Mapping), f"preview_diff={block!r}"):
        return
    for name, value in (("status", status), ("content_changed", status == "changed"),
                        ("applied", applied), ("operation", COMMAND)):
        report.expect(f"{label}: preview_diff.{name} == {value!r}", block.get(name) == value,
                      f"preview_diff={block!r}")
    report.expect(f"{label}: preview_diff.diff str, diagnostics list",
                  isinstance(block.get("diff"), str)
                  and isinstance(block.get("diagnostics"), list), f"preview_diff={block!r}")


def _bytes(report: _Report, sandbox: _Sandbox, label: str, rel: str,
           want: Optional[bytes]) -> None:
    """The strongest assertion here: the REAL bytes on the Code Analysis host."""
    got = sandbox.disk(rel)
    report.expect(label, got == want, f"expected={want!r} got={got!r}")


def _rejected(report: _Report, label: str, env: Mapping[str, Any], expected: Any) -> None:
    """The exact stable code, or just a rejection where the contract fixes none."""
    if expected is None:
        report.expect(f"{label}: rejected", not is_success(env), _why(env))
    else:
        report.expect(f"{label}: code {expected} and no data payload",
                      error_code(env) == expected and data_of(env) == {}, _why(env))


def _case_lifecycle(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """One draft through both enum values: preview diffs and touches no file, commit
    lands exactly the intended bytes and nothing else."""
    sid, rel, _ = sandbox.draft("lifecycle.txt", TXT_SRC)
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    got = _payload(report, "unchanged preview",
                   _write(sandbox, coverage, dict(base, write_mode="preview")),
                   {"phase": "preview", "write_mode": "preview", "has_changes": False,
                    "unchanged": True, "uploaded": False, "diff": ""})
    _diff_shape(report, "unchanged preview", got, "no_op", False)
    sandbox.edit(sid, rel, [BETA_OP])
    got = _payload(report, "changed preview",
                   _write(sandbox, coverage, dict(base, write_mode="preview")),
                   {"phase": "preview", "write_mode": "preview", "has_changes": True,
                    "unchanged": False, "uploaded": False})
    _diff_shape(report, "changed preview", got, "changed", False)
    report.expect("preview: diff shows exactly the edited line", "-beta" in got.get("diff", "")
                  and "+BETA" in got.get("diff", ""), f"diff={got.get('diff')!r}")
    # write_mode is optional with default "preview"; the omitted call must echo it.
    _payload(report, "preview by default (write_mode omitted)",
             _write(sandbox, coverage, dict(base)),
             {"phase": "preview", "write_mode": "preview", "has_changes": True})
    _bytes(report, sandbox, "preview: nothing was written to the CA host", rel, None)
    expected = b"alpha\nBETA\ngamma\n"
    got = _payload(report, "changed commit",
                   _write(sandbox, coverage, dict(base, write_mode="commit")),
                   {"phase": "committed", "write_mode": "commit", "has_changes": True,
                    "unchanged": False, "uploaded": True, "file_path": rel,
                    "project_id": PROJECT_ID, "session_id": sid})
    _diff_shape(report, "changed commit", got, "changed", True)
    _bytes(report, sandbox, "commit: on-disk bytes are exactly the intended bytes", rel, expected)
    _diff_shape(report, "no-op commit", _payload(
        report, "commit with nothing left to write",
        _write(sandbox, coverage, dict(base, write_mode="commit")),
        {"phase": "committed", "has_changes": False, "unchanged": True, "uploaded": False,
         "diff": ""}), "no_op", False)
    _bytes(report, sandbox, "no-op commit: on-disk bytes are untouched", rel, expected)
    off = data_of(_write(sandbox, coverage, dict(base, write_mode="commit",
                                                 verify_after_upload=False)))
    report.expect("verify_after_upload=False carries no ca_verify",
                  "ca_verify" not in off, f"data={off!r:.200}")
    sandbox.edit(sid, rel, [{"type": "insert", "position": "last", "content": "delta"}])
    expected = b"alpha\nBETA\ngamma\ndelta\n"
    verify = data_of(_write(sandbox, coverage, dict(base, write_mode="commit",
                                                    verify_after_upload=True))).get("ca_verify")
    report.expect("verify_after_upload=True carries a ca_verify object", isinstance(
        verify, Mapping), f"ca_verify={verify!r}")
    if isinstance(verify, Mapping):
        report.expect("ca_verify confirms a read-back of the committed length",
                      verify.get("verified") is True and verify.get("error") is None
                      and verify.get("expected_length") == verify.get("actual_length")
                      == len(expected), f"ca_verify={verify!r} expected={len(expected)}")
    _bytes(report, sandbox, "append commit: on-disk bytes are exact", rel, expected)


def _case_fidelity(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Awkward bytes survive a commit unchanged (CRLF, no trailing newline, UTF-8);
    a commit never loses on-disk content the caller never addressed."""
    for name, source in (("crlf.txt", CRLF_SRC), ("noeol.txt", NOEOL_SRC),
                         ("cyrillic.txt", CYRILLIC_SRC)):
        sid, rel, _ = sandbox.draft(name, source)
        base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
        expected, prev = source.encode(), _write(sandbox, coverage,
                                                 dict(base, write_mode="preview"))
        report.expect(f"{name}: an untouched draft previews as unchanged",
                      data_of(prev).get("has_changes") is False
                      and data_of(prev).get("diff") == "", _why(prev))
        _write(sandbox, coverage, dict(base, write_mode="commit"))
        _bytes(report, sandbox, f"{name}: committed bytes are byte-identical to the source",
               rel, expected)
    sid, rel, opened = sandbox.draft("damage.toml", BAD_TOML_SRC)
    report.expect("damage: the unparseable file opens in line-based fallback",
                  opened.get("is_invalid") is True, f"opened={opened!r:.200}")
    _write(sandbox, coverage, {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid,
                               "write_mode": "commit"})
    planted = BAD_TOML_SRC.encode()
    _bytes(report, sandbox, "damage: the fixture landed on the CA host verbatim", rel, planted)
    sandbox.ed.call("universal_file_close", {"project_id": PROJECT_ID, "session_id": sid})
    sid = sandbox.session()      # reopen the REAL on-disk file in a fresh session
    sandbox.open(sid, rel)
    sandbox.edit(sid, rel, [{"type": "replace", "start_line": 400, "end_line": 400,
                             "content": "oops = 9"}])
    _write(sandbox, coverage, {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid,
                               "write_mode": "commit"})
    _bytes(report, sandbox, "damage: an out-of-range edit must not reach the file on disk",
           rel, planted)


def _case_errors(sandbox: _Sandbox, coverage: CommandCoverage, report: _Report) -> None:
    """Documented failure paths (validation, upstream refusal, multi-file sessions),
    then the per-parameter negative matrix."""
    sid, rel, _ = sandbox.draft("novalidate.py", NODOC_PY_SRC)
    _rejected(report, "commit of a file failing pre-write validation", _write(sandbox, coverage, {
        "project_id": PROJECT_ID, "file_path": rel, "session_id": sid, "write_mode": "commit"}),
        "VALIDATION_ERROR")
    _bytes(report, sandbox, "VALIDATION_ERROR leaves nothing on the CA host", rel, None)
    sid, rel, _ = sandbox.draft("upstream.py", BAD_PY_SRC)
    _rejected(report, "commit refused upstream by Code Analysis", _write(sandbox, coverage, {
        "project_id": PROJECT_ID, "file_path": rel, "session_id": sid, "write_mode": "commit"}),
        "UPSTREAM_UPLOAD_FAILED")
    _bytes(report, sandbox, "UPSTREAM_UPLOAD_FAILED leaves nothing on the CA host", rel, None)
    sid, rel, _ = sandbox.draft("format.py", UGLY_PY_SRC)
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    # A .py with write_mode omitted takes the sidecar two-phase lockfile path, whose
    # second call commits; both calls therefore pin write_mode explicitly.
    prev = dict(base, write_mode="preview")
    plain = data_of(_write(sandbox, coverage, dict(prev, format_python=False)))
    black = data_of(_write(sandbox, coverage, dict(prev, format_python=True)))
    report.expect("format_python=False leaves the export untouched, True reformats it",
                  plain.get("has_changes") is False and black.get("has_changes") is True
                  and "+    return a + b" in black.get("diff", ""), f"plain="
                  f"{plain.get('has_changes')!r} black_diff={black.get('diff')!r}")
    sid, rel, _ = sandbox.draft("multi_one.txt", TXT_SRC)
    _payload(report, "file_path omitted with one open file",
             _write(sandbox, coverage, {"project_id": PROJECT_ID, "session_id": sid}),
             {"write_mode": "preview", "file_path": rel})
    sandbox.open(sid, sandbox.path("multi_two.txt"), create=True, initial_content=TXT_SRC)
    _rejected(report, "multi-file session without file_path",
              _write(sandbox, coverage, {"project_id": PROJECT_ID, "session_id": sid}),
              "SESSION_FILE_PATH_REQUIRED")
    # Per-parameter negatives. project_id is a REQUIRED project UUID: an empty or
    # foreign one must never be honoured.
    sid, rel, _ = sandbox.draft("params.txt", TXT_SRC)
    base = {"project_id": PROJECT_ID, "file_path": rel, "session_id": sid}
    for label, expected, params in (
        ("unknown session", "SESSION_NOT_FOUND", dict(base, session_id=str(uuid.uuid4()))),
        ("empty session_id", "SESSION_REJECTED", dict(base, session_id="")),
        ("file_path not open in session", "SESSION_NOT_FOUND",
         dict(base, file_path=f"{SANDBOX_DIR}/never_opened.txt")),
        ("project_id omitted", None, {"file_path": rel, "session_id": sid}),
        ("session_id omitted", None, {"project_id": PROJECT_ID, "file_path": rel}),
        ("write_mode out of enum", None, dict(base, write_mode="nonsense")),
        ("write_mode empty", None, dict(base, write_mode="")),
        ("write_mode wrong type", None, dict(base, write_mode=7)),
        ("format_python wrong type", None, dict(base, format_python="yes")),
        ("verify_after_upload wrong type", None, dict(base, verify_after_upload="yes")),
        ("project_id wrong type", None, dict(base, project_id=123)),
        ("file_path wrong type", None, dict(base, file_path=7)),
        ("unknown extra parameter", None, dict(base, bogus=1)),
        ("empty project_id", "VALIDATION_ERROR", dict(base, project_id="")),
        ("foreign project_id", "VALIDATION_ERROR", dict(base, project_id=str(uuid.uuid4()))),
    ):
        _rejected(report, label, _write(sandbox, coverage, params), expected)
    _bytes(report, sandbox, "the parameter matrix wrote nothing to the CA host", rel, None)


_CASES = (("preview_and_commit", _case_lifecycle), ("documented_errors", _case_errors),
          ("byte_fidelity_and_no_silent_damage", _case_fidelity))


def check_live_write() -> CheckResult:
    """Drive the whole declared surface of ``universal_file_write``; one verdict."""
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
    output, total = "\n".join([report.format(), *sections]), len(report.rows)
    failed = sum(1 for row in report.rows if not row[1])
    note = f"{failed or total}/{total} {COMMAND} assertion(s) {'failed' if failed else 'passed'}"
    return (CheckResult.fail if failed else CheckResult.ok)(message=note, output=output)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_write)
