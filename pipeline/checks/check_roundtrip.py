"""Continuous byte-identical round-trip check over a real file corpus ({p022}, {p106}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Byte-identical round-trip is the core guarantee of this engine: parsing a
real file with its format plugin and rendering the resulting ``Document``
back must reproduce the original bytes exactly. This check enforces that
guarantee continuously against real files rather than hand-written
fixtures. Per format it samples a bounded set of real files, runs
``plugin.parse_document(bytes)`` then ``plugin.render_document(document)``,
and compares the produced bytes against the bytes read from disk. Files are
enumerated in sorted order and sampled with ``random.Random(SAMPLE_SEED)``
-- never bare ``random`` -- so the sample, and every number measured below,
is reproducible rather than incidental.

There are two verdict policies. ``STRICT`` (python, json, toml, yaml,
plain_text): any byte difference is a failure, and so is a refusal (a
raised exception), *unless* an independent reference parser drawn from the
project's own declared dependencies rejects the same bytes too. That excuse
is not a tolerance knob but an objective second opinion that a file is
genuinely malformed: it is what keeps the two YAML documents under
``docs/`` that PyYAML itself rejects (``ScannerError``/``ParserError``)
from being reported as engine defects, while weakening nothing for
well-formed input.

``BASELINE`` (bsl). BSL has no stdlib reference parser and is genuinely the
weak format: measured on the real 1C configuration dump at
``BSL_CORPUS_DEFAULT`` (1550 ``.bsl`` files), a 200-file sample under
``SAMPLE_SEED`` yields **0 byte-identical files, 162 mismatches -- 62 of
them differing only by the UTF-8 BOM the translator drops -- and 38
refusals**. Those measurements, not guesses, are the baseline rates below.
A permanently RED check is one everybody learns to ignore, so BSL sitting
*at* its measured baseline does not turn the whole check RED; instead the
real BSL numbers are printed on every run, pass or fail, so the deficit is
never invisible. Any regression below the baseline -- a higher mismatch
rate or a higher refusal rate -- turns the check RED, and improving BSL is
expected to come with tightening these constants. That corpus lives outside
the repository; when it is missing the format is reported SKIPPED with the
reason and the path looked for, never silently counted as a pass, and the
same holds for any format whose patterns match no file. The check reports
through ``CheckResult`` only -- it never prints and never calls
``sys.exit``; the CLI owns console output and exit codes.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import importlib.util
import json
import os
import random
import sys
import tomllib
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from pipeline import registry
from pipeline.registry import CheckResult

CHECK_NAME = "check-roundtrip"
CHECK_DESCRIPTION = (
    "Byte-identical round-trip over a real corpus: parse each sampled file "
    "with its format plugin, render it back, and require identical bytes; "
    "per-format results with a documented, measured BSL baseline."
)

# Fixed seed for the per-format sample. Changing it changes which files are
# checked and therefore invalidates every measured number in this module.
SAMPLE_SEED = 20260806

# Reference corpus for BSL: a real 1C configuration dump outside the
# repository, overridable so the check can run against another dump.
BSL_CORPUS_ENV_VAR = "TREE_ENGINE_BSL_CORPUS"
BSL_CORPUS_DEFAULT = Path("/home/vasilyvz/vcv")

# Measured on BSL_CORPUS_DEFAULT (1550 .bsl files), 200-file sample under
# SAMPLE_SEED: 162 mismatches and 38 refusals out of 200.
BSL_BASELINE_MAX_MISMATCH_RATE = 162 / 200
BSL_BASELINE_MAX_REFUSED_RATE = 38 / 200

# Guard against float representation noise when an observed rate is
# arithmetically equal to a baseline rate. Not a tolerance: it is smaller
# than one file in any corpus this check can enumerate.
_RATE_EPSILON = 1e-9

# Directories never walked when collecting in-repository corpus files.
_PRUNED_DIRS = frozenset(
    {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
)

# Offending paths listed per format before the list is truncated.
_MAX_LISTED_FAILURES = 10

_UTF8_BOM = b"\xef\xbb\xbf"


class Policy(enum.Enum):
    """How a format's measurements are turned into a verdict."""
    STRICT = "strict"
    BASELINE = "baseline"


