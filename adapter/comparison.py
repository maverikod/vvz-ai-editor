"""Comparison mode for the AI Editor staged migration (G-029/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Concept C-023, {p034}: before a feature flag can be trusted, each operation must be
run through BOTH engines and every difference recorded, so the switchover is evidence
based. This module is that mode: :class:`ComparisonMode` dispatches the command on the
new engine through :class:`adapter.mcp_adapter.MCPAdapter` (the PRIMARY side, whose
result is returned to the caller unchanged), and schedules the legacy side on a
background worker so the caller never waits for it. :class:`ResultNormalizer` reduces
both outcomes to one comparable mapping per command, the diff is computed by the
already-merged ``CommandTrace.divergence()`` seam, and :class:`DivergenceLog` keeps the
machine-readable record: command, params, legacy result, new result, normalized diff.

Honesty rules this file is bound by. The legacy side is the REAL in-process
``ai_editor`` library -- ``cst_query.executor.query_source`` and
``tree.handlers.python_handler.PythonHandler`` -- never a stub and never a replayed
value; the legacy MCP command classes are not imported, they need a live server. An
operation with no in-process legacy counterpart is recorded NOT_COMPARABLE with the
concrete reason (:data:`NOT_COMPARABLE_COMMANDS`, :func:`not_comparable_reasons`), never
credited as agreement. A failure on one side and a success on the other IS a divergence
and is reported as one, carrying both outcomes. Only fields the two engines genuinely
share are compared; a field whose shape is engine-specific (node granularity, id spaces)
is listed in ``uncompared_fields`` instead of being faked into a diff. Importing
``ai_editor`` here is intended: this is ``adapter/``, the compatibility layer ({p003});
``src/tree_engine/`` stays clean of it.
"""

from __future__ import annotations

import itertools
import threading
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from adapter.mcp_adapter import (COMMAND_SPECS, UNAVAILABLE_BASELINE_COMMANDS, CommandTrace,
                                 MCPAdapter)

__all__ = ["NotComparable", "AGREEMENT", "DIVERGENCE", "NOT_COMPARABLE", "ComparisonRecord",
           "DivergenceLog", "EnablementStrategy", "ResultNormalizer", "ComparisonMode",
           "LEGACY_RUNNERS", "NOT_COMPARABLE_COMMANDS", "not_comparable_reasons"]

AGREEMENT, DIVERGENCE, NOT_COMPARABLE = "agreement", "divergence", "not_comparable"

#: Python is the only format the legacy in-process surface understands (LibCST).
_LEGACY_SUFFIXES = (".py", ".pyi", ".pyw")

#: Commands with no in-process legacy counterpart at all, with the real reason.
NOT_COMPARABLE_COMMANDS: Mapping[str, str] = {
    "universal_file_preview":
        "legacy preview is ai_editor.tree.preview_navigation.PreviewNavigation, built around a "
        "tree_loader over the Code Analysis edit-session/sidecar tree store and addressed by a "
        "short_id minted by that store; running it needs a live session, so nothing can be "
        "executed in process to compare against",
    "universal_file_capabilities":
        "adapter-native command: COMMAND_SPECS records baseline_command '(none)', so there is no "
        "legacy behaviour to run at all",
}


class NotComparable(Exception):
    """Raised by a legacy runner when THIS call cannot be compared, with the reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def not_comparable_reasons() -> Dict[str, str]:
    """Every command known to be uncomparable in process: the commands above plus the
    baseline commands the adapter never exposes (:data:`UNAVAILABLE_BASELINE_COMMANDS`)."""
    reasons = dict(NOT_COMPARABLE_COMMANDS)
    for command, reason in UNAVAILABLE_BASELINE_COMMANDS.items():
        reasons[command] = f"not exposed by the adapter: {reason}"
    return reasons


# -- the legacy side: real in-process ai_editor calls ------------------------

def _read(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8")


def _require_legacy_format(file_path: str) -> None:
    if Path(file_path).suffix.lower() not in _LEGACY_SUFFIXES:
        raise NotComparable(
            f"legacy in-process surface is LibCST/Python-only; {Path(file_path).suffix!r} has no "
            "ai_editor counterpart (its non-Python handlers live behind the MCP command classes, "
            "which need mcp_proxy_adapter and a live server)")


def _handler() -> Any:
    """The real legacy Python tree handler, imported lazily so a caller that never
    compares never pays for the ai_editor import."""
    from ai_editor.tree.handlers.python_handler import PythonHandler
    return PythonHandler()


def legacy_open(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy load: ``PythonHandler.mark`` really parses the file with LibCST and
    assigns the baseline short_id markers. Only the load OUTCOME is comparable -- the
    two engines index different node populations, so counts are not compared."""
    _require_legacy_format(str(params["file_path"]))
    _handler().mark(_read(str(params["file_path"])))
    return {"loaded": True}


