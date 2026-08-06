"""Optional per-phase instrumentation for the tree engine (C-022, {p030}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the engine's optional measurement surface and nothing else. Per invocation
of one of the seven exposed phase boundaries -- ``load``, ``parse``, ``query``,
``mutate``, ``index-update``, ``validate``, ``save`` -- it records wall-clock
duration, affected-node count, and changed-text volume, plus structural markers.
Per {p030} collection is DISABLED BY DEFAULT, turned on by one explicit
:func:`enable` call.

Zero cost when disabled: :func:`measure` returns a shared stateless no-op scope
whose methods do nothing -- no clock read, no per-call allocation, no storage
touched -- and :func:`record` returns at once. The only work left on the disabled
path is one frozenset test on the phase name.

Thread safety: every write goes into a per-thread store, so instrumented threads
never contend for one counter and no update can be lost. Each store carries its
own lock, held only for the statements updating its integers, so a reader merging
the stores never observes a half-updated dict. Stores live in a process-wide list
guarded by ``_REGISTRY_LOCK``; totals read once the writing threads joined are
exactly the sum of what those threads did.

Observation never mutates the observed: this module holds no reference to any
``Document`` or ``Node`` and only accumulates integers handed to it, so node
identity, ``document_version``, and rendered bytes cannot be affected by it.
Standard library only: no ``ai_editor`` import, no parser library ({p003}).

Benchmark gate ({p029}): an invocation may carry :data:`MARKER_FULL_TRAVERSAL`,
:data:`MARKER_FULL_PARSE`, or :data:`MARKER_FULL_INDEX_REBUILD`. The gate
snapshots before and after a single local operation, subtracts with
:meth:`CounterSnapshot.delta_from`, then asserts
:meth:`CounterSnapshot.is_local_operation`.

Source-of-truth requirement labels honored here: {p029}, {p030}.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import wraps
from time import perf_counter_ns
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = [
    "PHASE_LOAD", "PHASE_PARSE", "PHASE_QUERY", "PHASE_MUTATE", "PHASE_INDEX_UPDATE",
    "PHASE_VALIDATE", "PHASE_SAVE", "PHASES", "MARKER_FULL_TRAVERSAL", "MARKER_FULL_PARSE",
    "MARKER_FULL_INDEX_REBUILD", "STRUCTURAL_MARKERS", "SCOPE_GLOBAL", "SCOPE_THREAD",
    "METRICS", "PhaseCounter", "CounterSnapshot", "enable", "disable", "is_enabled",
    "reset", "measure", "record", "instrument", "query_counters",
]

PHASE_LOAD, PHASE_PARSE, PHASE_QUERY = "load", "parse", "query"
PHASE_MUTATE, PHASE_INDEX_UPDATE = "mutate", "index-update"
PHASE_VALIDATE, PHASE_SAVE = "validate", "save"

#: Every phase boundary the engine exposes for measurement ({p030}).
PHASES: Tuple[str, ...] = (PHASE_LOAD, PHASE_PARSE, PHASE_QUERY, PHASE_MUTATE,
                           PHASE_INDEX_UPDATE, PHASE_VALIDATE, PHASE_SAVE)
_PHASE_SET = frozenset(PHASES)
_PHASE_ORDER = {name: position for position, name in enumerate(PHASES)}

#: The per-invocation metrics of {p030}; the names :meth:`CounterSnapshot.total` takes.
METRICS: Tuple[str, ...] = ("invocations", "duration_ns", "affected_nodes", "changed_text")

MARKER_FULL_TRAVERSAL, MARKER_FULL_PARSE = "full-traversal", "full-parse"
MARKER_FULL_INDEX_REBUILD = "full-index-rebuild"

#: The three markers a single local operation must never raise ({p029}).
STRUCTURAL_MARKERS: Tuple[str, ...] = (MARKER_FULL_TRAVERSAL, MARKER_FULL_PARSE,
                                       MARKER_FULL_INDEX_REBUILD)

SCOPE_GLOBAL, SCOPE_THREAD = "global", "thread"

_EMPTY: Mapping[str, Any] = MappingProxyType({})

_ENABLED = False
_LOCAL = threading.local()
_STORES: List["_ThreadStore"] = []
_REGISTRY_LOCK = threading.Lock()


def _check_phase(phase: str) -> None:  # reject a phase the engine does not expose
    if phase not in _PHASE_SET:
        raise ValueError(f"unknown instrumentation phase {phase!r}; expected one of {PHASES}")


def _text_volume(value: Any) -> int:
    """Changed-text volume of ``value`` in bytes: ``None`` is zero, a ``str`` gives
    its UTF-8 length, ``bytes``-like data its length, an ``int`` is already a volume."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError(f"cannot measure changed-text volume of {type(value).__name__}")