class FormatVerdict(enum.Enum):
    """Per-format outcome. SKIPPED is never folded into PASS."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclasses.dataclass(frozen=True)
class FormatSpec:
    """One format: where its plugin lives, its corpus, and its policy."""
    format_id: str
    module: str
    attribute: str
    patterns: Tuple[str, ...]
    sample_cap: int
    policy: Policy
    external_corpus: bool = False


# Sample caps are chosen so the whole check stays around fifteen seconds;
# LibCST parsing dominates, so python is capped hardest.
_PLUGINS = "tree_engine.plugins"
FORMAT_SPECS: Tuple[FormatSpec, ...] = (
    FormatSpec("python", f"{_PLUGINS}.python.plugin", "PYTHON_FORMAT_PLUGIN", ("*.py", "*.pyi"), 60, Policy.STRICT),
    FormatSpec("json", f"{_PLUGINS}.json_format", "JSON_FORMAT_PLUGIN", ("*.json",), 200, Policy.STRICT),
    FormatSpec("toml", f"{_PLUGINS}.toml_format", "TOML_FORMAT_PLUGIN", ("*.toml",), 200, Policy.STRICT),
    FormatSpec("yaml", f"{_PLUGINS}.yaml.plugin", "YAML_FORMAT_PLUGIN", ("*.yaml", "*.yml"), 400, Policy.STRICT),
    FormatSpec("plain_text", f"{_PLUGINS}.plain_text", "PLAIN_TEXT_FORMAT_PLUGIN", ("*.txt", "*.md"), 200, Policy.STRICT),
    FormatSpec("bsl", f"{_PLUGINS}.bsl.plugin", "BSL_FORMAT_PLUGIN", ("*.bsl",), 200, Policy.BASELINE, True),
)


@dataclasses.dataclass
class FormatOutcome:
    """Measurements and verdict for one format."""

    format_id: str
    verdict: FormatVerdict
    reason: str = ""
    corpus_size: int = 0
    sampled: int = 0
    identical: int = 0
    mismatched: int = 0
    bom_only: int = 0
    refused_unexcused: int = 0
    refused_excused: int = 0
    failures: List[str] = dataclasses.field(default_factory=list)

    @property
    def failed_files(self) -> int:
        """Files that did not round-trip, excused refusals aside."""
        return self.mismatched + self.refused_unexcused

    def summary(self) -> str:
        """One dense line: what was measured for this format and how it was judged."""
        if self.verdict is FormatVerdict.SKIPPED:
            return f"  {self.format_id:<11} SKIPPED  {self.reason}"
        parts = [
            f"{self.identical}/{self.sampled} identical",
            f"{self.mismatched} mismatched",
            f"{self.refused_unexcused} refused",
        ]
        if self.bom_only:
            parts.append(f"{self.bom_only} mismatch(es) differ only by a dropped UTF-8 BOM")
        if self.refused_excused:
            parts.append(f"{self.refused_excused} refusal(s) excused, reference parser rejects them too")
        line = f"  {self.format_id:<11} {self.verdict.value:<8} " + ", ".join(parts)
        return line if not self.reason else f"{line}; {self.reason}"


# A STRICT refusal is excused only when an independent parser rejects the
# same bytes; each callable below simply raises when it does not accept the
# input. PyYAML is imported lazily so a machine lacking it can still import
# this module -- an unavailable reference parser excuses nothing and leaves
# the refusal counted as a failure.


_REFERENCE_PARSERS: Dict[str, Callable[[bytes], object]] = {
    "python": lambda data: ast.parse(data),
    "json": lambda data: json.loads(data.decode("utf-8")),
    "toml": lambda data: tomllib.loads(data.decode("utf-8")),
    "yaml": lambda data: list(importlib.import_module("yaml").compose_all(data.decode("utf-8"))),
    "plain_text": lambda data: data.decode("utf-8"),
}


def _reference_rejects(format_id: str, data: bytes) -> bool:
    """True when the independent reference parser also refuses ``data``.

    A missing reference parser, or one whose import fails, returns False:
    nothing is excused on the strength of a check that could not run.
    """
    parser = _REFERENCE_PARSERS.get(format_id)
    if parser is None:
        return False
    try:
        parser(data)
    except ImportError:
        return False
    except Exception:  # noqa: BLE001 - any rejection is the answer we want
        return True
    return False


def _repo_root() -> Path:
    """Repository root of the tree this check file ships inside."""
    return Path(__file__).resolve().parents[2]


def _ensure_engine_importable(root: Path) -> None:
    """Put ``<root>/src`` on ``sys.path`` when ``tree_engine`` is not installed.

    The check must round-trip the engine it ships with, including inside a
    verbatim copy of the repository, while staying importable by CLI
    discovery when only the repository root is on ``PYTHONPATH``.
    """
    if importlib.util.find_spec("tree_engine") is not None:
        return
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
        importlib.invalidate_caches()


def _collect_files(root: Path, patterns: Sequence[str]) -> List[Path]:
    """Every file under ``root`` matching ``patterns``, sorted, VCS/build dirs pruned."""
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _PRUNED_DIRS)
        base = Path(dirpath)
        for filename in sorted(filenames):
            candidate = base / filename
            if any(candidate.match(pattern) for pattern in patterns):
                found.append(candidate)
    return sorted(set(found))


def _sample(files: Sequence[Path], cap: int) -> List[Path]:
    """Deterministically pick at most ``cap`` files out of ``files``."""
    if len(files) <= cap:
        return list(files)
    return sorted(random.Random(SAMPLE_SEED).sample(list(files), cap))


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _measure(spec: FormatSpec, plugin: object, files: Sequence[Path], root: Path) -> FormatOutcome:
    """Round-trip every sampled file and record the raw counts."""
    outcome = FormatOutcome(spec.format_id, FormatVerdict.PASS, sampled=len(files))
    for path in files:
        try:
            original = path.read_bytes()
        except OSError as exc:
            outcome.refused_unexcused += 1
            outcome.failures.append(f"{_relative(path, root)}: unreadable: {exc}")
            continue
        try:
            document = plugin.parse_document(original)  # type: ignore[attr-defined]
            rendered = plugin.render_document(document)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - a refusal is a measurement
            if _reference_rejects(spec.format_id, original):
                outcome.refused_excused += 1
            else:
                outcome.refused_unexcused += 1
                outcome.failures.append(
                    f"{_relative(path, root)}: refused: {type(exc).__name__}: {exc}"
                )
            continue
        if rendered == original:
            outcome.identical += 1
            continue
        outcome.mismatched += 1
        detail = "rendered bytes differ"
        if original.startswith(_UTF8_BOM) and rendered == original[len(_UTF8_BOM):]:
            outcome.bom_only += 1
            detail = "rendered bytes differ: UTF-8 BOM dropped"
        outcome.failures.append(f"{_relative(path, root)}: {detail}")
    return outcome


def _judge(spec: FormatSpec, outcome: FormatOutcome) -> None:
    """Apply the format's policy to its measurements, in place."""
    if spec.policy is Policy.STRICT:
        if outcome.failed_files:
            outcome.verdict = FormatVerdict.FAIL
            outcome.reason = f"{outcome.failed_files} file(s) did not round-trip byte-identically"
        return

    sampled = outcome.sampled or 1
    mismatch_rate = outcome.mismatched / sampled
    refused_rate = outcome.refused_unexcused / sampled
    regressions = []
    if mismatch_rate > BSL_BASELINE_MAX_MISMATCH_RATE + _RATE_EPSILON:
        regressions.append(
            f"mismatch rate {mismatch_rate:.1%} exceeds measured baseline "
            f"{BSL_BASELINE_MAX_MISMATCH_RATE:.1%}"
        )
    if refused_rate > BSL_BASELINE_MAX_REFUSED_RATE + _RATE_EPSILON:
        regressions.append(
            f"refusal rate {refused_rate:.1%} exceeds measured baseline "
            f"{BSL_BASELINE_MAX_REFUSED_RATE:.1%}"
        )
    if regressions:
        outcome.verdict = FormatVerdict.FAIL
        outcome.reason = "regression below documented baseline: " + "; ".join(regressions)
        return
    outcome.reason = (
        f"at or under the documented baseline (max {BSL_BASELINE_MAX_MISMATCH_RATE:.1%} "
        f"mismatched, max {BSL_BASELINE_MAX_REFUSED_RATE:.1%} refused); known-weak, not correct"
    )