def legacy_search(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy ``cst_query`` executed for real over the same file and selector."""
    _require_legacy_format(str(params["file_path"]))
    from ai_editor.cst_query.executor import query_source
    matches = query_source(_read(str(params["file_path"])), str(params["query"]))
    return _match_shape([(m.kind, m.name or "") for m in matches])


def legacy_write(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy save-side guarantee: ``unmark(mark(source))`` must return the original
    bytes. Nothing is written -- the legacy round trip is pure, and comparison mode
    must never mutate the corpus it observes."""
    file_path = str(params["file_path"])
    _require_legacy_format(file_path)
    source = params.get("content")
    source = _read(file_path) if source is None else str(source)
    handler = _handler()
    return {"byte_identical": handler.unmark(handler.mark(source)) == source}


def _match_shape(pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
    """The shared shape of a selector result: how many, of which semantic kinds, under
    which names. Names are sorted so a traversal-order difference is not read as a
    content difference; ids, positions and source text are engine-specific (uncompared)."""
    return {"total": len(pairs), "kind_counts": dict(sorted(Counter(k for k, _ in pairs).items())),
            "names": sorted(n for _, n in pairs)}


#: command -> the real legacy callable. A command absent here is NOT_COMPARABLE.
LEGACY_RUNNERS: Mapping[str, Callable[[Mapping[str, Any]], Dict[str, Any]]] = {
    "universal_file_open": legacy_open, "universal_file_search": legacy_search,
    "universal_file_write": legacy_write}


# -- normalization ----------------------------------------------------------

class ResultNormalizer:
    """New-engine envelope -> the same shape the legacy runners return.

    Every command declares which fields are genuinely shared and which are deliberately
    left out; :attr:`uncompared` is reported on each record so a reader sees what the
    verdict does NOT cover instead of assuming it covers everything."""

    UNCOMPARED: Mapping[str, Tuple[str, ...]] = {
        "universal_file_open": ("node_count/root ids: different node populations, different "
                                "id spaces",),
        "universal_file_search": ("node_id/short_id_hex, range, parent_path, source: "
                                  "engine-specific id space and result payload",),
        "universal_file_write": ("target_path/sha256/bytes_written: the legacy round trip "
                                 "publishes nothing, so only the fidelity flag is shared",)}

    def normalize(self, command: str, envelope: Mapping[str, Any]) -> Dict[str, Any]:
        """Reduce a new-engine envelope to the comparable mapping for ``command``."""
        if not envelope.get("success"):
            return {"error": str((envelope.get("error") or {}).get("code"))}
        data = dict(envelope.get("data") or {})
        if command == "universal_file_open":
            return {"loaded": True}
        if command == "universal_file_search":
            return _match_shape([(str(m.get("kind", "")), str(m.get("name", "") or ""))
                                 for m in data.get("matches", [])])
        if command == "universal_file_write":
            return {"byte_identical": bool(data.get("byte_identical"))}
        raise NotComparable(NOT_COMPARABLE_COMMANDS.get(
            command, f"no normalization is defined for {command!r}"))

    @staticmethod
    def from_exception(exc: BaseException) -> Dict[str, Any]:
        """An exception is a real outcome, not a missing one: it is normalized into the
        comparable mapping so success on one side and failure on the other diverges."""
        return {"error": f"{type(exc).__name__}: {exc}"}

    def uncompared(self, command: str) -> Tuple[str, ...]:
        return self.UNCOMPARED.get(command, ())


# -- the record and the log -------------------------------------------------

@dataclass(frozen=True)
class ComparisonRecord:
    """One machine-readable comparison outcome."""

    command: str
    params: Mapping[str, Any]
    verdict: str
    old: Optional[Mapping[str, Any]] = None
    new: Optional[Mapping[str, Any]] = None
    diff: Optional[Mapping[str, Any]] = None
    reason: str = ""
    uncompared_fields: Tuple[str, ...] = ()
    approved_divergences: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        """JSON-safe form; keys are fixed and ordered, so two runs over the same corpus
        serialize identically."""
        pairs = (("old", self.old), ("new", self.new), ("diff", self.diff))
        return {"command": self.command, "params": dict(self.params), "verdict": self.verdict,
                **{k: (None if v is None else dict(v)) for k, v in pairs},
                "reason": self.reason, "uncompared_fields": list(self.uncompared_fields),
                "approved_divergences": list(self.approved_divergences)}


class DivergenceLog:
    """Thread-safe, append-only record of every comparison the mode performed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[ComparisonRecord] = []

    def add(self, record: ComparisonRecord) -> None:
        with self._lock:
            self._records.append(record)

    @property
    def records(self) -> Tuple[ComparisonRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def of(self, verdict: str) -> Tuple[ComparisonRecord, ...]:
        """Every record with one verdict: ``AGREEMENT``/``DIVERGENCE``/``NOT_COMPARABLE``."""
        return tuple(r for r in self.records if r.verdict == verdict)

    def as_dict(self) -> Dict[str, Any]:
        records = self.records
        totals: Dict[str, Any] = {v: len(self.of(v))
                                  for v in (AGREEMENT, DIVERGENCE, NOT_COMPARABLE)}
        totals["records"] = len(records)
        return {"totals": totals, "records": [record.as_dict() for record in records]}

    @staticmethod
    def _brief(value: Optional[Mapping[str, Any]], limit: int = 400) -> str:
        """Elide an oversized value in the TEXT report only, marking how much was left
        out; :meth:`as_dict` always keeps the record whole."""
        text = str(dict(value or {}))
        return text if len(text) <= limit else f"{text[:limit]}...[{len(text)-limit} more chars]"

    def render(self) -> str:
        """The full human-readable report: agreements, divergences with their diffs, and
        every not-comparable case WITH its reason. Nothing is summarized away."""
        totals = self.as_dict()["totals"]
        lines = [f"comparison report: {totals['records']} record(s) -- " + ", ".join(
            f"{totals[v]} {v}" for v in (AGREEMENT, DIVERGENCE, NOT_COMPARABLE))]
        for record in self.records:
            lines.append(f"[{record.verdict}] {record.command} {dict(record.params)}")
            if record.verdict == NOT_COMPARABLE:
                lines.append(f"    reason: {record.reason}")
                continue
            if record.verdict == DIVERGENCE:
                diff = dict(record.diff or {})
                lines.append(f"    diverging fields: {diff.get('keys')}")
                lines.append(f"    old(ai_editor)  : {self._brief(record.old)}")
                lines.append(f"    new(tree_engine): {self._brief(record.new)}")
                for approved in record.approved_divergences:
                    lines.append(f"    approved divergence on record: {approved}")
            else:
                lines.append(f"    both engines   : {self._brief(record.new)}")
            for note in record.uncompared_fields:
                lines.append(f"    not compared   : {note}")
        return "\n".join(lines)


# -- enablement -------------------------------------------------------------

@dataclass(frozen=True)
class EnablementStrategy:
    """Configuration flags deciding whether a given call is compared at all.

    ``enabled`` is the global switch, ``per_command`` overrides it for one command, and
    ``sample_every`` compares one call in N (deterministically, by that command's own
    occurrence counter -- never randomly), so sampling can be enabled without doubling
    traffic for every operation."""

    enabled: bool = True
    per_command: Mapping[str, bool] = field(default_factory=dict)
    sample_every: int = 1

    def enabled_for(self, command: str, occurrence: int) -> bool:
        """``occurrence`` is 0-based and per command; the first call is always sampled."""
        if not self.per_command.get(command, self.enabled):
            return False
        return occurrence % max(int(self.sample_every), 1) == 0


# -- the mode --------------------------------------------------------------

class ComparisonMode:
    """Run each command on both engines and log where they diverge.

    The new engine is the primary side: its result (or its exception) reaches the caller
    exactly as :class:`MCPAdapter` produced it, and the legacy run happens on a worker
    thread, so the caller never blocks on the secondary side. :meth:`wait` joins the
    outstanding comparisons when a report is about to be read."""

    def __init__(self, adapter: Optional[MCPAdapter] = None, *,
                 strategy: EnablementStrategy = EnablementStrategy(),
                 log: Optional[DivergenceLog] = None,
                 normalizer: Optional[ResultNormalizer] = None,
                 legacy_runners: Mapping[str, Callable[[Mapping[str, Any]], Dict[str, Any]]]
                 = LEGACY_RUNNERS, max_workers: int = 1) -> None:
        self.adapter, self.strategy = adapter if adapter is not None else MCPAdapter(), strategy
        self.log = log if log is not None else DivergenceLog()
        self.normalizer = normalizer if normalizer is not None else ResultNormalizer()
        self._legacy = dict(legacy_runners)
        self._counters: Dict[str, Any] = {}
        self._counter_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers,
                                            thread_name_prefix="comparison-mode")
        self._pending: List[Future] = []

    def run(self, command: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Dispatch ``command`` on the new engine and return its result UNCHANGED.

        A primary-side exception is re-raised unchanged too, after the comparison has
        been scheduled with that exception as the new-side outcome."""
        compare = self.strategy.enabled_for(command, self._next_occurrence(command))
        try:
            primary = self.adapter.dispatch(command, params)
        except Exception as exc:
            if compare:
                self._schedule(command, params, self.normalizer.from_exception(exc))
            raise
        if compare:
            self._schedule(command, params, self._normalize_primary(command, primary))
        return primary

    def wait(self, timeout: Optional[float] = None) -> None:
        """Block until every scheduled comparison has been recorded -- what a caller
        does before reading the log, never something :meth:`run` does for it."""
        for future in list(self._pending):
            future.result(timeout)
        self._pending = [f for f in self._pending if not f.done()]

    def close(self) -> None:
        self.wait()
        self._executor.shutdown(wait=True)

    def __enter__(self) -> "ComparisonMode":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def _next_occurrence(self, command: str) -> int:
        with self._counter_lock:
            counter = self._counters.setdefault(command, itertools.count())
            return next(counter)

    def _normalize_primary(self, command: str, envelope: Mapping[str, Any]
                           ) -> Optional[Dict[str, Any]]:
        """``None`` marks "the new side itself is not comparable for this command"."""
        try:
            return self.normalizer.normalize(command, envelope)
        except NotComparable:
            return None

    def _schedule(self, command: str, params: Mapping[str, Any],
                  new_normalized: Optional[Mapping[str, Any]]) -> None:
        self._pending.append(
            self._executor.submit(self._compare, command, dict(params), new_normalized))

    def _compare(self, command: str, params: Mapping[str, Any],
                 new_normalized: Optional[Mapping[str, Any]]) -> None:
        """The secondary side: run the legacy engine and record the verdict."""
        spec = COMMAND_SPECS.get(command)
        approved = spec.divergences if spec is not None else ()
        uncompared = self.normalizer.uncompared(command)
        runner = self._legacy.get(command)
        if runner is None or new_normalized is None:
            reason = not_comparable_reasons().get(
                command, f"no in-process legacy runner is registered for {command!r}")
            self.log.add(ComparisonRecord(command, params, NOT_COMPARABLE, reason=reason,
                                          new=new_normalized, approved_divergences=approved))
            return
        try:
            old_normalized: Mapping[str, Any] = runner(params)
        except NotComparable as exc:
            self.log.add(ComparisonRecord(command, params, NOT_COMPARABLE, reason=exc.reason,
                                          new=new_normalized, approved_divergences=approved))
            return
        except Exception as exc:  # a legacy failure is an outcome, never swallowed
            old_normalized = self.normalizer.from_exception(exc)
        diff = CommandTrace(command=command, params=params, result=dict(new_normalized),
                            old_result=dict(old_normalized)).divergence()
        self.log.add(ComparisonRecord(
            command=command, params=params,
            verdict=AGREEMENT if diff is None else DIVERGENCE,
            old=old_normalized, new=new_normalized, diff=diff,
            uncompared_fields=uncompared, approved_divergences=approved))