class _PhaseAccumulator:
    """Mutable per-phase totals; never touched without the owning store's lock."""

    __slots__ = ("invocations", "duration_ns", "affected_nodes", "changed_text", "markers")

    def __init__(self) -> None:
        self.invocations = self.duration_ns = self.affected_nodes = self.changed_text = 0
        self.markers: Dict[str, int] = {}

    def absorb(self, other: "_PhaseAccumulator") -> None:
        """Add another accumulator's totals into this one, marker counts included."""
        self.invocations += other.invocations
        self.duration_ns += other.duration_ns
        self.affected_nodes += other.affected_nodes
        self.changed_text += other.changed_text
        for marker, count in other.markers.items():
            self.markers[marker] = self.markers.get(marker, 0) + count

    def to_counter(self, phase: str) -> "PhaseCounter":  # freeze into an immutable counter
        return PhaseCounter(phase, self.invocations, self.duration_ns, self.affected_nodes,
                            self.changed_text, MappingProxyType(dict(self.markers)))


class _ThreadStore:
    """One writing thread's private counters plus the lock a reader must take. It is
    uncontended in the common case -- only the owning thread writes -- and
    :meth:`merge_into` takes it so a snapshot never iterates a resizing dict."""

    __slots__ = ("lock", "phases")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.phases: Dict[str, _PhaseAccumulator] = {}

    def add(self, phase: str, duration_ns: int, affected_nodes: int, changed_text: int,
            markers: Iterable[str], invocations: int = 1) -> None:  # one recorded invocation
        with self.lock:
            accumulator = self.phases.get(phase)
            if accumulator is None:
                accumulator = _PhaseAccumulator()
                self.phases[phase] = accumulator
            accumulator.invocations += invocations
            accumulator.duration_ns += duration_ns
            accumulator.affected_nodes += affected_nodes
            accumulator.changed_text += changed_text
            for marker in markers:
                accumulator.markers[marker] = accumulator.markers.get(marker, 0) + 1

    def merge_into(self, target: Dict[str, _PhaseAccumulator]) -> None:
        """Add this store's totals into ``target``, under this store's own lock."""
        with self.lock:
            for phase, accumulator in self.phases.items():
                destination = target.get(phase)
                if destination is None:
                    destination = _PhaseAccumulator()
                    target[phase] = destination
                destination.absorb(accumulator)

    def clear(self) -> None:  # Drop this store's counters.
        with self.lock:
            self.phases.clear()


def _current_store() -> _ThreadStore:  # this thread's store, registered on first use
    store = getattr(_LOCAL, "store", None)
    if store is None:
        store = _ThreadStore()
        with _REGISTRY_LOCK:
            _STORES.append(store)
        _LOCAL.store = store
    return store


@dataclass(frozen=True)
class PhaseCounter:
    """Immutable totals for one phase: summed nanoseconds, summed affected-node count,
    summed changed-text bytes, and how many invocations raised each marker."""

    phase: str
    invocations: int = 0
    duration_ns: int = 0
    affected_nodes: int = 0
    changed_text: int = 0
    markers: Mapping[str, int] = _EMPTY


def _freeze(counters: Dict[str, PhaseCounter]) -> Mapping[str, PhaseCounter]:  # read-only
    ordered = sorted(counters.items(), key=lambda item: _PHASE_ORDER.get(item[0], len(PHASES)))
    return MappingProxyType(dict(ordered))


