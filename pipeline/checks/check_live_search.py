"""Live full-surface check for ``universal_file_search``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises every declared parameter and every declared error case of
``universal_file_search`` against the REAL deployed ai-editor server (mTLS,
sandbox project ``editor_test``), driving coverage from the server's own
``help(cmdname="universal_file_search")`` schema so nothing added later goes
silently untested. Nothing here is mocked, stubbed, or replayed.

This is the command where an editor lies most easily, so the emphasis is on
exact assertions rather than "the call did not raise": both search modes are
checked against a file of KNOWN structure (exact counts/identifiers, not a
non-empty list); a selector matching nothing asserts EMPTY (``matches ==
[]``), never an error; a malformed CSTQuery selector fails with the declared
``QUERY_PARSE_ERROR``, reproducibly (fixed: used to be a bare, undeclared
``-32000`` -- the parser's ``QueryParseError`` is not a ``ValueError`` and
missed the ``ValueError``->``INVALID_SEARCH`` handler); every malformed
request shape (missing/unknown parameter, enum violation) now returns the
declared ``VALIDATION_ERROR`` instead of a generic ``-32603``; and the
parse-error fallback returns the documented ``UNKNOWN_FORMAT`` here too.

Also asserted: ``project_id`` is declared ``required`` and now enforced (it
used to be discarded outright, so empty/wrong values returned full results
for another project's file); both now fail ``VALIDATION_ERROR``, the same
code and message ``universal_file_preview`` uses, while the owning id still
returns every match.

Registration is unconditional, like ``check-live-core``: no environment gate,
no skip concept. :func:`pipeline.live.client.run_live_check` FAILS the check
outright when the server cannot be reached -- an unreachable deployment is
this check being RED, not opting out.
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

CHECK_NAME = "check-live-search"
CHECK_DESCRIPTION = (
    "Live full-surface check for universal_file_search against the REAL "
    "deployed server: every declared parameter and error case, exact match "
    "counts/identifiers, empty-result vs malformed-selector, and the "
    "parse-error-fallback UNKNOWN_FORMAT path.")

COMMAND = "universal_file_search"
PROJECT_ID = "99d60878-53d0-42c0-a06e-41e4782b75e7"  # sandbox 'editor_test' -- never the real project
FILE_A = "wliveq_search_a.py"
FILE_B = "wliveq_search_b.py"
BROKEN_FILE = "wliveq_search_broken.py"
WRONG_PROJECT_ID = "00000000-0000-0000-0000-000000000000"

# Known structure: 4 FunctionDef nodes (alpha, beta, Gamma.method_one/two); beta spans lines 8-9.
SAMPLE_PY = (
    '"""Sample module for the live search check."""\n'
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
ALL_FUNCTION_NAMES = ("alpha", "beta", "method_one", "method_two")
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
    def search(params: Dict[str, Any]) -> Dict[str, Any]:
        env = client.call(COMMAND, params)
        coverage.record_call(params, env)
        return env

    def case_xpath_default_all_functiondefs() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "query": "//FunctionDef"})
        d = data_of(env)
        _require(is_success(env), f"expected success: {env!r}")
        _require(d.get("search_type") == "xpath", f"search_type={d.get('search_type')!r}")
        _require(d.get("total_matches") == 4, f"total_matches={d.get('total_matches')!r}")
        names = sorted(m.get("name") for m in d.get("matches", []))
        _require(names == sorted(ALL_FUNCTION_NAMES), f"names={names!r}")
        return f"4/4 FunctionDef matches: {names}"

    def case_simple_node_type_matches_same_set() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "search_type": "simple", "node_type": "FunctionDef"})
        d = data_of(env)
        _require(is_success(env) and d.get("search_type") == "simple", str(env))
        _require(d.get("total_matches") == 4, f"total_matches={d.get('total_matches')!r}")
        return "simple/node_type=FunctionDef agrees with xpath: 4 matches"

    def case_simple_name_and_qualname_filters() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "search_type": "simple", "name": "beta"})
        d = data_of(env)
        _require(is_success(env) and d.get("total_matches", 0) >= 1, str(env))
        named = [m["name"] for m in d["matches"] if m.get("name") is not None]
        _require(named and all(n == "beta" for n in named), f"named={named!r}")

        env2 = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                        "search_type": "simple", "qualname": "Gamma.method_one"})
        d2 = data_of(env2)
        _require(is_success(env2) and d2.get("total_matches", 0) >= 1, str(env2))
        quals = {m.get("qualname") for m in d2["matches"]}
        _require(quals == {"Gamma.method_one"}, f"qualnames={quals!r}")
        return (f"name=beta: {d['total_matches']} match(es) all named 'beta'; "
                f"qualname=Gamma.method_one: {d2['total_matches']} match(es) all matching")

    def case_simple_line_range() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "search_type": "simple", "node_type": "FunctionDef",
                       "start_line": 8, "end_line": 9})
        d = data_of(env)
        _require(is_success(env), str(env))
        _require(d.get("total_matches") == 1, f"total_matches={d.get('total_matches')!r}")
        _require(d["matches"][0]["name"] == "beta", d["matches"][0].get("name"))
        return "start_line=8/end_line=9 isolates exactly beta"

    def case_text_search_mode() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "search_type": "text", "query": "return"})
        d = data_of(env)
        _require(is_success(env) and d.get("search_type") == "text", str(env))
        _require(d.get("total_matches", 0) > 0, f"total_matches={d.get('total_matches')!r}")
        _require("code" not in d["matches"][0], "include_code defaulted true unexpectedly")
        return f"text search 'return': {d['total_matches']} match(es), include_code default absent"

    def case_include_code_and_require_one_unique() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "query": "//FunctionDef[@name='alpha']", "require_one": True,
                       "include_code": True})
        d = data_of(env)
        _require(is_success(env), str(env))
        _require(d.get("returned_matches") == 1, f"returned_matches={d.get('returned_matches')!r}")
        _require("code" in d["matches"][0], "include_code=True did not attach source")
        _require(d.get("node_ref") == d["matches"][0]["node_ref"], "top-level node_ref mismatch")
        return "require_one unique match + include_code=True: source attached, node_ref echoed"

    def case_require_one_nomatch_and_nonunique() -> str:
        env1 = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                        "query": "//FunctionDef[@name='ghost_fn_xyz']", "require_one": True})
        env2 = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                        "query": "//FunctionDef", "require_one": True})
        _require(not is_success(env1) and error_code(env1) == "NoMatch", f"0 matches: {env1!r}")
        _require(not is_success(env2) and error_code(env2) == "NonUniqueMatch", f"4 matches: {env2!r}")
        return "require_one + 0 matches -> stable NoMatch; require_one + 4 matches -> NonUniqueMatch"

    def case_selector_matching_nothing_is_empty_not_error() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "query": "//FunctionDef[@name='does_not_exist_xyz']"})
        d = data_of(env)
        _require(is_success(env), f"a no-match selector must succeed, not error: {env!r}")
        _require(d.get("matches") == [], f"matches={d.get('matches')!r}")
        _require(d.get("total_matches") == 0, f"total_matches={d.get('total_matches')!r}")
        return "selector matching nothing: success=True, matches=[], total_matches=0"

    def case_malformed_selector_reproducible_code() -> str:
        env1 = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                        "query": "((("})
        env2 = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                        "query": "%%%not-valid%%%"})
        _require(not is_success(env1) and not is_success(env2), "both malformed queries must fail")
        c1, c2 = error_code(env1), error_code(env2)
        _require(c1 == c2 == "QUERY_PARSE_ERROR", f"codes={c1!r},{c2!r}; expected QUERY_PARSE_ERROR both times")
        return ("two different malformed selectors both fail with the declared QUERY_PARSE_ERROR "
                "(fixed: used to be a bare, undeclared -32000 -- CSTQuery's own QueryParseError "
                "was not a ValueError, so it missed the command's ValueError->INVALID_SEARCH "
                "handler and fell to the generic default-code branch)")

    def case_missing_query_is_invalid_search() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id})
        _require(not is_success(env), f"expected failure: {env!r}")
        _require(error_code(env) == "INVALID_SEARCH", f"code={error_code(env)!r}")
        return "xpath default with no query -> stable INVALID_SEARCH"

    def case_max_results_cap_and_minimum() -> str:
        def cap(n: int) -> Mapping[str, Any]:
            return search({"project_id": PROJECT_ID, "session_id": session_id,
                           "file_path": FILE_A, "query": "//FunctionDef", "max_results": n})
        for n in (1, 2):
            _require((d := data_of(cap(n))).get("total_matches") == 4 and len(d["matches"]) == n
                      and d.get("returned_matches") == n, f"max_results={n}: {d!r}")
        for low in (0, -1):  # below the declared minimum=1: a value, never "unspecified"
            _require(error_code(env := cap(low)) == "VALIDATION_ERROR" and data_of(env) == {}
                      and ">= 1" in error_message(env), f"max_results={low}: {env!r}")
        return ("max_results=1 and =2 cap returned_matches (total_matches stays 4); 0 and -1 "
                "are below the declared minimum of 1 and are refused with VALIDATION_ERROR "
                "and no data (fixed: 0 used to be read as 'not specified', so it never capped)")

    def case_project_id_is_enforced() -> str:
        env = search({"project_id": "", "session_id": session_id, "file_path": FILE_A,
                       "query": "//FunctionDef"})
        _require(not is_success(env), f"empty project_id must be refused: {env!r}")
        _require(error_code(env) == "VALIDATION_ERROR",
                  f"empty project_id: code={error_code(env)!r}")
        _require(data_of(env) == {}, f"empty project_id leaked data: {data_of(env)!r}")
        env = search({"project_id": WRONG_PROJECT_ID, "session_id": session_id,
                       "file_path": FILE_A, "query": "//FunctionDef"})
        _require(not is_success(env), f"foreign project_id must be refused: {env!r}")
        _require(error_code(env) == "VALIDATION_ERROR",
                  f"foreign project_id: code={error_code(env)!r}")
        _require(error_message(env) == "session_id does not match project_id",
                  f"foreign project_id: message={error_message(env)!r}")
        _require(data_of(env) == {}, f"foreign project_id leaked data: {data_of(env)!r}")
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
                       "query": "//FunctionDef"})
        d = data_of(env)
        _require(is_success(env) and d.get("total_matches") == 4,
                  f"owning project_id must still work: {env!r}")
        return ("project_id is enforced: '' and a well-formed but FOREIGN project id are both "
                "VALIDATION_ERROR with no data (the FOREIGN one carries the same message "
                "universal_file_preview uses), while the owning project id still returns all "
                "4 matches")

    def case_malformed_request_shapes_are_validation_error() -> str:
        scenarios = (
            ("missing project_id",
             {"session_id": session_id, "file_path": FILE_A, "query": "//FunctionDef"}),
            ("missing session_id",
             {"project_id": PROJECT_ID, "file_path": FILE_A, "query": "//FunctionDef"}),
            ("unknown extra parameter",
             {"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
              "query": "//FunctionDef", "bogus_param": 1}),
            ("search_type enum violation",
             {"project_id": PROJECT_ID, "session_id": session_id, "file_path": FILE_A,
              "search_type": "bogus", "query": "x"}),
        )
        for label, params in scenarios:
            env = search(params)
            _require(not is_success(env), f"expected failure ({label}): {env!r}")
            _require(error_code(env) == "VALIDATION_ERROR", f"{label}: code={error_code(env)!r}")
        return ("declared VALIDATION_ERROR (fixed: used to be a generic, undeclared -32603) for: " +
                ", ".join(label for label, _ in scenarios))

    def case_session_not_found_empty_and_unknown() -> str:
        env1 = search({"project_id": PROJECT_ID, "session_id": "", "file_path": FILE_A,
                        "query": "//FunctionDef"})
        env2 = search({"project_id": PROJECT_ID, "session_id": f"wliveq-unknown-{uuid.uuid4()}",
                        "query": "//FunctionDef"})
        for env, label in ((env1, "empty session_id"), (env2, "unregistered session_id")):
            _require(not is_success(env), f"expected failure ({label}): {env!r}")
            _require(error_code(env) == "SESSION_NOT_FOUND", f"{label}: code={error_code(env)!r}")
        return ("session_id='' and an unregistered session_id both -> stable SESSION_NOT_FOUND "
                "(unlike a MISSING session_id, which is the schema-level VALIDATION_ERROR path)")

    def case_file_path_absent_resolves_single_open_file() -> str:
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "query": "//FunctionDef"})
        d = data_of(env)
        _require(is_success(env) and d.get("file_path") == FILE_A, str(env))
        return "file_path omitted with exactly one open file: resolves to that file"

    def case_multi_file_requires_file_path() -> str:
        _open(client, session_id, FILE_B, SAMPLE_PY)
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "query": "//FunctionDef"})
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
        env = search({"project_id": PROJECT_ID, "session_id": session_id, "file_path": BROKEN_FILE,
                       "query": "//FunctionDef"})
        _close(client, session_id, BROKEN_FILE)
        _require(not is_success(env), f"expected failure on an invalid-fallback file: {env!r}")
        _require(error_code(env) == "UNKNOWN_FORMAT", f"code={error_code(env)!r}")
        return "search on a parse-error/line-based-fallback session -> stable UNKNOWN_FORMAT"

    return [
        ("xpath_default_matches_all_functiondefs", case_xpath_default_all_functiondefs),
        ("simple_node_type_matches_same_set", case_simple_node_type_matches_same_set),
        ("simple_name_and_qualname_filters", case_simple_name_and_qualname_filters),
        ("simple_start_end_line_range", case_simple_line_range),
        ("text_search_mode", case_text_search_mode),
        ("include_code_and_require_one_unique", case_include_code_and_require_one_unique),
        ("require_one_nomatch_and_nonunique", case_require_one_nomatch_and_nonunique),
        ("selector_matching_nothing_is_empty_not_error",
         case_selector_matching_nothing_is_empty_not_error),
        ("malformed_selector_reproducible_code", case_malformed_selector_reproducible_code),
        ("missing_query_is_invalid_search", case_missing_query_is_invalid_search),
        ("max_results_cap_and_minimum", case_max_results_cap_and_minimum),
        ("project_id_is_enforced", case_project_id_is_enforced),
        ("malformed_request_shapes_are_validation_error", case_malformed_request_shapes_are_validation_error),
        ("session_not_found_empty_and_unknown", case_session_not_found_empty_and_unknown),
        ("file_path_absent_resolves_single_open_file",
         case_file_path_absent_resolves_single_open_file),
        ("multi_file_requires_file_path", case_multi_file_requires_file_path),
        ("parse_error_fallback_is_unknown_format", case_parse_error_fallback_is_unknown_format),
    ]


def _body(client: LiveClient) -> CheckResult:
    schema = client.command_schema(COMMAND)
    coverage = CommandCoverage(schema)
    ca = CaSession.acquire(comment="check-live-search")
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
        output.append("NOTE: TREE_NOT_AVAILABLE has no known public-API trigger -- left "
                       "untested and named here explicitly.")
    output.append(schema.format_declared_surface())
    failed = [r.name for r in results if not r.passed]
    body_text = "\n".join(output)
    if failed:
        return CheckResult.fail(
            message=f"{len(failed)}/{len(results)} search case(s) failed: " + ", ".join(failed),
            output=body_text)
    return CheckResult.ok(
        message=f"{len(results)}/{len(results)} search case(s) passed against "
                f"{client.endpoint.describe()}; coverage: {report.format().splitlines()[0]}",
        output=body_text)


def check_live_search() -> CheckResult:
    """Entry point: run the live search cases against the real deployed server.
    An unreachable server FAILS the check (see run_live_check) -- there is no
    skip concept and no registration gate: the check always exists."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_search)
