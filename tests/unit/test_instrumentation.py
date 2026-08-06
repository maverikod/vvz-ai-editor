"""Unit tests for tree_engine.core.instrumentation (G-028/T-001/A-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the optional per-phase measurement surface of the tree engine core
({p029}, {p030}) -- disabled-by-default inertness, the enable/disable/reset
lifecycle, per-phase and aggregate counter accuracy, the structural-marker
guarantee a benchmark gate relies on, the ``instrument`` decorator, and
thread safety under concurrent recording.

``instrumentation.py`` is process-global state. Every test here uses real
work -- real ``.py`` files under ``src/tree_engine/`` parsed with
``PythonFormatPlugin`` and queried with ``TreeQueryEngine`` -- so node
counts and timings are genuine, but only monotonic direction and
non-zero-ness are asserted, never a wall-clock magnitude. An autouse fixture
snapshots and restores the enabled flag and every counter around each test,
so the suite is order-independent under any run order.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from tree_engine.core import instrumentation as instr
from tree_engine.core.nodes import walk
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.query.engine import TreeQueryEngine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LARGE_SOURCE = _REPO_ROOT / "src" / "tree_engine" / "query" / "engine.py"
_SMALL_SOURCE = _REPO_ROOT / "src" / "tree_engine" / "errors.py"


def _load_document(path: Path):
    """Parse ``path`` with a fresh ``PythonFormatPlugin``: real source, real parse."""

    plugin = PythonFormatPlugin()
    document = plugin.parse_document(path.read_text(encoding="utf-8"))
    return document, plugin


@pytest.fixture(autouse=True)
def _restore_instrumentation_state():
    """Snapshot the enabled flag and every counter before each test and put both
    back exactly afterward, so tests never leak state into each other or into
    unrelated suites and the run order never matters."""

    was_enabled = instr.is_enabled()
    baseline = instr.query_counters(scope=instr.SCOPE_GLOBAL)
    yield
    instr.reset()
    instr.enable(reset_counters=False)
    for phase, counter in baseline.phases.items():
        if counter.invocations or counter.duration_ns or counter.affected_nodes or counter.changed_text:
            instr.record(phase, duration_ns=counter.duration_ns, affected_nodes=counter.affected_nodes,
                         changed_text=counter.changed_text, invocations=counter.invocations)
        for marker, count in counter.markers.items():
            for _ in range(count):
                instr.record(phase, invocations=0, markers=(marker,))
    if not was_enabled:
        instr.disable()


def test_counters_disabled_by_default_are_completely_inert():
    """While disabled, a ``measure`` scope and a ``record`` call leave every
    counter at zero, and re-enabling with ``reset_counters=False`` does not
    resurrect anything that was never actually recorded."""

    instr.disable()
    instr.reset()
    with instr.measure(instr.PHASE_QUERY, affected_nodes=5, changed_text="hi") as scope:
        scope.add_affected_nodes(3)
        scope.add_changed_text("more")
        scope.mark(instr.MARKER_FULL_PARSE)
    instr.record(instr.PHASE_SAVE, duration_ns=999, affected_nodes=9, changed_text=b"xyz")

    snapshot = instr.query_counters()
    assert snapshot.total("invocations") == 0
    assert snapshot.total("affected_nodes") == 0
    assert snapshot.total("changed_text") == 0
    assert snapshot.markers() == {}

    instr.enable(reset_counters=False)
    assert instr.query_counters().total("invocations") == 0


def test_enable_call_activates_and_is_idempotent():
    """One explicit ``enable()`` turns collection on; a second call while already
    enabled changes nothing observable, and ``reset_counters`` controls whether an
    earlier run's counters carry over."""

    instr.enable()
    instr.record(instr.PHASE_LOAD, duration_ns=10, affected_nodes=1)
    instr.enable(reset_counters=False)  # idempotent re-enable, explicit no-reset
    assert instr.is_enabled() is True
    assert instr.query_counters().total("invocations", phase=instr.PHASE_LOAD) == 1

    instr.enable()  # default reset_counters=True drops the carried-over count
    assert instr.is_enabled() is True
    assert instr.query_counters().total("invocations", phase=instr.PHASE_LOAD) == 0

    instr.disable()
    assert instr.is_enabled() is False


