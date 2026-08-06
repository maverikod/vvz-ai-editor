"""Reality checks for ``adapter.comparison`` (G-029/T-001/A-006, C-023).

``ComparisonMode`` runs each command on BOTH the new engine (primary,
via a real :class:`adapter.mcp_adapter.MCPAdapter`) and the legacy
in-process ``ai_editor`` engine (secondary, on a background worker), and
records where they disagree. This suite drives both sides for real: no
mock of either engine. The only fakes used are small, purpose-built
legacy RUNNER callables -- plain functions matching the
``LEGACY_RUNNERS`` signature -- and only for the two cases that need a
controlled, deterministic outcome the real legacy engine cannot be
coaxed into on demand: an injected difference and a one-sided failure
(each test that uses one says so). Every other test runs the real
``MCPAdapter`` against the real ``ai_editor`` package.

Several tests pin genuine, currently-measured engine differences as the
truth of record, not as bugs: a ``function``/``class`` search agrees with
legacy on ``total`` and ``kind_counts`` but the new engine reports EMPTY
names where legacy reports real identifiers; the ``*`` selector finds
more nodes on the new engine and uses a different kind vocabulary
(legacy's ``import``/``decorator``/``stmt``/``smallstmt`` do not exist on
the new side, which reports ``""`` for anything with no semantic role);
and ``QueryMatch.range`` is always null. If a future change to either
engine narrows or removes one of these gaps, the corresponding assertion
below is exactly what will fail and prompt this file to be updated.

Cost note: the real legacy engine is ``ai_editor.tree.handlers
.python_handler.PythonHandler`` (LibCST) and ``ai_editor.cst_query
.executor.query_source`` -- the cheap entry points ``comparison.py``
itself already chose, not the slow ``PythonHandler.parse_content`` path.
The corpus below is one ~12-line module. Importing ``ai_editor`` the
first time costs about a second (module import, not parsing); every
call after that is millisecond-scale.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Mapping

import pytest

from adapter.mcp_adapter import AdapterContractError, MCPAdapter
from adapter.comparison import (
    AGREEMENT,
    DIVERGENCE,
    LEGACY_RUNNERS,
    NOT_COMPARABLE,
    ComparisonMode,
    EnablementStrategy,
)

#: One real, independently written Python module exercising an import, a
#: decorator, a module-level function, a class and a method -- enough to
#: make the new-vs-legacy selector-kind vocabulary genuinely diverge.
SOURCE = (
    "import os\n"
    "\n\n"
    "@staticmethod\n"
    "def helper():\n"
    "    return 1\n"
    "\n\n"
    "class Widget:\n"
    '    """A widget."""\n'
    "\n"
    "    def render(self):\n"
    "        return helper()\n"
)


@pytest.fixture
def probe_file(tmp_path: Path) -> str:
    path = tmp_path / "probe.py"
    path.write_text(SOURCE, encoding="utf-8")
    return str(path)


def _fake_legacy_success(_params: Mapping[str, Any]) -> Dict[str, Any]:
    """Purpose-built fake legacy RUNNER: always reports a successful,
    byte-identical round trip. Used only for the one-sided-failure case,
    where the real legacy engine has no way to succeed on a file that
    does not exist."""
    return {"byte_identical": True}


def _fake_legacy_failure(_params: Mapping[str, Any]) -> Dict[str, Any]:
    """Purpose-built fake legacy RUNNER: always raises. Used only for the
    injected secondary-failure cases below, so the failure is
    deterministic rather than depending on some real corpus defect."""
    raise RuntimeError("legacy exploded")


# -- identical results: real engines, real agreement -------------------------

def test_identical_results_no_divergence(probe_file):
    # universal_file_write's legacy counterpart is a pure mark/unmark
    # round trip on the SAME bytes; both engines genuinely agree here.
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.wait(timeout=5)
        records = mode.log.records
    assert len(records) == 1
    assert records[0].verdict == AGREEMENT
    assert records[0].old == {"byte_identical": True}
    assert records[0].new == {"byte_identical": True}
    assert records[0].diff is None


# -- differing results: real divergence, names empty vs real -----------------

def test_differing_results_divergence_record(probe_file):
    # Real, measured truth: a 'function' search agrees with legacy on
    # total and kind_counts but the new engine's name is "" where legacy
    # reports the real identifier "helper".
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        mode.wait(timeout=5)
        records = mode.log.records
    assert len(records) == 1
    record = records[0]
    assert record.verdict == DIVERGENCE
    assert record.old == {"total": 1, "kind_counts": {"function": 1}, "names": ["helper"]}
    assert record.new == {"total": 1, "kind_counts": {"function": 1}, "names": [""]}
    assert record.diff["keys"] == ["names"]


# -- primary result: unchanged and returned by identity -----------------------

class _RecordingAdapter:
    """Wraps the REAL adapter only to capture the exact object identity
    of what ``dispatch`` produced, so the test can prove ``run`` hands
    back that same object rather than a copy. Not a fake of the engine:
    every call is delegated to a real ``MCPAdapter``."""

    def __init__(self) -> None:
        self._real = MCPAdapter()
        self.last: Any = None

    def dispatch(self, command: str, params: Mapping[str, Any]) -> Any:
        self.last = self._real.dispatch(command, params)
        return self.last


def test_primary_result_returned_unchanged(probe_file):
    recorder = _RecordingAdapter()
    with ComparisonMode(adapter=recorder,
                        strategy=EnablementStrategy(enabled=True)) as mode:
        # A command that DOES diverge (see previous test): even so, what
        # comes back from run() is the adapter's own object, by identity.
        result = mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        assert result is recorder.last
        mode.wait(timeout=5)
    assert result["success"] is True
    assert result["data"]["total"] == 1


# -- sampling gate -------------------------------------------------------------

def test_sampling_gate_controls_secondary_execution(probe_file):
    strategy = EnablementStrategy(enabled=True, sample_every=2)
    with ComparisonMode(strategy=strategy) as mode:
        for _ in range(3):  # occurrences 0, 1, 2 -> only 0 and 2 are sampled
            mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.wait(timeout=5)
        records = mode.log.records
    assert len(records) == 2


# -- per-command gate ------------------------------------------------------

def test_per_command_enablement_gate(probe_file):
    strategy = EnablementStrategy(enabled=True,
                                  per_command={"universal_file_write": False})
    with ComparisonMode(strategy=strategy) as mode:
        mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        mode.wait(timeout=5)
        records = mode.log.records
    assert [r.command for r in records] == ["universal_file_search"]


def test_global_enablement_off_records_nothing(probe_file):
    with ComparisonMode(strategy=EnablementStrategy(enabled=False)) as mode:
        mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        mode.wait(timeout=5)
        records = mode.log.records
    assert records == ()


# -- secondary-engine failure: recorded, primary unharmed --------------------

def test_secondary_engine_failure_recorded_as_divergence(probe_file):
    runners = {"universal_file_write": _fake_legacy_failure}
    with ComparisonMode(strategy=EnablementStrategy(enabled=True),
                        legacy_runners=runners) as mode:
        mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.wait(timeout=5)
        records = mode.log.records
    assert len(records) == 1
    assert records[0].verdict == DIVERGENCE
    assert records[0].old == {"error": "RuntimeError: legacy exploded"}
    assert records[0].new == {"byte_identical": True}


def test_secondary_failure_never_breaks_primary(probe_file):
    runners = {"universal_file_write": _fake_legacy_failure}
    with ComparisonMode(strategy=EnablementStrategy(enabled=True),
                        legacy_runners=runners) as mode:
        result = mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        mode.wait(timeout=5)  # the legacy exception must not propagate here either
    assert result["success"] is True
    assert result["data"]["byte_identical"] is True


def test_primary_failure_with_secondary_success_is_one_sided_divergence(tmp_path):
    # The new side fails for real (missing source file -> STORAGE_IO_ERROR
    # envelope, no exception raised). The real legacy write would also
    # fail on a missing file, so a fake success runner forces the OTHER
    # side of the one-sided case: new fails, legacy "succeeds".
    missing = str(tmp_path / "does_not_exist.py")
    runners = {"universal_file_write": _fake_legacy_success}
    with ComparisonMode(strategy=EnablementStrategy(enabled=True),
                        legacy_runners=runners) as mode:
        result = mode.run("universal_file_write", {"file_path": missing})
        mode.wait(timeout=5)
        records = mode.log.records
    assert result["success"] is False
    assert len(records) == 1
    assert records[0].verdict == DIVERGENCE
    assert records[0].old == {"byte_identical": True}
    assert records[0].new == {"error": "STORAGE_IO_ERROR"}


# -- what a divergence record carries -----------------------------------------

def test_divergence_record_carries_command_name(probe_file):
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        mode.wait(timeout=5)
        record = mode.log.records[0]
    assert record.command == "universal_file_search"


def test_divergence_record_carries_inputs(probe_file):
    params = {"file_path": probe_file, "query": "function"}
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_search", dict(params))
        mode.wait(timeout=5)
        record = mode.log.records[0]
    assert dict(record.params) == params


def test_divergence_record_carries_both_outputs(probe_file):
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_search", {"file_path": probe_file, "query": "function"})
        mode.wait(timeout=5)
        record = mode.log.records[0]
    assert record.old is not None and record.new is not None
    assert record.old != record.new  # the whole reason it is a divergence


# -- pinned engine realities: wildcard vocabulary, null range ----------------

def test_wildcard_selector_more_nodes_and_kind_vocabulary_diverges(probe_file):
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_search", {"file_path": probe_file, "query": "*"})
        mode.wait(timeout=5)
        record = mode.log.records[0]
    assert record.verdict == DIVERGENCE
    assert record.new["total"] > record.old["total"], (
        "the new engine is currently measured to surface MORE nodes for '*' "
        "than the legacy selector; if this stops holding, the engines' "
        "traversal populations have converged and this pin must be updated"
    )
    legacy_only_kinds = {"import", "decorator", "stmt", "smallstmt"}
    assert legacy_only_kinds <= set(record.old["kind_counts"])
    assert legacy_only_kinds.isdisjoint(record.new["kind_counts"])
    assert "" in record.new["kind_counts"] and "" not in record.old["kind_counts"]


def test_query_match_range_is_null(probe_file):
    # Not reached through the comparison mode's normalized shape (range is
    # deliberately uncompared -- see ResultNormalizer.UNCOMPARED) but this
    # is the raw new-engine payload comparison mode normalizes away from,
    # pinned directly so the gap is visible.
    adapter = MCPAdapter()
    result = adapter.universal_file_search(probe_file, query="function")
    assert result["data"]["matches"][0]["range"] is None


# -- off the caller's critical path -------------------------------------------

def _gate_delayed(real_runner, gate: threading.Event):
    """Wrap a REAL legacy runner so it blocks on ``gate`` before doing its
    real work. This fakes no outcome -- the real runner still runs and
    its real result is still what gets recorded -- it only makes the
    background thread's timing deterministic, so the "off the critical
    path" guarantee below can be proven structurally instead of raced."""

    def wrapped(params: Mapping[str, Any]) -> Dict[str, Any]:
        gate.wait(timeout=5)
        return real_runner(params)

    return wrapped


