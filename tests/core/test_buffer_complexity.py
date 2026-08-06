"""Cost and scaling tests for concept C-005: the piece-table ``SourceBuffer``
(``src/tree_engine/core/buffer.py``) and the lazy offset index /
``subtree_bytes`` aggregate layered on top of it
(``src/tree_engine/core/positions.py``).

These tests measure operation COST, not correctness -- a sibling test file
already covers round-trip correctness. Neither module ships built-in
operation counters, and this file must not modify either module, so two
measurement techniques are used instead, both robust on a shared or loaded
machine:

* structural spying: wrapping (via ``monkeypatch``) the exact function/
  method each module's own docstring names as the sole O(document size) or
  O(position count) entry point -- ``LazyOffsetIndex.full_resync`` (the only
  sanctioned full traversal, {p016}) and the module-level
  ``_apply_edit_to_span`` (invoked once per replayed edit record inside
  ``LazyOffsetIndex.resolve``, so its call count IS the shifted-range-entry
  count) -- plus direct inspection of ``SourceBuffer``'s own piece list and
  of the ``touched`` tuple ``SubtreeBytesAggregate.apply_delta`` returns.
  These give exact, deterministic counts with no timing noise at all.
* wall-clock ratio comparisons across a LARGE size difference (20KB vs 2MB
  documents, or 1k vs 50k tracked positions), asserted with a generous
  margin -- never a fixed millisecond budget, which a loaded machine could
  fail for reasons unrelated to the code under test.
"""

from __future__ import annotations

import time

import pytest

import tree_engine.core.positions as positions_mod
from tree_engine.core.buffer import SourceBuffer
from tree_engine.core.positions import (
    FullReindexReason,
    LazyOffsetIndex,
    PositionIndex,
    SubtreeBytesAggregate,
)

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

SMALL_SIZE = 20_000
LARGE_SIZE = 2_000_000
EDITS_PER_TRIAL = 300
EDIT_BASE = 4_000
EDIT_STEP = 32
REMOVED_SPAN = 4
FRAGMENT = b"<<EDIT>>"  # 8 bytes; net length delta per edit is +4