def test_counter_recording_all_phases():
    """Once enabled, each of the seven exposed phases records duration,
    affected-node count and changed-text volume independently of the others."""

    instr.enable()
    for index, phase in enumerate(instr.PHASES, start=1):
        with instr.measure(phase) as scope:
            scope.add_affected_nodes(index)
            scope.add_changed_text("x" * index)

    snapshot = instr.query_counters()
    for index, phase in enumerate(instr.PHASES, start=1):
        counter = snapshot.counter(phase)
        assert counter.invocations == 1
        assert counter.duration_ns > 0
        assert counter.affected_nodes == index
        assert counter.changed_text == index
    assert snapshot.total("invocations") == len(instr.PHASES)


def test_counters_accumulate_across_calls_and_reset_clears():
    """Repeated ``record`` calls on the same phase sum into one counter, and
    ``reset`` drops every counter of every thread back to zero."""

    instr.enable()
    for _ in range(4):
        instr.record(instr.PHASE_VALIDATE, duration_ns=100, affected_nodes=2, changed_text=5)
    counter = instr.query_counters().counter(instr.PHASE_VALIDATE)
    assert (counter.invocations, counter.duration_ns, counter.affected_nodes, counter.changed_text) == (
        4, 400, 8, 20,
    )
    instr.reset()
    cleared = instr.query_counters().counter(instr.PHASE_VALIDATE)
    assert cleared == instr.PhaseCounter(phase=instr.PHASE_VALIDATE)


def test_scope_thread_isolates_own_view_from_global():
    """``SCOPE_THREAD`` reports only the calling thread's own counters; only
    ``SCOPE_GLOBAL`` merges in what another thread recorded."""

    instr.enable()
    instr.record(instr.PHASE_SAVE, duration_ns=1, affected_nodes=1)  # this (main) thread

    other_recorded = threading.Event()
    release_other = threading.Event()

    def other_thread_work() -> None:
        instr.record(instr.PHASE_SAVE, duration_ns=2, affected_nodes=2)
        other_recorded.set()
        release_other.wait()

    worker = threading.Thread(target=other_thread_work)
    worker.start()
    try:
        other_recorded.wait(timeout=5)
        thread_view = instr.query_counters(phase=instr.PHASE_SAVE, scope=instr.SCOPE_THREAD)
        global_view = instr.query_counters(phase=instr.PHASE_SAVE, scope=instr.SCOPE_GLOBAL)
        assert thread_view.total("invocations") == 1
        assert thread_view.total("affected_nodes") == 1
        assert global_view.total("invocations") == 2
        assert global_view.total("affected_nodes") == 3
    finally:
        release_other.set()
        worker.join(timeout=5)


def test_counter_snapshot_delta_from_computes_true_difference():
    """``delta_from`` isolates exactly the work done between two snapshots,
    unaffected by whatever the counters already carried."""

    instr.enable()
    instr.record(instr.PHASE_INDEX_UPDATE, duration_ns=50, affected_nodes=4, changed_text=10)
    baseline = instr.query_counters()
    instr.record(instr.PHASE_INDEX_UPDATE, duration_ns=30, affected_nodes=1, changed_text=2)
    after = instr.query_counters()

    delta = after.delta_from(baseline)
    counter = delta.counter(instr.PHASE_INDEX_UPDATE)
    assert (counter.invocations, counter.duration_ns, counter.affected_nodes, counter.changed_text) == (
        1, 30, 1, 2,
    )


