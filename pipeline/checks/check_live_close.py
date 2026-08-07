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

This check asserts the DECLARED CONTRACT and FAILS when the deployed server
diverges from it. Three divergences it previously only recorded as findings are
now hard assertions, because each of them was a real defect:

* ``MODIFIED_NOT_WRITTEN`` is documented as the guard that stops uncommitted
  edits from being silently discarded ("false (default): reject the close with
  MODIFIED_NOT_WRITTEN so edits are never silently discarded"). It must FIRE:
  after a real ``universal_file_edit`` that ``universal_file_write`` confirms as
  ``has_changes: true``, a default close must be REFUSED and the session left
  open with the edit intact. It used to succeed and destroy the edit.
* ``write_before_close=true`` -- the one declared escape -- must really commit
  the pending edit before closing. It used to discard it just as silently.
* ``project_id`` is declared required, so an EMPTY ``project_id`` must be
  rejected with ``VALIDATION_ERROR`` exactly as ``universal_file_open`` rejects
  it, and an empty ``file_path`` must be rejected too rather than silently
  treated as an omitted ``file_path``.

A ``file_path`` that names no open file is still recorded as a FINDING: it is
rejected with ``SESSION_NOT_FOUND`` whose message reads ``Unknown session:
<session_id>`` even though the session exists and is healthy.

Work is confined to the sandbox project ``editor_test``. Only the
``write_before_close=true`` case commits -- it must, to prove the escape really
writes -- and it commits to one FIXED fixture path that every run overwrites, so
the sandbox never accumulates files.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pipeline import registry
from pipeline.checks.check_live_close_scenarios import (
    COMMAND,
    UNREACHABLE_CODES,
    _empty_value_scenarios,
    _modified_scenario,
    _multi_file_scenario,
    _negative_scenarios,
    _Probe,
    _single_file_scenarios,
    _write_before_close_scenario,
)
from pipeline.live.client import CommandCoverage, LiveClient, run_live_check
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-close"
CHECK_DESCRIPTION = (
    "Exercise the entire declared surface of universal_file_close against the "
    "real deployed server: all four parameters in both directions, both "
    "write_before_close states, and every reachable error case."
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
    _write_before_close_scenario(probe)
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
