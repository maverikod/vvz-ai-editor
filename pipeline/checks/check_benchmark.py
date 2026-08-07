"""Pipeline-level benchmark gate check (C-022, {p028}, {p029}, {p030}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

This module is the ONLY place in the benchmark chain that registers with the
pipeline registry (see ``pipeline/registry.py``). ``benchmarks/gate.py`` and
``benchmarks/bench_suite.py`` are pure, registry-free callables --
:func:`benchmarks.gate.run_gate` is the single entry point this check drives.
Nothing here re-implements measurement or judgement; it runs the real gate
against the real ``src/tree_engine`` engine and turns its verdict into a
:class:`~pipeline.registry.CheckResult`.

Default profile
----------------

The full default benchmark profile (``sizes=(1000, 5000, 10000)``,
``formats=("python", "json")``) takes roughly four minutes -- too slow for a
check a person runs routinely alongside the rest of ``pipeline``. Measured on
this machine, ``sizes=(1000,)`` alone (both formats, {p028}'s minimum of 5
measured iterations) takes on the order of fifteen seconds. That is the
default here: fast enough to run every time, real enough to exercise every
scenario at least once. A full pre-release run, or a run matching whatever
profile a recorded baseline was made at, is one environment variable away --
see ``*_ENV_VAR`` below -- never a code change.

The no-baseline decision
-------------------------

No baseline is committed to this repository (``benchmarks/baselines/`` does
not exist yet). :func:`benchmarks.gate.run_gate` reports that honestly as
``status="no-baseline", passed=False``: on principle it never invents a
comparison it cannot make, and by itself it does not distinguish "no data"
from "a real violation" in its own ``passed`` field for that branch -- it
returns ``passed=False`` for BOTH a missing baseline and a structural
violation is folded into other branches (``fail``/``profile-mismatch``).

A missing baseline is NOT a regression: nothing has gotten slower, there is
simply nothing recorded yet to compare against. But it must not read as an
unqualified, silent green either. This check resolves that by judging on the
STRUCTURAL half alone whenever the TEMPORAL half could not run for a benign
reason (``no-baseline`` or ``profile-mismatch``, per the module docstring of
``benchmarks/gate.py`` -- a different machine/profile is likewise not a
regression): the structural instrumentation counters (no full-traversal, no
full-parse, no full-index-rebuild marker on a single local mutation; a
bounded locality ratio; flat per-operation cost as the corpus grows) are
real, baseline-independent evidence, and a genuine structural regression
must still turn this check red even with zero history. When the temporal
half DID run and reports ``status="fail"``, that verdict is trusted as-is.
The message and output always say, in the open, which half ran and which
did not, plus the exact call to record a baseline deliberately -- never
performed by this check itself, per {p029}'s requirement that a baseline is
written only by an explicit, human-decided ``run_gate(update_baseline=True,
decision=...)`` call.

The check registers itself on the shared pipeline registry and reports
through ``CheckResult``/``CheckStatus`` only -- it never prints or calls
``sys.exit`` itself; the pipeline CLI owns all console output and process
exit codes.
"""

from __future__ import annotations

import os
from typing import Any, Dict, FrozenSet, List, Sequence, Tuple

from pipeline import registry
from pipeline.registry import CheckResult

from benchmarks import bench_suite, gate

CHECK_NAME = "check-benchmark"
CHECK_DESCRIPTION = (
    "Run the {p029} benchmark gate: structural instrumentation-counter "
    "assertions (no full traversal/parse/index-rebuild, bounded locality, "
    "flat local-operation scaling) plus, when a matching baseline exists, "
    "median/p95 timing regression detection at a 20% tolerance."
)

#: Override the default profile without touching this file. Comma-separated;
#: e.g. ``TREE_ENGINE_BENCHMARK_SIZES=1000,5000,10000`` for a full pre-release
#: run, or values matching a recorded baseline's profile exactly.
SIZES_ENV_VAR = "TREE_ENGINE_BENCHMARK_SIZES"
FORMATS_ENV_VAR = "TREE_ENGINE_BENCHMARK_FORMATS"
ITERATIONS_ENV_VAR = "TREE_ENGINE_BENCHMARK_ITERATIONS"

#: {p028} minimum iterations is bench_suite's own default (5); only the
#: default SIZE tuple is narrowed here, to keep a routine run fast (see the
#: module docstring's "Default profile" section for the measured timings).
DEFAULT_CHECK_SIZES: Tuple[int, ...] = (1000,)

#: gate finding "check" kinds that need no baseline to be meaningful --
#: {p030}'s instrumentation counters and the within-run scaling invariants.
#: A failure here is real evidence of a structural regression regardless of
#: whether a baseline exists.
STRUCTURAL_CHECK_KINDS: FrozenSet[str] = frozenset({
    "instrumentation", "structural_markers", "locality_ratio",
    "structural_counters", "local_scaling", "document_scaling",
})
#: gate finding "check" kinds that only exist once a matching baseline let
#: the temporal half run.
TEMPORAL_CHECK_KINDS: FrozenSet[str] = frozenset({"timing_point", "timing_regression"})
#: Statuses where the temporal half legitimately did not run for a benign
#: reason -- missing history or a different machine/profile -- neither of
#: which is itself a regression (see the module docstring).
_BENIGN_NO_COMPARISON_STATUSES = frozenset({"no-baseline", "profile-mismatch"})