def test_run_returns_before_legacy_finishes_and_wait_joins(probe_file):
    gate = threading.Event()
    runners = {"universal_file_write": _gate_delayed(
        LEGACY_RUNNERS["universal_file_write"], gate)}
    with ComparisonMode(strategy=EnablementStrategy(enabled=True),
                        legacy_runners=runners) as mode:
        mode.run("universal_file_write", {"file_path": probe_file, "content": SOURCE})
        # run() has returned; the background comparison is parked on the
        # gate and cannot have recorded anything yet -- this is the "off
        # the critical path" guarantee, proven structurally rather than
        # by a timing race.
        assert mode.log.records == ()
        gate.set()
        mode.wait(timeout=5)
        assert len(mode.log.records) == 1
        assert mode.log.records[0].verdict == AGREEMENT


# -- NOT_COMPARABLE carries a real reason -------------------------------------

def test_not_comparable_carries_a_real_reason(probe_file):
    # universal_file_preview has no in-process legacy counterpart at all
    # (see adapter.comparison.NOT_COMPARABLE_COMMANDS): a real, named
    # reason, never a swallowed or generic one.
    with ComparisonMode(strategy=EnablementStrategy(enabled=True)) as mode:
        mode.run("universal_file_preview",
                 {"file_path": probe_file, "select": "function", "depth": 0})
        mode.wait(timeout=5)
        record = mode.log.records[0]
    assert record.verdict == NOT_COMPARABLE
    assert record.reason and "PreviewNavigation" in record.reason


# -- unknown command -----------------------------------------------------------

def test_unknown_command_raises_adapter_contract_error():
    # Comparison mode's default strategy is enabled, so it still tries to
    # schedule a comparison for the failed dispatch -- but the exception
    # reaches the caller regardless, and the command being unknown to
    # LEGACY_RUNNERS too makes that scheduled comparison NOT_COMPARABLE
    # with a real reason, never a silent drop.
    with ComparisonMode() as mode:
        with pytest.raises(AdapterContractError):
            mode.run("no_such_command", {})
        mode.wait(timeout=5)
        records = mode.log.records
    assert len(records) == 1
    assert records[0].verdict == NOT_COMPARABLE
    assert "no_such_command" in records[0].reason