def test_single_operation_structural_guarantee():
    """A whole-document parse carries ``MARKER_FULL_PARSE`` and is correctly
    reported as non-local; a single targeted query on the same document carries
    no structural marker and is reported as local -- {p029}'s benchmark-gate
    assertion, exercised against a real parse and a real query."""

    instr.enable()
    document, plugin = _load_document(_LARGE_SOURCE)
    total_nodes = sum(1 for _ in walk(document.root))
    assert total_nodes > 0

    with instr.measure(instr.PHASE_PARSE, markers=(instr.MARKER_FULL_PARSE,)) as scope:
        scope.add_affected_nodes(total_nodes)  # a fresh parse touches every node

    engine = TreeQueryEngine(document, plugin)
    with instr.measure(instr.PHASE_QUERY) as scope:  # one targeted local lookup
        matches = engine.query("class")
        scope.add_affected_nodes(len(matches))
    assert len(matches) >= 1

    whole_document = instr.query_counters(phase=instr.PHASE_PARSE)
    local_operation = instr.query_counters(phase=instr.PHASE_QUERY)
    assert whole_document.is_local_operation() is False
    assert whole_document.structural_markers() == (instr.MARKER_FULL_PARSE,)
    assert local_operation.is_local_operation() is True
    assert local_operation.structural_markers() == ()


def test_counter_query_interface_accuracy():
    """``query_counters`` returns accurate per-phase and aggregate metrics for
    real, mixed-phase work: a real parse plus two real queries."""

    instr.enable()
    document, plugin = _load_document(_LARGE_SOURCE)
    engine = TreeQueryEngine(document, plugin)

    with instr.measure(instr.PHASE_PARSE) as scope:
        scope.add_affected_nodes(sum(1 for _ in walk(document.root)))
    with instr.measure(instr.PHASE_QUERY) as scope:
        functions = engine.query("function")
        scope.add_affected_nodes(len(functions))
    with instr.measure(instr.PHASE_QUERY) as scope:
        classes = engine.query("class")
        scope.add_affected_nodes(len(classes))
    assert functions and classes  # real file, real non-degenerate matches

    query_counter = instr.query_counters(phase=instr.PHASE_QUERY).counter(instr.PHASE_QUERY)
    assert query_counter.invocations == 2
    assert query_counter.affected_nodes == len(functions) + len(classes)

    aggregate = instr.query_counters()
    assert aggregate.total("invocations") == 3  # one parse, two query
    assert aggregate.total("invocations", phase=instr.PHASE_PARSE) == 1
    assert aggregate.total("affected_nodes") >= query_counter.affected_nodes


def test_instrument_decorator_preserves_behavior_and_records():
    """The ``instrument`` decorator records one invocation without changing the
    wrapped callable's return value, and still records -- and still propagates
    unchanged -- when the wrapped callable raises."""

    instr.enable()

    @instr.instrument(instr.PHASE_QUERY, markers=(instr.MARKER_FULL_TRAVERSAL,))
    def compute(a: int, b: int) -> int:
        return a + b

    assert compute(2, 3) == 5
    counter = instr.query_counters().counter(instr.PHASE_QUERY)
    assert counter.invocations == 1
    assert counter.markers.get(instr.MARKER_FULL_TRAVERSAL) == 1

    @instr.instrument(instr.PHASE_QUERY)
    def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        boom()
    counter_after = instr.query_counters().counter(instr.PHASE_QUERY)
    assert counter_after.invocations == 2  # the raising call is still counted


def test_measure_scope_closes_and_propagates_on_exception():
    """An exception raised inside a ``measure`` scope still closes the scope --
    recording what was reported before the raise -- and propagates unchanged."""

    class _BoomError(RuntimeError):
        pass

    instr.enable()
    with pytest.raises(_BoomError, match="kaboom"):
        with instr.measure(instr.PHASE_MUTATE) as scope:
            scope.add_affected_nodes(7)
            raise _BoomError("kaboom")

    counter = instr.query_counters().counter(instr.PHASE_MUTATE)
    assert counter.invocations == 1
    assert counter.affected_nodes == 7
    assert counter.duration_ns > 0


