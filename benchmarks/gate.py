"""Benchmark gate: structural counters plus temporal regression detection (C-022, {p029}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The gate consumes a ``tree_engine.bench_suite/1`` report -- produced here by calling
:func:`bench_suite.run_benchmarks`, or handed in already measured -- and judges it against a
baseline stored per version branch. :func:`run_gate` is the only public callable; the module
registers nothing with the pipeline registry, which the sibling check-benchmark module owns.

Two families of criteria, weighted by how much each can be trusted on a real machine. Every
threshold here is derived from three independent full runs of IDENTICAL code (45 measurements
each), because a gate that cries wolf gets disabled and then protects nothing:

* STRUCTURAL, from the {p030} instrumentation counters, and by far the stronger half. These
  are counts, not clocks: across those three runs every one of the 45 per-operation
  ``affected_nodes`` values was bit-identical, so they are compared tightly. A single local
  mutation must raise no ``full-traversal``/``full-parse``/``full-index-rebuild`` marker,
  must touch a bounded fraction of the tree, and -- the scaling invariant -- must touch a
  flat number of nodes while the corpus grows 10x, whereas a whole-document scenario must
  grow roughly linearly with it.
* TEMPORAL, median and p95 against the baseline, only for the four scenarios that run long
  enough to mean anything (:data:`TIMED_SCENARIOS`). The six ``mutate_*`` scenarios and
  ``batch_mixed`` run 0.06-8 ms and drifted by up to 733% between identical runs; they are
  measured and reported but NEVER thresholded on time. Even the four timed scenarios drifted
  hard: run 2 was 1.47-2.31x slower than run 1 on every scenario at once, so a plain 20%
  median+p95 rule would have fired on 4 of 24 identical-code scenario comparisons. {p029}'s
  qualifier is therefore enforced literally: a point counts only when it also exceeds
  :data:`TIMING_NOISE_FACTOR` units of the within-run spread the suite measured for those two
  runs, and a scenario counts only when :data:`STABILITY_FRACTION` of its corpora agree. The
  honest cost of that, measured against two deliberately slowed engines: a 1.2-1.5x slowdown
  of ``load_parse`` is REPORTED (``advisory``) but does not block, while a 4.1-5.3x one
  blocks on 6 of 6 corpora. With the suite's default 5 iterations this half resolves a
  multiple, not the 20% of the policy. Raise ``iterations`` to tighten it -- and record the
  baseline with the same value, since it is part of the profile key.

Baseline: ``benchmarks/baselines/<major>.<minor>.json``, schema
``tree_engine.bench_gate_baseline/1``, written ONLY by an explicit
``run_gate(update_baseline=True, decision="...")`` call that records who decided what and
which violations were accepted. With no baseline the gate does NOT invent one and does NOT
pass: it returns ``status="no-baseline"`` with ``passed=False``, having still run every
structural check, and tells the caller how to record one.
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _path in (str(_ROOT / "src"), str(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import bench_suite  # noqa: E402
from tree_engine.core import instrumentation as instr  # noqa: E402

#: The one entry point this module exposes; everything else is a constant or private.
__all__ = ["run_gate"]

GATE_SCHEMA = "tree_engine.bench_gate/1"
BASELINE_SCHEMA = "tree_engine.bench_gate_baseline/1"
DEFAULT_BASELINE_DIR = _HERE / "baselines"

#: {p029} default: reject a stable regression above 20%.
DEFAULT_TOLERANCE = 0.20
#: Scenarios whose wall time is large enough to threshold; see module docstring.
TIMED_SCENARIOS: Tuple[str, ...] = ("load_parse", "query_select", "save_publish",
                                    "load_tree_decode")
#: A timing regression must show on this share of a scenario's corpora to count as stable.
#: The worst identical-code case measured reached 3 of 6 corpora (query_select, the run that
#: was uniformly ~2x slow), so 0.6 would have left a single corpus of margin; 0.8 leaves two
#: and costs almost no detection power, because a genuine slowdown hits every corpus.
STABILITY_FRACTION = 0.8
#: ...and on at least this many of them, so a lone outlier can never fire the gate.
STABILITY_MIN_POINTS = 2
#: ...and it must exceed this many units of the measured within-run spread of the two runs
#: being compared. Measured on three independent runs of IDENTICAL code (24 scenario
#: comparisons): the worst deciding value was 1.80 units, and a factor of 2.0 is the
#: smallest round value above it -- 0 of those 24 comparisons fire at 2.0, 1 fires at 1.5
#: and 2 fire at 1.0. This is what makes {p029}'s "statistically stable" testable instead of
#: decorative; at 20% alone, 4 of the 24 identical-code comparisons would have fired.
TIMING_NOISE_FACTOR = 2.0
#: Share of the document one local operation may touch before it stops being local. The
#: worst measured value is batch_mixed's 196 of 11704 nodes = 0.0167 (eight operations in
#: one scenario); every single mutation measures 0.0039 or less. The limit is 3x the worst.
LOCALITY_RATIO_LIMIT = 0.05
#: Growth of a per-operation structural counter over the baseline that counts as a
#: regression. The counters are identical to the node across independent runs, so this is
#: slack for deliberate model changes, not for noise.
STRUCTURAL_TOLERANCE = 0.25
#: ...ignored below this absolute node delta: the smallest counter measured is 4 nodes per
#: operation (mutate_delete), so a floor of 2 still catches a 50% regression there.
STRUCTURAL_MIN_DELTA = 2
#: A local mutation's node cost must stay flat while the corpus grows: max largest/smallest.
LOCAL_SCALING_LIMIT = 1.5
#: A whole-document scenario may grow with the corpus, but not super-linearly: the measured
#: median ratio over a 10x corpus growth must stay under this multiple of that growth.
DOCUMENT_SCALING_SLACK = 2.5

_MUTATE = instr.PHASE_MUTATE
_VERSION_RE = re.compile(r"^version\s*=\s*[\"'](\d+)\.(\d+)\.", re.MULTILINE)


def _version_branch() -> str:
    """The ``major.minor`` branch the baseline is indexed by, read from ``pyproject.toml``."""
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"no 'version = \"major.minor.patch\"' in {_ROOT / 'pyproject.toml'}")
    return f"{match.group(1)}.{match.group(2)}"


def _profile_key(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """The fixed-CI-profile identity of a report ({p029}). Timing is only comparable within
    one of these; the OS patch level is deliberately left out so a kernel bump does not
    invalidate a baseline, while the machine, interpreter and suite shape do."""
    platform_name = str(metadata.get("platform", "")).split("-")[0]
    python = ".".join(str(metadata.get("python_version", "")).split(".")[:2])
    return {"platform": platform_name, "python": python, "sizes": list(metadata.get("sizes", [])),
            "formats": list(metadata.get("formats", [])), "seed": metadata.get("seed"),
            "iterations": metadata.get("iterations"), "warmups": metadata.get("warmups")}


def _measurements(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Flatten a suite report into ``"scenario|corpus" -> comparable metrics``."""
    if report.get("schema") != bench_suite.SCHEMA_ID:
        raise ValueError(f"expected a {bench_suite.SCHEMA_ID} report, got {report.get('schema')!r}")
    out: Dict[str, Dict[str, Any]] = {}
    for scenario, per_corpus in report["results"].items():
        for corpus, record in per_corpus.items():
            timing, counters = record["timing_ns"], record["counters"]
            phases = (counters or {}).get("phases", {})
            # The suite's counter delta covers every measured repetition, so a raw
            # affected_nodes total is iterations-dependent; per invocation it is not, and
            # it is the number a locality budget can be stated against.
            calls = sum(int(p["invocations"]) for p in phases.values())
            touched = sum(int(p["affected_nodes"]) for p in phases.values())
            out[f"{scenario}|{corpus}"] = {
                "scenario": scenario, "corpus": corpus, "phase": record["phase"],
                "format_id": record["format_id"], "nodes": record["input"]["nodes"],
                "bytes": record["input"]["bytes"], "lines": record["input"]["lines"],
                "median_ns": timing["median_ns"], "p95_ns": timing["p95_ns"],
                "min_ns": timing["min_ns"], "relative_spread": timing["relative_spread"],
                "invocations": calls,
                "affected_nodes": None if counters is None else touched / calls if calls else 0.0,
                "is_local": None if counters is None else bool(counters["is_local_operation"]),
                "markers": [] if counters is None else list(counters["structural_markers"])}
    return out