def _corpus_root(spec: FormatSpec, repo_root: Path) -> Path:
    """Where this format's corpus lives: the repository, or the external dump."""
    if not spec.external_corpus:
        return repo_root
    configured = os.environ.get(BSL_CORPUS_ENV_VAR)
    return Path(configured) if configured else BSL_CORPUS_DEFAULT


def _run_format(spec: FormatSpec, repo_root: Path) -> FormatOutcome:
    """Resolve the corpus and the plugin, then measure and judge one format."""
    corpus_root = _corpus_root(spec, repo_root)
    if spec.external_corpus and not corpus_root.is_dir():
        return FormatOutcome(spec.format_id, FormatVerdict.SKIPPED, reason=(
            f"external corpus not present at {corpus_root} (set {BSL_CORPUS_ENV_VAR} "
            f"to point at a real corpus); nothing was verified"))
    try:
        plugin = getattr(importlib.import_module(spec.module), spec.attribute)
    except Exception as exc:  # noqa: BLE001 - an unloadable plugin is a failure
        return FormatOutcome(spec.format_id, FormatVerdict.FAIL, reason=(
            f"cannot load {spec.module}:{spec.attribute}: {type(exc).__name__}: {exc}"))

    files = _collect_files(corpus_root, spec.patterns)
    if not files:
        return FormatOutcome(spec.format_id, FormatVerdict.SKIPPED, reason=(
            f"no file matching {', '.join(spec.patterns)} under {corpus_root}; "
            f"nothing was verified"))

    outcome = _measure(spec, plugin, _sample(files, spec.sample_cap), corpus_root)
    outcome.corpus_size = len(files)
    _judge(spec, outcome)
    return outcome