@dataclass(frozen=True)
class CounterSnapshot:
    """An immutable read of the counters: ``phases`` maps a phase name to its
    :class:`PhaseCounter`. A phase never recorded is absent, and :meth:`counter`
    returns a zeroed counter for it, so a caller never tests membership."""

    phases: Mapping[str, PhaseCounter] = _EMPTY

    def counter(self, phase: str) -> PhaseCounter:  # zeroed when never recorded
        _check_phase(phase)
        return self.phases.get(phase, PhaseCounter(phase=phase))

    def total(self, metric: str, phase: Optional[str] = None) -> int:
        """Sum one of :data:`METRICS` over ``phase``, or over every phase."""
        if metric not in METRICS:
            raise ValueError(f"unknown metric {metric!r}; expected one of {METRICS}")
        if phase is not None:
            return int(getattr(self.counter(phase), metric))
        return sum(int(getattr(counter, metric)) for counter in self.phases.values())

    def markers(self, phase: Optional[str] = None) -> Mapping[str, int]:  # merged if no phase
        if phase is not None:
            return self.counter(phase).markers
        merged: Dict[str, int] = {}
        for counter in self.phases.values():
            for marker, count in counter.markers.items():
                merged[marker] = merged.get(marker, 0) + count
        return MappingProxyType(merged)

    def structural_markers(self, phase: Optional[str] = None) -> Tuple[str, ...]:
        """Which of :data:`STRUCTURAL_MARKERS` this snapshot carries, in declared order."""
        present = self.markers(phase)
        return tuple(marker for marker in STRUCTURAL_MARKERS if present.get(marker, 0) > 0)

    def is_local_operation(self, phase: Optional[str] = None) -> bool:
        """True when no full-traversal, full-parse, or full-index-rebuild marker
        was raised -- the structural assertion of {p029}."""
        return not self.structural_markers(phase)

    def delta_from(self, baseline: "CounterSnapshot") -> "CounterSnapshot":
        """This snapshot minus ``baseline``, so the gate isolates exactly one operation
        from counters already carrying earlier work; unmoved phases are dropped."""
        result: Dict[str, PhaseCounter] = {}
        for phase, counter in self.phases.items():
            old = baseline.phases.get(phase, PhaseCounter(phase=phase))
            markers = {marker: count - old.markers.get(marker, 0)
                       for marker, count in counter.markers.items()
                       if count > old.markers.get(marker, 0)}
            values = {metric: getattr(counter, metric) - getattr(old, metric)
                      for metric in METRICS}
            if markers or any(values.values()):
                result[phase] = PhaseCounter(phase, **values, markers=MappingProxyType(markers))
        return CounterSnapshot(_freeze(result))


def _noop(*args: Any, **kwargs: Any) -> None:
    """The disabled-path no-op shared by every :class:`_NullScope` reporting method."""


class _NullScope:
    """The shared stateless scope returned while collection is disabled: every
    reporting method is :func:`_noop` and the instance carries no per-call state, so
    one object is safely shared by every thread and nothing is allocated."""

    __slots__ = ()
    add_affected_nodes = _noop
    add_changed_text = _noop
    mark = _noop

    def __enter__(self) -> "_NullScope":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        return None


_NULL_SCOPE = _NullScope()


class _ActiveScope:
    """A live measurement of one phase invocation. The clock starts in ``__enter__``
    and the record is written in ``__exit__`` -- including when the body raised, so a
    failed phase is still counted. Nested scopes are allowed; an outer scope's
    duration includes its inner scopes."""

    __slots__ = ("_phase", "_nodes", "_text", "_markers", "_start")

    def __init__(self, phase: str, nodes: int, text: int, markers: List[str]) -> None:
        self._phase = phase
        self._nodes = nodes
        self._text = text
        self._markers = markers
        self._start = 0

    def __enter__(self) -> "_ActiveScope":
        self._start = perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        duration = perf_counter_ns() - self._start
        _current_store().add(self._phase, duration, self._nodes, self._text, self._markers)

    def add_affected_nodes(self, count: int = 1) -> None:  # this invocation touched more nodes
        self._nodes += int(count)

    def add_changed_text(self, value: Any) -> None:  # int, str, or bytes; see _text_volume
        self._text += _text_volume(value)

    def mark(self, *markers: str) -> None:  # raise structural markers on this invocation
        self._markers.extend(markers)


