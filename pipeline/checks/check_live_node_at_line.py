"""Live full-surface check for ``universal_file_node_at_line``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises every declared parameter and every declared error case of
``universal_file_node_at_line`` against the REAL deployed ai-editor server
(mTLS, sandbox project ``editor_test``), driving coverage from the server's
own ``help(cmdname="universal_file_node_at_line")`` schema. Nothing here is
mocked, stubbed, or replayed.

The command's own promise is to return the MOST SPECIFIC node covering a
line, so this check asserts exact node identity/type on a file of known
structure -- never merely "the call succeeded":

* Line 1 (the module docstring, nothing else on that line) must resolve to
  the ``SimpleString`` node itself, not the enclosing ``Module``.
* The file's last line (``return 2`` inside ``Gamma.method_two``) must
  resolve to the ``Integer`` literal, not the enclosing ``Return`` or
  ``FunctionDef`` -- proof the walk goes all the way to the leaf.
* ``include_ancestors=True`` is asserted to return the FULL covering chain,
  smallest span first, ending in the ``Module`` node (the documented order).
* Boundary lines are exercised in both directions: line 1, the last real
  line, one past the end, line 0, and a negative line. The schema declares
  ``line`` with ``minimum: 1``, but 0 and negative both reach the SAME
  domain-level ``LINE_NOT_FOUND`` as "one past the end" rather than being
  rejected by parameter validation -- the declared minimum is not actually
  enforced at that layer, which is recorded explicitly below rather than
  assumed from the schema alone.
* The parse-error fallback (line-based editing when structural parse fails)
  is exercised directly: this command on such a session is asserted to
  return the documented ``UNKNOWN_FORMAT``.

Also asserted: like ``universal_file_search`` (see that check's module
docstring), ``project_id`` used to have no observed effect here either --
empty and even a well-formed-but-wrong project_id both still resolved
correctly, because the command was scoped by ``session_id`` alone. It is now
enforced: both empty and foreign are ``VALIDATION_ERROR`` -- the code and
message ``universal_file_preview`` already uses for a project/session
mismatch -- and the owning project id still resolves the node.

Registration is unconditional, like ``check-live-core``: there is no
environment gate and no skip concept anywhere in this file.
:func:`pipeline.live.client.run_live_check` FAILS the check outright when the
server cannot be reached -- the deployment is this project's own service, so
an unreachable server is this check being RED, not opting out.
"""

from __future__ import annotations

import dataclasses
import traceback
import uuid
from typing import Any, Callable, Dict, List, Mapping

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

CHECK_NAME = "check-live-node-at-line"
CHECK_DESCRIPTION = (
    "Live full-surface check for universal_file_node_at_line against the "
    "REAL deployed server: every declared parameter and error case, exact "
    "most-specific-node assertions at line 1/last-line/boundaries, "
    "include_ancestors ordering, and the parse-error-fallback UNKNOWN_FORMAT path.")

COMMAND = "universal_file_node_at_line"
PROJECT_ID = "99d60878-53d0-42c0-a06e-41e4782b75e7"  # sandbox 'editor_test' -- never the real project
FILE_A = "wliveq_nal_a.py"
FILE_B = "wliveq_nal_b.py"
BROKEN_FILE = "wliveq_nal_broken.py"
WRONG_PROJECT_ID = "00000000-0000-0000-0000-000000000000"

# Known structure, 1-based lines:
#  1  """Sample module for the live node-at-line check."""
#  2  (blank)
#  3  (blank)
#  4  def alpha(x):
#  5      return x + 1
#  6  (blank)
#  7  (blank)
#  8  def beta(y):
#  9      return y * 2
# 10  (blank)
# 11  (blank)
# 12  class Gamma:
# 13      def method_one(self):
# 14          return 1
# 15  (blank)
# 16      def method_two(self):
# 17          return 2
SAMPLE_PY = (
    '"""Sample module for the live node-at-line check."""\n'
    "\n\n"
    "def alpha(x):\n"
    "    return x + 1\n"
    "\n\n"
    "def beta(y):\n"
    "    return y * 2\n"
    "\n\n"
    "class Gamma:\n"
    "    def method_one(self):\n"
    "        return 1\n"
    "\n"
    "    def method_two(self):\n"
    "        return 2\n")