def _render_output(outcomes: Sequence[FormatOutcome], repo_root: Path) -> str:
    """Full detail: corpus sizes and the bounded list of offending files."""
    lines = [f"repository root: {repo_root}", f"sample seed: {SAMPLE_SEED}", ""]
    for outcome in outcomes:
        if outcome.verdict is FormatVerdict.SKIPPED:
            lines.append(f"{outcome.format_id}: SKIPPED - {outcome.reason}")
            continue
        lines.append(
            f"{outcome.format_id}: {outcome.verdict.value} - sampled {outcome.sampled} "
            f"of {outcome.corpus_size} file(s)"
        )
        shown = outcome.failures[:_MAX_LISTED_FAILURES]
        lines.extend(f"    {failure}" for failure in shown)
        omitted = len(outcome.failures) - len(shown)
        if omitted > 0:
            lines.append(f"    ... and {omitted} more offending file(s) not listed")
    return "\n".join(lines)


def check_roundtrip() -> CheckResult:
    """Round-trip every format's sampled corpus and report the verdict."""
    repo_root = _repo_root()
    _ensure_engine_importable(repo_root)

    outcomes = [_run_format(spec, repo_root) for spec in FORMAT_SPECS]
    passed = [o for o in outcomes if o.verdict is FormatVerdict.PASS]
    failed = [o for o in outcomes if o.verdict is FormatVerdict.FAIL]
    skipped = [o for o in outcomes if o.verdict is FormatVerdict.SKIPPED]

    headline = (
        f"{len(passed)} format(s) PASS, {len(failed)} FAIL, {len(skipped)} SKIPPED "
        f"over {sum(o.sampled for o in outcomes)} sampled file(s)"
    )
    message = "\n".join([headline] + [o.summary() for o in outcomes])
    output = _render_output(outcomes, repo_root)
    if failed:
        return CheckResult.fail(message=message, output=output)
    return CheckResult.ok(message=message, output=output)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_roundtrip)