def _resolve_profile() -> Dict[str, Any]:
    """The sizes/formats/iterations/warmups this run uses, defaults or env."""
    sizes_raw = os.environ.get(SIZES_ENV_VAR, "").strip()
    formats_raw = os.environ.get(FORMATS_ENV_VAR, "").strip()
    iterations_raw = os.environ.get(ITERATIONS_ENV_VAR, "").strip()
    sizes = (tuple(int(part) for part in sizes_raw.split(",") if part.strip())
             if sizes_raw else DEFAULT_CHECK_SIZES)
    formats = (tuple(part.strip() for part in formats_raw.split(",") if part.strip())
               if formats_raw else tuple(bench_suite.DEFAULT_FORMATS))
    iterations = int(iterations_raw) if iterations_raw else bench_suite.DEFAULT_ITERATIONS
    return {"sizes": sizes, "formats": formats, "iterations": iterations,
            "warmups": bench_suite.DEFAULT_WARMUPS}


def _structural_findings(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [f for f in findings if f["check"] in STRUCTURAL_CHECK_KINDS]


def _temporal_findings(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [f for f in findings if f["check"] in TEMPORAL_CHECK_KINDS]


def _structural_ok(findings: Sequence[Dict[str, Any]]) -> bool:
    """True when every baseline-independent structural finding passed."""
    return all(f["status"] != "fail" for f in _structural_findings(findings))


def _finding_line(finding: Dict[str, Any]) -> str:
    tag = finding["status"].upper()
    return f"    [{tag}] {finding['check']} {finding['scenario']}@{finding['corpus']}: {finding['detail']}"


def _section(title: str, findings: Sequence[Dict[str, Any]]) -> List[str]:
    if not findings:
        return [f"  {title}: none"]
    ok_statuses = ("pass", "ok")
    ok = sum(1 for f in findings if f["status"] in ok_statuses)
    lines = [f"  {title}: {ok}/{len(findings)} ok"]
    lines += [_finding_line(f) for f in findings]
    return lines


def _record_baseline_hint(profile: Dict[str, Any], branch: str) -> str:
    return (
        f"no committed baseline for version branch {branch}: this run's temporal half did "
        "not compare against anything, by design (nothing is invented). Record one "
        "deliberately from a run you trust, e.g.:\n"
        "  python -c \"from benchmarks.gate import run_gate; run_gate("
        f"sizes={list(profile['sizes'])}, formats={list(profile['formats'])}, "
        f"iterations={profile['iterations']}, update_baseline=True, "
        "decision='<why this run is the new baseline>')\""
    )


def _render(result: Dict[str, Any], profile: Dict[str, Any], structural_ok: bool) -> str:
    """Full CI-log detail: profile used, gate verdict, then both halves."""
    findings = result["findings"]
    lines = [
        f"profile: sizes={list(profile['sizes'])} formats={list(profile['formats'])} "
        f"iterations={profile['iterations']} warmups={profile['warmups']}",
        f"gate status={result['status']} gate.passed={result['passed']} "
        f"structural_ok={structural_ok} tolerance={result['tolerance']:.0%}",
        result["message"],
        "",
        "-- structural half ({p030} instrumentation; meaningful without a baseline) --",
    ]
    structural = _structural_findings(findings)
    for kind in ("instrumentation", "structural_markers", "locality_ratio",
                 "structural_counters", "local_scaling", "document_scaling"):
        lines += _section(kind, [f for f in structural if f["check"] == kind])
    lines += ["", "-- temporal half (median/p95 vs. baseline; requires a matching profile) --"]
    if result["status"] in _BENIGN_NO_COMPARISON_STATUSES:
        lines.append(f"  skipped: {result['message']}")
    else:
        temporal = _temporal_findings(findings)
        for kind in ("timing_point", "timing_regression"):
            lines += _section(kind, [f for f in temporal if f["check"] == kind])
    if result["status"] == "no-baseline":
        lines += ["", _record_baseline_hint(profile, result["version_branch"])]
    elif result["status"] == "profile-mismatch":
        lines += ["", f"baseline profile {result['baseline_profile']} does not match this "
                       f"run's profile {result['profile']}; re-record on this profile to "
                       "compare timing again"]
    return "\n".join(lines)


def _verdict_message(result: Dict[str, Any], structural_ok: bool, passed: bool) -> str:
    if result["status"] in _BENIGN_NO_COMPARISON_STATUSES:
        half = "structural only -- temporal comparison did not run: " + result["status"]
        verdict = "structural checks hold" if structural_ok else "STRUCTURAL REGRESSION found"
        return f"{half}; {verdict}"
    checks = result["summary"]["checks"]
    failed = result["summary"]["failed"]
    return f"{result['status']}: {checks - failed}/{checks} gate checks passed ({result['message']})"


def check_benchmark() -> CheckResult:
    """Run the real {p029} benchmark gate and report its verdict.

    Judges on the gate's own verdict when the temporal half actually ran
    (``status in ("pass", "fail", "baseline-updated")``); when it could not
    run for a benign reason (``no-baseline``/``profile-mismatch``), judges on
    the baseline-independent structural half alone, which the gate itself
    still computes and reports in that case -- see the module docstring.
    """
    profile = _resolve_profile()
    result = gate.run_gate(sizes=profile["sizes"], formats=profile["formats"],
                            iterations=profile["iterations"], warmups=profile["warmups"])
    structural_ok = _structural_ok(result["findings"])
    if result["status"] in _BENIGN_NO_COMPARISON_STATUSES:
        passed = structural_ok
    else:
        passed = bool(result["passed"])
    message = _verdict_message(result, structural_ok, passed)
    output = _render(result, profile, structural_ok)
    return (CheckResult.ok if passed else CheckResult.fail)(message=message, output=output)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_benchmark)