def test_thread_safety_of_enable_disable_and_recording():
    """8 threads x 500 measured scopes land exactly: 4000 invocations, 12000
    affected nodes, no lost updates -- while a concurrent reader thread merges
    every store *while the writers are still writing*, and a second thread
    hammers idempotent ``enable()``/``is_enabled()``. Nothing crashes."""

    instr.enable()
    threads_n, per_thread = 8, 500
    barrier = threading.Barrier(threads_n + 2)
    stop_reading = threading.Event()
    reader_errors: list = []

    def recorder() -> None:
        barrier.wait()
        for _ in range(per_thread):
            with instr.measure(instr.PHASE_MUTATE) as scope:
                scope.add_affected_nodes(1)
                scope.add_affected_nodes(1)
                scope.add_affected_nodes(1)

    def concurrent_reader() -> None:
        # Merges every store while the recorders are still writing them.
        barrier.wait()
        try:
            while not stop_reading.is_set():
                instr.query_counters(scope=instr.SCOPE_GLOBAL)
        except Exception as exc:  # pragma: no cover - only reachable with a broken lock
            reader_errors.append(exc)

    def flip_enable() -> None:
        barrier.wait()
        for _ in range(200):
            instr.enable(reset_counters=False)
            assert isinstance(instr.is_enabled(), bool)

    threads = [threading.Thread(target=recorder) for _ in range(threads_n)]
    threads.append(threading.Thread(target=flip_enable))
    reader = threading.Thread(target=concurrent_reader)
    threads.append(reader)
    for thread in threads:
        thread.start()
    for thread in threads:
        if thread is not reader:
            thread.join()
    stop_reading.set()
    reader.join()

    assert reader_errors == []  # a broken lock surfaces here as a live crash
    instr.enable(reset_counters=False)
    counter = instr.query_counters(phase=instr.PHASE_MUTATE).counter(instr.PHASE_MUTATE)
    assert counter.invocations == threads_n * per_thread == 4000
    assert counter.affected_nodes == threads_n * per_thread * 3 == 12000


def test_thread_store_add_is_lock_protected_against_lost_updates():
    """Normal use gives each store exactly one writer, so a genuine write-write
    race needs sharing one ``_ThreadStore`` across threads directly. This
    white-box check does that, proving ``add``'s lock -- not favorable
    scheduling -- is what the public exact-totals guarantee above rests on."""

    store = instr._ThreadStore()  # noqa: SLF001 - deliberate white-box access
    writers, per_writer = 6, 3000
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # force frequent GIL handoffs so interleaving is real, not lucky

    def hammer() -> None:
        for _ in range(per_writer):
            store.add(instr.PHASE_SAVE, 1, 1, 0, ())

    workers = [threading.Thread(target=hammer) for _ in range(writers)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    finally:
        sys.setswitchinterval(original_interval)
    assert store.phases[instr.PHASE_SAVE].invocations == writers * per_writer == 18000


@pytest.mark.timeout(180)
def test_real_parse_duration_is_nonzero_and_scales_with_work():
    """A real parse of a small real file against one roughly four times its size:
    both durations are non-zero, and more real work never measures as less time.

    This one really parses 60 files with libcst, so its wall clock tracks how
    loaded the machine is; it carries its own timeout instead of the suite
    default, which it exceeds under concurrent load while asserting nothing
    about elapsed time itself."""

    instr.enable()
    small_text = _SMALL_SOURCE.read_text(encoding="utf-8")
    large_text = _LARGE_SOURCE.read_text(encoding="utf-8")
    repeats = 30

    with instr.measure(instr.PHASE_PARSE) as scope:
        for _ in range(repeats):
            PythonFormatPlugin().parse_document(small_text)
        scope.add_affected_nodes(repeats)
    small_counter = instr.query_counters().counter(instr.PHASE_PARSE)

    instr.reset()
    instr.enable()
    with instr.measure(instr.PHASE_PARSE) as scope:
        for _ in range(repeats):
            PythonFormatPlugin().parse_document(large_text)
        scope.add_affected_nodes(repeats)
    large_counter = instr.query_counters().counter(instr.PHASE_PARSE)

    assert small_counter.duration_ns > 0
    assert large_counter.duration_ns > 0
    assert large_counter.duration_ns > small_counter.duration_ns