def enable(*, reset_counters: bool = True) -> None:
    """Turn collection on -- the single explicit call of {p030}; ``reset_counters``
    clears what an earlier run left behind."""
    global _ENABLED
    if reset_counters:
        reset()
    _ENABLED = True


def disable() -> None:
    """Turn collection off, restoring the no-op fast path. Counters already collected
    are kept; call :func:`reset` to drop them."""
    global _ENABLED
    _ENABLED = False


def is_enabled() -> bool:  # True while collection is on
    return _ENABLED


def reset() -> None:  # drop every counter of every thread; the enabled state is untouched
    with _REGISTRY_LOCK:
        stores = list(_STORES)
    for store in stores:
        store.clear()


def measure(phase: str, *, affected_nodes: int = 0, changed_text: Any = None,
            markers: Iterable[str] = ()) -> Any:
    """A context manager measuring one invocation of ``phase``. While disabled it is
    the shared no-op scope, allocating nothing and reading no clock; while enabled it
    times the block and takes ``add_affected_nodes``, ``add_changed_text`` and
    ``mark`` as the block runs, so a caller reports what it touched once it knows."""
    if phase not in _PHASE_SET:
        _check_phase(phase)
    if not _ENABLED:
        return _NULL_SCOPE
    return _ActiveScope(phase, int(affected_nodes), _text_volume(changed_text), list(markers))


def record(phase: str, *, duration_ns: int = 0, affected_nodes: int = 0, changed_text: Any = None,
           markers: Iterable[str] = (), invocations: int = 1) -> None:
    """Record one already-measured invocation of ``phase``, for a caller that timed it
    itself; ``invocations=0`` raises markers only. A no-op while disabled."""
    if phase not in _PHASE_SET:
        _check_phase(phase)
    if not _ENABLED:
        return
    _current_store().add(phase, int(duration_ns), int(affected_nodes),
                         _text_volume(changed_text), tuple(markers), int(invocations))


def instrument(phase: str, *, markers: Iterable[str] = ()) -> Callable[[Callable], Callable]:
    """Decorator wrapping a callable as one invocation of ``phase``, so the benchmark
    suite or gate can attach instrumentation to an existing entry point without
    editing it. While disabled the wrapper calls straight through."""
    _check_phase(phase)
    fixed = tuple(markers)

    def decorator(function: Callable) -> Callable:
        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return function(*args, **kwargs)
            with _ActiveScope(phase, 0, 0, list(fixed)):
                return function(*args, **kwargs)
        return wrapper

    return decorator


def query_counters(*, phase: Optional[str] = None, scope: str = SCOPE_GLOBAL) -> CounterSnapshot:
    """An immutable snapshot of the counters. ``scope`` is :data:`SCOPE_GLOBAL` (every
    thread's counters merged, the default) or :data:`SCOPE_THREAD` (only the calling
    thread's, what a structural assertion should use while other threads work);
    ``phase`` narrows it to one phase. Callable enabled or not."""
    if phase is not None:
        _check_phase(phase)
    if scope == SCOPE_THREAD:
        stores = [_current_store()]
    elif scope == SCOPE_GLOBAL:
        with _REGISTRY_LOCK:
            stores = list(_STORES)
    else:
        raise ValueError(
            f"unknown counter scope {scope!r}; expected {SCOPE_GLOBAL!r} or {SCOPE_THREAD!r}")
    merged: Dict[str, _PhaseAccumulator] = {}
    for store in stores:
        store.merge_into(merged)
    counters = {name: accumulator.to_counter(name) for name, accumulator in merged.items()
                if phase is None or name == phase}
    return CounterSnapshot(_freeze(counters))