def _finding(check: str, key: str, status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    scenario, _, corpus = key.partition("|")
    return {"check": check, "scenario": scenario, "corpus": corpus, "status": status,
            "detail": detail, **extra}


def _structural_findings(current: Dict[str, Dict[str, Any]],
                         baseline: Optional[Dict[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Marker, locality-ratio and counter-growth checks. No clock is read here, so nothing in
    this function can fire on scheduler noise."""
    findings: List[Dict[str, Any]] = []
    for key, m in sorted(current.items()):
        if m["is_local"] is None:
            findings.append(_finding("instrumentation", key, "fail",
                                     "counters are null: run the suite with instrumentation=True"))
            continue
        if m["phase"] != _MUTATE:
            continue
        findings.append(_finding(
            "structural_markers", key, "pass" if m["is_local"] else "fail",
            f"markers={m['markers'] or 'none'}; a single local operation must raise none of "
            f"{list(instr.STRUCTURAL_MARKERS)}", markers=m["markers"]))
        ratio = m["affected_nodes"] / m["nodes"] if m["nodes"] else 1.0
        findings.append(_finding(
            "locality_ratio", key, "pass" if ratio <= LOCALITY_RATIO_LIMIT else "fail",
            f"touched {m['affected_nodes']:.1f} of {m['nodes']} nodes per operation "
            f"= {ratio:.4f}, "
            f"limit {LOCALITY_RATIO_LIMIT}", observed=ratio, limit=LOCALITY_RATIO_LIMIT))
        old = (baseline or {}).get(key)
        if old is None or old.get("affected_nodes") is None:
            continue
        grown = m["affected_nodes"] - old["affected_nodes"]
        over = old["affected_nodes"] * (1 + STRUCTURAL_TOLERANCE)
        failed = grown >= STRUCTURAL_MIN_DELTA and m["affected_nodes"] > over
        findings.append(_finding(
            "structural_counters", key, "fail" if failed else "pass",
            f"affected_nodes/op {old['affected_nodes']:.1f} -> {m['affected_nodes']:.1f} "
            f"({grown:+.1f}); tolerance {STRUCTURAL_TOLERANCE:.0%} and >= "
            f"{STRUCTURAL_MIN_DELTA} nodes", observed=m["affected_nodes"],
            baseline=old["affected_nodes"]))
    return findings


def _by_scenario(current: Dict[str, Dict[str, Any]],
                 scenario: str, format_id: str) -> List[Dict[str, Any]]:
    return sorted((m for m in current.values()
                   if m["scenario"] == scenario and m["format_id"] == format_id),
                  key=lambda m: m["lines"])


def _scaling_findings(current: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The invariant a stored baseline cannot express: within ONE run, a local mutation's
    cost must stay flat as the corpus grows, and a whole-document scenario may grow with the
    corpus but not faster. Both are ratios inside one run, so machine speed cancels out."""
    findings: List[Dict[str, Any]] = []
    scenarios = sorted({m["scenario"] for m in current.values()})
    formats = sorted({m["format_id"] for m in current.values()})
    for scenario in scenarios:
        for format_id in formats:
            series = _by_scenario(current, scenario, format_id)
            if len(series) < 2 or series[0]["lines"] == series[-1]["lines"]:
                continue
            small, large = series[0], series[-1]
            key = f"{scenario}|{format_id}:{small['lines']}->{large['lines']}"
            growth = large["nodes"] / small["nodes"]
            if small["phase"] == _MUTATE:
                if small["affected_nodes"] in (None, 0):
                    continue
                ratio = large["affected_nodes"] / small["affected_nodes"]
                findings.append(_finding(
                    "local_scaling", key, "pass" if ratio <= LOCAL_SCALING_LIMIT else "fail",
                    f"affected_nodes/op {small['affected_nodes']:.1f} -> "
                    f"{large['affected_nodes']:.1f} "
                    f"({ratio:.2f}x) while the corpus grew {growth:.1f}x; a local operation "
                    f"must stay under {LOCAL_SCALING_LIMIT}x", observed=ratio,
                    limit=LOCAL_SCALING_LIMIT))
                continue
            ratio = large["median_ns"] / small["median_ns"] if small["median_ns"] else math.inf
            limit = growth * DOCUMENT_SCALING_SLACK
            findings.append(_finding(
                "document_scaling", key, "pass" if ratio <= limit else "fail",
                f"median grew {ratio:.2f}x while the corpus grew {growth:.1f}x; roughly linear "
                f"is expected, limit {limit:.1f}x", observed=ratio, limit=limit))
    return findings


def _timing_findings(current: Dict[str, Dict[str, Any]], baseline: Dict[str, Dict[str, Any]],
                     tolerance: float) -> List[Dict[str, Any]]:
    """Median and p95 against the baseline for :data:`TIMED_SCENARIOS`, under the {p029}
    stability rule as measured, not as hoped: a corpus point counts only when median AND p95
    both exceed ``tolerance`` AND the excess is larger than :data:`TIMING_NOISE_FACTOR` units
    of the within-run spread the suite itself reported for those two runs; a scenario counts
    only when enough of its corpora agree. A point over the tolerance but inside the noise
    envelope is reported as ``advisory`` -- visible, never blocking."""
    findings: List[Dict[str, Any]] = []
    for scenario in TIMED_SCENARIOS:
        points: List[Tuple[str, bool]] = []
        for key, m in sorted(current.items()):
            old = baseline.get(key)
            if m["scenario"] != scenario or old is None:
                continue
            median = m["median_ns"] / old["median_ns"] if old["median_ns"] else math.inf
            p95 = m["p95_ns"] / old["p95_ns"] if old["p95_ns"] else math.inf
            joint = min(median, p95)
            spread = float(old.get("relative_spread", 0.0)) + m["relative_spread"]
            units = (joint - 1) / spread if spread else math.inf
            over = joint > 1 + tolerance
            stable = over and units > TIMING_NOISE_FACTOR
            points.append((key, stable))
            findings.append(_finding(
                "timing_point", key,
                "regressed" if stable else "advisory" if over else "ok",
                f"median {old['median_ns'] / 1e6:.3f} -> {m['median_ns'] / 1e6:.3f} ms "
                f"({median:.2f}x), p95 {old['p95_ns'] / 1e6:.3f} -> {m['p95_ns'] / 1e6:.3f} ms "
                f"({p95:.2f}x); joint {joint:.2f}x is {units:.2f} units of the {spread:.2f} "
                f"within-run spread, envelope {TIMING_NOISE_FACTOR}",
                median_ratio=median, p95_ratio=p95, noise_units=units))
        if not points:
            continue
        hot = [key for key, stable in points if stable]
        share = len(hot) / len(points)
        stable = len(hot) >= STABILITY_MIN_POINTS and share >= STABILITY_FRACTION
        findings.append(_finding(
            "timing_regression", f"{scenario}|all", "fail" if stable else "pass",
            f"{len(hot)}/{len(points)} corpora regressed above {tolerance:.0%} on median AND "
            f"p95 and beyond the noise envelope ({share:.0%}); stable needs "
            f">= {STABILITY_MIN_POINTS} corpora and >= {STABILITY_FRACTION:.0%}"
            + (f"; regressed: {hot}" if hot else ""), regressed=hot, corpora=len(points)))
    return findings


def _baseline_payload(report: Dict[str, Any], current: Dict[str, Dict[str, Any]], branch: str,
                      decision: str, accepted: Sequence[Dict[str, Any]],
                      previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    keep = ("median_ns", "p95_ns", "min_ns", "affected_nodes", "invocations", "is_local",
            "markers", "nodes", "bytes", "lines", "phase", "format_id", "scenario", "corpus",
            "relative_spread")
    return {"schema": BASELINE_SCHEMA, "version_branch": branch,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "decision": decision, "profile": _profile_key(report["metadata"]),
            "source_metadata": report["metadata"],
            "accepted_violations": [dict(item) for item in accepted],
            "supersedes": None if previous is None else
            {"recorded_at": previous.get("recorded_at"), "decision": previous.get("decision")},
            "measurements": {key: {name: m[name] for name in keep} for key, m in current.items()}}


def _read_baseline(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != BASELINE_SCHEMA:
        raise ValueError(f"{path}: expected schema {BASELINE_SCHEMA}, got {payload.get('schema')!r}")
    return payload


def _verdict(status: str, passed: bool, branch: str, path: Path, tolerance: float,
             findings: List[Dict[str, Any]], report: Dict[str, Any],
             baseline: Optional[Dict[str, Any]], message: str) -> Dict[str, Any]:
    failures = [f for f in findings if f["status"] == "fail"]
    return {"schema": GATE_SCHEMA, "status": status, "passed": passed, "message": message,
            "version_branch": branch, "baseline_path": str(path), "tolerance": tolerance,
            "baseline_recorded_at": None if baseline is None else baseline.get("recorded_at"),
            "baseline_decision": None if baseline is None else baseline.get("decision"),
            "profile": _profile_key(report["metadata"]),
            "baseline_profile": None if baseline is None else baseline.get("profile"),
            "findings": findings, "violations": failures,
            "summary": {"measurements": report["summary"]["measurements"],
                        "checks": len(findings), "failed": len(failures),
                        "suite_structural_failures": report["summary"]["structural_failures"],
                        "wall_clock_s": report["summary"]["wall_clock_s"]}}


def run_gate(*, report: Optional[Dict[str, Any]] = None, baseline_dir: Optional[Path] = None,
             version_branch: Optional[str] = None, tolerance: float = DEFAULT_TOLERANCE,
             update_baseline: bool = False, decision: Optional[str] = None,
             **suite_kwargs: Any) -> Dict[str, Any]:
    """Run the benchmark gate and return its verdict ({p029}); the single entry point.

    ``report`` is an already-measured ``tree_engine.bench_suite/1`` payload, or ``None`` to
    run the suite here with ``suite_kwargs`` (``sizes``, ``formats``, ``iterations``, ...).
    The baseline is ``<baseline_dir>/<version_branch>.json``, defaulting to
    ``benchmarks/baselines/`` and the ``major.minor`` of ``pyproject.toml``.

    ``update_baseline=True`` records the run as the new baseline for that branch and REQUIRES
    a non-empty ``decision`` explaining it; the decision, the superseded record and every
    violation accepted by it are written into the file. Without a baseline the gate returns
    ``status="no-baseline"`` and ``passed=False``: structural checks still ran and are
    reported, but nothing is compared and nothing is invented.

    ``status`` is one of ``pass``, ``fail``, ``no-baseline``, ``profile-mismatch`` or
    ``baseline-updated``; ``passed`` is the boolean a caller gates on.
    """
    if update_baseline and not (decision or "").strip():
        raise ValueError("update_baseline requires a non-empty decision explaining the change")
    if report is None:
        report = bench_suite.run_benchmarks(instrumentation=True, **suite_kwargs)
    elif suite_kwargs:
        raise ValueError(f"suite arguments {sorted(suite_kwargs)} are meaningless with a report")
    branch = version_branch or _version_branch()
    path = Path(baseline_dir or DEFAULT_BASELINE_DIR) / f"{branch}.json"
    current = _measurements(report)
    previous = _read_baseline(path)
    old_measurements = None if previous is None else previous["measurements"]
    findings = _structural_findings(current, old_measurements) + _scaling_findings(current)
    if previous is not None:
        if _profile_key(report["metadata"]) == previous.get("profile"):
            findings += _timing_findings(current, old_measurements, tolerance)
        else:
            findings.append(_finding(
                "profile", "profile|all", "fail",
                f"this run's profile {_profile_key(report['metadata'])} is not the baseline's "
                f"{previous.get('profile')}; timing is not comparable across profiles "
                "({p029} fixes the CI profile). Re-record the baseline on this profile."))
    failures = [f for f in findings if f["status"] == "fail"]
    if update_baseline:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _baseline_payload(report, current, branch, decision.strip(), failures, previous)
        path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        return _verdict("baseline-updated", True, branch, path, tolerance, findings, report,
                        payload, f"baseline for {branch} recorded from this run; "
                        f"{len(failures)} violation(s) accepted by decision: {decision.strip()}")
    if previous is None:
        return _verdict(
            "no-baseline", False, branch, path, tolerance, findings, report, None,
            f"no baseline for version branch {branch} at {path}: the temporal half of the gate "
            f"cannot run and is NOT assumed to pass. {len(failures)} structural violation(s) "
            "were still checked. Record one with run_gate(update_baseline=True, "
            "decision='...') from a run you trust.")
    if failures:
        status = "profile-mismatch" if any(f["check"] == "profile" for f in failures) else "fail"
        return _verdict(status, False, branch, path, tolerance, findings, report, previous,
                        f"{len(failures)} violation(s): "
                        + "; ".join(f"{f['check']} {f['scenario']}@{f['corpus']}"
                                    for f in failures[:6]))
    return _verdict("pass", True, branch, path, tolerance, findings, report, previous,
                    f"{len(findings)} checks passed against the {branch} baseline recorded "
                    f"{previous.get('recorded_at')} at tolerance {tolerance:.0%}")