def _make_source(size: int) -> bytes:
    """Deterministic, cheaply generated source content of exactly ``size``
    bytes. Content is irrelevant to these tests, only its length."""
    pattern = b"abcdefgh"
    return (pattern * (size // len(pattern) + 1))[:size]


def _apply_edit_script(buffer: SourceBuffer, n_edits: int) -> None:
    """Apply ``n_edits`` small, non-overlapping local edits at a fixed,
    document-size-independent set of absolute positions near the start of
    the buffer. Because the positions do not depend on the buffer's total
    length, the exact same piece-table transformation happens regardless of
    how large the surrounding document is."""
    for i in range(n_edits):
        start = EDIT_BASE + i * EDIT_STEP
        buffer.apply_edit(start, start + REMOVED_SPAN, FRAGMENT, node_path=("root", f"n{i}"))


def _fastest_of(fn, repeats: int = 5) -> float:
    """Minimum wall-clock time over several trials. Minimum (not mean) is
    used deliberately: scheduler/GC jitter can only add delay, never
    subtract it, so the minimum is the best available estimate of the
    operation's true cost."""
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        if dt < best:
            best = dt
    return best


def _spy(monkeypatch, target, name: str) -> dict:
    """Wrap ``target.name`` with a call-counting shim, without touching the
    defining module's source. Works for bound methods on an instance and
    for module-level functions alike, since both are ordinary attributes."""
    original = getattr(target, name)
    calls = {"n": 0}

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, wrapper)
    return calls


# --------------------------------------------------------------------------
# 1. single-edit-batch cost vs. total document size
# --------------------------------------------------------------------------


def test_single_edit_cost_scales_with_fragment_size():
    """Verified: applying the identical 300-edit script costs the same at
    20KB and at 2MB (a 100x size gap). ``SourceBuffer.apply_edit`` only
    touches pieces overlapping the edit; a freshly loaded buffer starts as
    ONE piece regardless of its byte length, so neither the piece-count
    growth nor the wall-clock cost of a fixed edit script should depend on
    total document size."""
    small_source = _make_source(SMALL_SIZE)
    large_source = _make_source(LARGE_SIZE)

    small_buf = SourceBuffer(small_source)
    _apply_edit_script(small_buf, EDITS_PER_TRIAL)
    large_buf = SourceBuffer(large_source)
    _apply_edit_script(large_buf, EDITS_PER_TRIAL)

    # Exact structural evidence, no timing involved: each of the 300
    # non-overlapping edits nets exactly +2 pieces (left remainder +
    # inserted fragment, replacing the single piece it split), regardless
    # of how large the untouched remainder piece is. White-box read of the
    # buffer's own piece list -- introspection only, not a modification.
    expected_pieces = 2 * EDITS_PER_TRIAL + 1
    assert len(small_buf._pieces) == expected_pieces
    assert len(large_buf._pieces) == expected_pieces

    def run_small():
        buf = SourceBuffer(small_source)
        _apply_edit_script(buf, EDITS_PER_TRIAL)

    def run_large():
        buf = SourceBuffer(large_source)
        _apply_edit_script(buf, EDITS_PER_TRIAL)

    run_small()  # warm-up, outside the measured window
    run_large()

    t_small = _fastest_of(run_small)
    t_large = _fastest_of(run_large)

    floor = 1e-4  # guard against timer-resolution noise on very fast runs
    ratio = max(t_large, floor) / max(t_small, floor)
    # Document size differs 100x. A cost genuinely tied to document size
    # would show up as roughly that ratio; a 10x margin is generous enough
    # to absorb machine noise while still catching such a regression.
    assert ratio < 10.0, f"edit-batch time tracked document size: small={t_small} large={t_large}"


# --------------------------------------------------------------------------
# 2. subtree_bytes update cost vs. path depth (not total node count)
# --------------------------------------------------------------------------


def test_single_edit_cost_scales_with_path_depth():
    """``SubtreeBytesAggregate.apply_delta`` walks a node's ancestor chain
    only ({p067}): its cost -- and the exact set of entries it touches --
    must scale with path DEPTH, not with how many unrelated totals are
    registered elsewhere."""
    agg = SubtreeBytesAggregate()

    # A large unrelated population, standing in for "total node count".
    unrelated_count = 20_000
    for i in range(unrelated_count):
        agg.initialize(("unrelated", f"n{i}"), i)

    shallow_path = ("root", "a")
    agg.initialize((), 100)
    agg.initialize(("root",), 100)
    agg.initialize(shallow_path, 10)

    deep_depth = 2_000
    deep_path = tuple(f"d{i}" for i in range(deep_depth))
    for i in range(len(deep_path) + 1):
        agg.initialize(deep_path[:i], 1_000)

    touched_shallow = agg.apply_delta(shallow_path, 5)
    touched_deep = agg.apply_delta(deep_path, 5)

    # Exact counts: apply_delta touches exactly depth+1 prefixes (the node
    # plus every registered ancestor including the root), never anything
    # from the 20,000-entry unrelated population.
    assert len(touched_shallow) == len(shallow_path) + 1
    assert len(touched_deep) == len(deep_path) + 1
    assert all(p[:1] != ("unrelated",) for p in touched_deep)  # never touches the unrelated namespace
    # Deep-path cost is driven by depth, and stays far below the unrelated
    # population size -- proof it is not O(total node count).
    assert len(touched_deep) < unrelated_count / 5

    # Corroborate with timing: apply_delta on the SAME shallow path must
    # cost about the same whether the aggregate additionally holds 20,000
    # unrelated entries or almost none of them.
    def run_against(totals_size: int) -> float:
        local_agg = SubtreeBytesAggregate()
        local_agg.initialize((), 1)
        local_agg.initialize(("root",), 1)
        local_agg.initialize(shallow_path, 1)
        for i in range(totals_size):
            local_agg.initialize(("unrelated", f"n{i}"), i)

        def op():
            local_agg.apply_delta(shallow_path, 1)

        op()  # warm-up
        return _fastest_of(op)

    t_small_totals = run_against(10)
    t_large_totals = run_against(unrelated_count)
    floor = 1e-5
    ratio = max(t_large_totals, floor) / max(t_small_totals, floor)
    assert ratio < 10.0, f"apply_delta cost tracked totals-dict size: {t_small_totals=} {t_large_totals=}"


# --------------------------------------------------------------------------
# 3. offset-resolution cost vs. shifted/pending edit count
# --------------------------------------------------------------------------


def test_single_edit_cost_scales_with_shifted_range_count(monkeypatch):
    """Verified: 200 edits cost the same whether the index tracks 1k or
    50k positions. ``LazyOffsetIndex.resolve`` replays only the edits
    recorded since the resolved position was last touched -- cost bounded
    by that pending count, never by how many other positions are
    registered. Few pending edits must cost less to resolve than many,
    independent of the unrelated population size."""
    index = LazyOffsetIndex()

    unrelated_positions = 50_000
    for i in range(unrelated_positions):
        index.create_position(i, 1, node_path=("unrelated", f"n{i}"))

    replay_calls = _spy(monkeypatch, positions_mod, "_apply_edit_to_span")

    probe_few = index.create_position(10, 1, node_path=("probe", "few"))
    few_edits = 5
    for i in range(few_edits):
        index.record_edit(1_000_000 + i, 1_000_000 + i + 1, 1)

    replay_calls["n"] = 0
    index.resolve(probe_few)
    # Exact: replay cost equals precisely the edits recorded since creation,
    # never touching the 50,000 unrelated registered positions.
    assert replay_calls["n"] == few_edits

    probe_many = index.create_position(20, 1, node_path=("probe", "many"))
    many_edits = 5_000
    for i in range(many_edits):
        index.record_edit(2_000_000 + i, 2_000_000 + i + 1, 1)

    replay_calls["n"] = 0
    index.resolve(probe_many)
    assert replay_calls["n"] == many_edits
    assert many_edits > few_edits * 100  # few must cost far less than many

    # Corroborate with timing: resolving a position with a SMALL pending
    # count costs about the same whether 1k or 50k unrelated positions are
    # registered in the same index.
    def build_and_resolve(total_positions: int) -> float:
        idx = LazyOffsetIndex()
        for i in range(total_positions):
            idx.create_position(i, 1, node_path=("unrelated", f"n{i}"))
        probe = idx.create_position(0, 1, node_path=("probe",))
        for i in range(200):
            idx.record_edit(500_000 + i, 500_000 + i + 1, 1)

        def op():
            idx.resolve(probe)

        return op

    op_1k = build_and_resolve(1_000)
    op_50k = build_and_resolve(50_000)
    op_1k()  # first resolve consumes the pending log; time a no-op resolve
    op_50k()  # after warm-up, both are already fully resolved (0 pending)

    floor = 1e-5
    t_1k = _fastest_of(op_1k)
    t_50k = _fastest_of(op_50k)
    ratio = max(t_50k, floor) / max(t_1k, floor)
    assert ratio < 10.0, f"resolve cost tracked registered-position count: {t_1k=} {t_50k=}"


# --------------------------------------------------------------------------
# 4. K-operation batch never performs K full traversals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("k", [5, 20, 100])
def test_k_operation_batch_no_k_full_traversals(k, monkeypatch):
    """``PositionIndex.on_edit_applied`` never calls ``full_reindex`` /
    ``full_resync`` ({p016}, {p017}): applying a batch of K local edits
    must trigger zero full traversals, for every tested K. Exactly one
    sanctioned full traversal (the batch's own control check, {p016} case
    4) is then allowed -- never more, and never scaling with K."""
    source = _make_source(50_000)
    buffer = SourceBuffer(source)
    index = PositionIndex(buffer)
    buffer.add_listener(index)

    full_calls = _spy(monkeypatch, index.offsets, "full_resync")

    for i in range(k):
        start = EDIT_BASE + i * EDIT_STEP
        buffer.apply_edit(start, start + REMOVED_SPAN, FRAGMENT, node_path=("root", f"n{i}"))

    assert index.offsets.edit_count == k  # the batch really did K edits
    assert full_calls["n"] == 0  # yet triggered zero full traversals

    index.full_reindex(FullReindexReason.BATCH_CONTROL_CHECK)
    assert full_calls["n"] == 1  # exactly one, the batch's own control check


# --------------------------------------------------------------------------
# 5. baseline correctness: unedited regions round-trip byte-for-byte
# --------------------------------------------------------------------------


def test_byte_for_byte_roundtrip_unedited_regions():
    """Sanity baseline ({p014}, {p022}) alongside the scaling assertions
    above: bytes outside every edited span must reproduce the original
    source exactly."""
    size = 30_000
    source = _make_source(size)
    buffer = SourceBuffer(source)

    zone_start, zone_end = 5_000, size - 5_000
    edits = [
        (zone_start + 100, zone_start + 104, b"AAAA"),
        (zone_start + 500, zone_start + 508, b"BBBBBBBB"),
        (zone_end - 300, zone_end - 292, b"CCCCCCCC"),
    ]
    for i, (start, end, repl) in enumerate(edits):
        assert end - start == len(repl)  # same-length: no downstream shift
        buffer.apply_edit(start, end, repl, node_path=("root", f"e{i}"))

    result = buffer.serialize()
    assert len(result) == size

    assert result[:zone_start] == source[:zone_start]
    assert result[zone_end:] == source[zone_end:]
    assert result[zone_start + 104 : zone_start + 500] == source[zone_start + 104 : zone_start + 500]
    assert result[zone_start + 508 : zone_end - 300] == source[zone_start + 508 : zone_end - 300]

    assert result[zone_start + 100 : zone_start + 104] == b"AAAA"
    assert result[zone_start + 500 : zone_start + 508] == b"BBBBBBBB"
    assert result[zone_end - 300 : zone_end - 292] == b"CCCCCCCC"