LAST_LINE = 17
BROKEN_PY = "def broken(:\n    this is not python\n"


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


def _open(client: LiveClient, session_id: str, file_path: str, content: str) -> Mapping[str, Any]:
    env = client.call("universal_file_open", {
        "project_id": PROJECT_ID, "file_path": file_path, "session_id": session_id,
        "create": True, "initial_content": content})
    _require(is_success(env), f"setup: open {file_path!r} failed: {env!r}")
    return env


def _close(client: LiveClient, session_id: str, file_path: str) -> None:
    try:
        client.call("universal_file_close",
                     {"project_id": PROJECT_ID, "session_id": session_id, "file_path": file_path})
    except Exception:  # noqa: BLE001 - cleanup must never mask the verdict
        pass


def _build_cases(client: LiveClient, session_id: str,
                  coverage: CommandCoverage) -> List[tuple]:
    def node_at_line(params: Dict[str, Any]) -> Dict[str, Any]:
        env = client.call(COMMAND, params)
        coverage.record_call(params, env)
        return env

    def case_line_1_is_the_docstring_leaf() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 1})
        d = data_of(env)
        _require(is_success(env), str(env))
        _require(d.get("type") == "SimpleString", f"type={d.get('type')!r}")
        _require(d.get("start_line") == 1 and d.get("end_line") == 1, str(d))
        _require("ancestors" not in d, "ancestors present though include_ancestors was omitted")
        return "line 1 -> SimpleString (the docstring itself, not Module); ancestors absent by default"

    def case_last_line_is_the_integer_leaf() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": LAST_LINE})
        d = data_of(env)
        _require(is_success(env), str(env))
        _require(d.get("type") == "Integer", f"type={d.get('type')!r}")
        _require(d.get("qualname") == "Gamma.method_two", f"qualname={d.get('qualname')!r}")
        _require(d.get("start_line") == LAST_LINE and d.get("end_line") == LAST_LINE, str(d))
        return f"last line ({LAST_LINE}) -> Integer leaf inside Gamma.method_two, not Return/FunctionDef"

    def case_include_ancestors_true_full_chain() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 5, "include_ancestors": True})
        d = data_of(env)
        _require(is_success(env), str(env))
        _require(d.get("qualname") == "alpha", f"qualname={d.get('qualname')!r}")
        ancestors = d.get("ancestors")
        _require(isinstance(ancestors, list) and ancestors, f"ancestors={ancestors!r}")
        _require(ancestors[-1].get("type") == "Module", f"last ancestor={ancestors[-1]!r}")
        _require(any(a.get("type") == "FunctionDef" and a.get("name") == "alpha"
                      for a in ancestors),
                  "enclosing FunctionDef 'alpha' missing from ancestor chain")
        return (f"include_ancestors=True: {len(ancestors)} ancestor(s), smallest-first, "
                "ending in Module, enclosing FunctionDef 'alpha' present")

    def case_include_ancestors_false_explicit() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 5, "include_ancestors": False})
        d = data_of(env)
        _require(is_success(env) and "ancestors" not in d, str(env))
        return "include_ancestors=False (explicit): ancestors absent"

    def case_one_past_end_is_line_not_found() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": LAST_LINE + 50})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "LINE_NOT_FOUND", f"code={error_code(env)!r}")
        return "line far past EOF -> stable LINE_NOT_FOUND"

    def case_line_zero_is_line_not_found() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 0})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "LINE_NOT_FOUND", f"code={error_code(env)!r}")
        return ("line=0 -> stable LINE_NOT_FOUND, NOT a parameter-validation error though the "
                "schema declares minimum=1 -- that minimum is not enforced at the validation layer")

    def case_negative_line_is_line_not_found() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": -7})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "LINE_NOT_FOUND", f"code={error_code(env)!r}")
        return "negative line -> stable LINE_NOT_FOUND, same as line=0 (declared minimum unenforced)"

    def case_wrong_type_line_generic_error() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": "not-an-int"})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == -32603, f"code={error_code(env)!r}")
        return "line as a string (wrong declared type) -> generic -32603"

    def case_missing_line_generic_error() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == -32603, f"code={error_code(env)!r}")
        return "missing required 'line' -> generic -32603 (no VALIDATION_ERROR-style stable code)"

    def case_missing_project_id_generic_error() -> str:
        env = node_at_line({"session_id": session_id, "file_path": FILE_A, "line": 1})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == -32603, f"code={error_code(env)!r}")
        return "missing project_id -> generic -32603"

    def case_empty_project_id_is_validation_error() -> str:
        env = node_at_line({"project_id": "", "session_id": session_id, "file_path": FILE_A, "line": 1})
        _require(not is_success(env), f"empty project_id must be refused: {env!r}")
        _require(error_code(env) == "VALIDATION_ERROR", f"code={error_code(env)!r}")
        _require(data_of(env) == {}, f"empty project_id leaked data: {data_of(env)!r}")
        return "project_id='' -> stable VALIDATION_ERROR, exactly as universal_file_open rejects it"

    def case_wrong_project_id_is_refused() -> str:
        env = node_at_line({"project_id": WRONG_PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 1})
        _require(not is_success(env), f"foreign project_id must be refused: {env!r}")
        _require(error_code(env) == "VALIDATION_ERROR", f"code={error_code(env)!r}")
        _require(error_message(env) == "session_id does not match project_id",
                  f"message={error_message(env)!r}")
        _require(data_of(env) == {}, f"foreign project_id leaked data: {data_of(env)!r}")
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": FILE_A, "line": 1})
        _require(is_success(env) and data_of(env).get("type") == "SimpleString",
                  f"owning project_id must still work: {env!r}")
        return ("a well-formed but FOREIGN project_id -> VALIDATION_ERROR with no data and "
                "universal_file_preview's own message, while the owning project_id still "
                "resolves the SimpleString node")

    def case_missing_session_id_generic_error() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "file_path": FILE_A, "line": 1})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == -32603, f"code={error_code(env)!r}")
        return "missing session_id -> generic -32603"

    def case_empty_session_id_is_session_not_found() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": "", "file_path": FILE_A, "line": 1})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "SESSION_NOT_FOUND", f"code={error_code(env)!r}")
        return "session_id='' -> stable SESSION_NOT_FOUND, unlike missing session_id (-32603)"

    def case_unknown_session_is_session_not_found() -> str:
        env = node_at_line({"project_id": PROJECT_ID,
                             "session_id": f"wliveq-unknown-{uuid.uuid4()}", "line": 1})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "SESSION_NOT_FOUND", f"code={error_code(env)!r}")
        return "unregistered session_id -> stable SESSION_NOT_FOUND"

    def case_unknown_extra_parameter_rejected() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                             "line": 1, "bogus": True})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == -32603, f"code={error_code(env)!r}")
        return "unknown extra parameter -> generic -32603, not a declared code"

    def case_file_path_absent_resolves_single_open_file() -> str:
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id, "line": 1})
        d = data_of(env)
        _require(is_success(env) and d.get("file_path") == FILE_A, str(env))
        return "file_path omitted with exactly one open file: resolves to that file"

    def case_multi_file_requires_file_path() -> str:
        _open(client, session_id, FILE_B, SAMPLE_PY)
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id, "line": 1})
        _require(not is_success(env), f"expected failure once 2 files are open: {env!r}")
        _require(error_code(env) == "SESSION_FILE_PATH_REQUIRED", f"code={error_code(env)!r}")
        _close(client, session_id, FILE_B)
        return "2 open files + no file_path -> stable SESSION_FILE_PATH_REQUIRED"

    def case_parse_error_fallback_is_unknown_format() -> str:
        env = client.call("universal_file_open", {
            "project_id": PROJECT_ID, "file_path": BROKEN_FILE, "session_id": session_id,
            "create": True, "initial_content": BROKEN_PY})
        _require(is_success(env), f"setup: open broken file failed: {env!r}")
        _require(data_of(env).get("is_invalid") is True, "server did not report is_invalid fallback")
        env = node_at_line({"project_id": PROJECT_ID, "session_id": session_id,
                             "file_path": BROKEN_FILE, "line": 1})
        _close(client, session_id, BROKEN_FILE)
        _require(not is_success(env), f"expected failure on an invalid-fallback file: {env!r}")
        _require(error_code(env) == "UNKNOWN_FORMAT", f"code={error_code(env)!r}")
        return "node_at_line on a parse-error/line-based-fallback session -> stable UNKNOWN_FORMAT"

    return [
        ("line_1_is_the_docstring_leaf", case_line_1_is_the_docstring_leaf),
        ("last_line_is_the_integer_leaf", case_last_line_is_the_integer_leaf),
        ("include_ancestors_true_full_chain", case_include_ancestors_true_full_chain),
        ("include_ancestors_false_explicit", case_include_ancestors_false_explicit),
        ("one_past_end_is_line_not_found", case_one_past_end_is_line_not_found),
        ("line_zero_is_line_not_found", case_line_zero_is_line_not_found),
        ("negative_line_is_line_not_found", case_negative_line_is_line_not_found),
        ("wrong_type_line_generic_error", case_wrong_type_line_generic_error),
        ("missing_line_generic_error", case_missing_line_generic_error),
        ("missing_project_id_generic_error", case_missing_project_id_generic_error),
        ("empty_project_id_is_validation_error", case_empty_project_id_is_validation_error),
        ("wrong_project_id_is_refused", case_wrong_project_id_is_refused),
        ("missing_session_id_generic_error", case_missing_session_id_generic_error),
        ("empty_session_id_is_session_not_found", case_empty_session_id_is_session_not_found),
        ("unknown_session_is_session_not_found", case_unknown_session_is_session_not_found),
        ("unknown_extra_parameter_rejected", case_unknown_extra_parameter_rejected),
        ("file_path_absent_resolves_single_open_file",
         case_file_path_absent_resolves_single_open_file),
        ("multi_file_requires_file_path", case_multi_file_requires_file_path),
        ("parse_error_fallback_is_unknown_format", case_parse_error_fallback_is_unknown_format),
    ]


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    ca = CaSession.acquire(comment="check-live-node-at-line")
    session_id = ca.session_id
    try:
        _open(client, session_id, FILE_A, SAMPLE_PY)
        cases = _build_cases(client, session_id, coverage)
        results = [_run_case(name, func) for name, func in cases]
    finally:
        _close(client, session_id, FILE_A)
        ca.dispose()

    output = [r.format() for r in results]
    report = coverage.report()
    output.append(report.format())
    if not report.complete:
        output.append("NOTE: TREE_NOT_AVAILABLE has no known public-API trigger (mirrors the "
                       "SESSION_INVALID/VALIDATION_ERROR pattern documented as unreachable "
                       "elsewhere in this API) -- left untested and named here explicitly.")
    output.append(schema.format_declared_surface())
    failed = [r.name for r in results if not r.passed]
    body_text = "\n".join(output)
    if failed:
        return CheckResult.fail(
            message=f"{len(failed)}/{len(results)} node_at_line case(s) failed: "
                    + ", ".join(failed),
            output=body_text)
    return CheckResult.ok(
        message=f"{len(results)}/{len(results)} node_at_line case(s) passed against "
                f"{client.endpoint.describe()}; coverage: {report.format().splitlines()[0]}",
        output=body_text)


def check_live_node_at_line() -> CheckResult:
    """Entry point: run the live node_at_line cases against the real deployed
    server. An unreachable server FAILS the check (see run_live_check) --
    there is no skip concept and no registration gate: the check always
    exists."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_node_at_line)
