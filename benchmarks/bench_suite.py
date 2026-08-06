"""Reproducible benchmark suite for the tree engine (C-022, {p028}, {p029}, {p030}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Real engine, real files: deterministic Python and JSON corpora of 1k/5k/10k lines on disk,
driven through the real plugins (libcst for Python), ``query.engine``, the ``SourceBuffer``
edit path with real ``parse_fragment`` reparses, and ``storage.codec`` encode/decode plus
``file_txn`` atomic publish -- nothing simulated, nothing fabricated. Each scenario runs
``warmups`` unmeasured then ``iterations`` measured repetitions (1 + 5 by default, the
{p028} minimum) timed with ``perf_counter_ns``, reporting min/median/p95/max/mean/stdev, a
relative spread and the raw samples (p95 is nearest-rank, hence the maximum at n=5) beside
its size in bytes and nodes plus the derived ns-per-byte and ns-per-node.

Instrumentation ({p030}) is off in the engine by default and switched on here, and markers
are DERIVED FROM THE MEASUREMENT, never asserted: ``full-traversal`` only when the operation
touched at least as many nodes as the document holds, ``full-parse`` only when it parsed at
least as many bytes, ``full-index-rebuild`` only for the codec paths that really rebuild the
short-id map; the {p029} gate holds when every ``mutate`` scenario's counter delta is
``is_local_operation()``. The frozen ``Node`` model carries no mutable ``nodes_by_id`` for
``core.operations`` to resolve through, so a local mutation costs what that model costs: a
real ``apply_edit``, a real ``parse_fragment``, an ancestor-path rebuild through
``dataclasses.replace``; ``rendered_bytes`` is that tree rendered back to source.

JSON schema ``tree_engine.bench_suite/1``: ``schema``, ``metadata``, ``summary``, ``corpora``
(format_id, lines, bytes, nodes, tree_bytes, path, targets), ``results[scenario][corpus]`` --
scenario, corpus, format_id, phase, ``input``, ``timing_ns`` (:func:`_stats`),
``ns_per_byte``, ``ns_per_node``, ``rendered_bytes``, ``counters`` (:func:`_counters`, null
while off) and ``structural_check``. :func:`run_benchmarks` is the callable entry point.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import random
import shutil
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tree_engine.core import instrumentation as instr  # noqa: E402
from tree_engine.core.buffer import SourceBuffer  # noqa: E402
from tree_engine.core.nodes import Node, walk  # noqa: E402
from tree_engine.plugins.json_format import JsonFormatPlugin  # noqa: E402
from tree_engine.plugins.python.plugin import PythonFormatPlugin  # noqa: E402
from tree_engine.query.adapter import TreeTraversalAdapter  # noqa: E402
from tree_engine.query.engine import TreeQueryEngine  # noqa: E402
from tree_engine.storage import codec, file_txn  # noqa: E402

SCHEMA_ID = "tree_engine.bench_suite/1"
DEFAULT_SIZES: Tuple[int, ...] = (1000, 5000, 10000)
DEFAULT_FORMATS: Tuple[str, ...] = ("python", "json")
DEFAULT_ITERATIONS, DEFAULT_WARMUPS, DEFAULT_SEED = 5, 1, 20260806
_NEW_NAME = "renamed_by_benchmark"
_FRAGMENT = "def benchmark_inserted(self, value):\n    return value + 1\n"
_BODY_STATEMENT = "total = value * 2\n"
_BATCH_KINDS = ("replace", "insert", "delete", "identifier")
_BATCH_OPERATIONS = 8
_MUTATE = instr.PHASE_MUTATE

def _python_source(lines, rng):  # exactly `lines` lines, whole class blocks only
    out = ['"""Deterministic benchmark corpus."""', "import os", ""]
    while len(out) + 22 <= lines:
        index = len(out)
        out += [f"class Klass{index}:", f"    ATTR{index} = {rng.randint(0, 999)}"]
        for slot in range(4):
            out += [f"    def method_{index}_{slot}(self, value):",
                    f"        # step {index}.{slot}",
                    f"        total = value + {rng.randint(1, 99)}", "        return total", ""]
    while len(out) < lines:
        out.append(f"# filler line {len(out)}")
    return "\n".join(out) + "\n"

def _json_source(lines, rng):  # exactly `lines` lines, comma-free tail, still valid
    body: List[str] = []
    while len(body) + 5 <= lines - 3:
        body += [f'  "entry_{len(body)}": {{', f'    "id": {rng.randint(0, 9999)},',
                 '    "tags": ["alpha", "beta", "gamma"],',
                 f'    "enabled": {"true" if rng.random() < 0.5 else "false"}', "  },"]
    while len(body) < lines - 3:
        body.append(f'  "pad_{len(body)}": {len(body)},')
    body.append(f'  "tail": {len(body)}')
    return "{\n" + "\n".join(body) + "\n}\n"

_FORMATS: Dict[str, Tuple[Any, Any, str, str]] = {
    "python": (PythonFormatPlugin, _python_source, ".py", "method"),
    "json": (JsonFormatPlugin, _json_source, ".json", "object:*")}

class _Corpus(NamedTuple):  # one measured input: bytes on disk, parsed document, size
    key: str
    format_id: str
    plugin: Any
    lines: int
    path: Path
    outdir: Path
    source: bytes
    document: Any
    nodes: int
    selector: str
    tree_bytes: bytes
    targets: Tuple[Any, ...]

class _Effect(NamedTuple):  # nodes touched, bytes changed, implied markers, artifact
    affected: int
    changed: int
    markers: Tuple[str, ...]
    artifact: Any = None

def _build_corpus(format_id, lines, workdir, outdir, seed) -> _Corpus:  # never timed
    factory, generate, suffix, selector = _FORMATS[format_id]
    plugin = factory()
    source = generate(lines, random.Random(seed + lines)).encode("utf-8")
    path = workdir / f"corpus_{format_id}_{lines}{suffix}"
    path.write_bytes(source)
    document = plugin.parse_document(source)
    targets = tuple((node, tuple(ancestors)) for node, ancestors, role
                    in TreeTraversalAdapter(document, plugin).iter_nodes()
                    if role == "method" and node.buffer_range and ancestors
                    and "body" in node.fields) if format_id == "python" else ()
    return _Corpus(f"{format_id}:{lines}", format_id, plugin, lines, path, outdir, source,
                   document, sum(1 for _ in walk(document.root)), selector,
                   codec.encode(document), targets)

def _markers(corpus, affected, parsed, rebuilt=False):  # implied by measurement {p029}
    return tuple(([instr.MARKER_FULL_TRAVERSAL] if affected >= corpus.nodes else [])
                 + ([instr.MARKER_FULL_PARSE] if parsed >= len(corpus.source) else [])
                 + ([instr.MARKER_FULL_INDEX_REBUILD] if rebuilt else []))

def _rewrite(items, old, new, mode):  # old replaced, dropped (new None), or preceded
    if mode == "insert":
        return tuple(x for item in items for x in ((new, item) if item is old else (item,)))
    return tuple(item if item is not old else new
                 for item in items if item is not old or new is not None)

def _rebuild_parent(parent, old, new, mode="replace") -> Node:  # rebuild one changed child
    fields = {name: (new if value is old and mode != "insert" else
                     _rewrite(value, old, new, mode)
                     if isinstance(value, tuple) and any(x is old for x in value) else value)
              for name, value in parent.fields.items()}
    return dataclasses.replace(parent, fields=fields,
                               children=_rewrite(parent.children, old, new, mode))

def _rebuild_path(ancestors, old, new):  # only the ancestor chain: root, nodes touched
    touched, current_old, current_new = 1, old, new
    for parent in reversed(tuple(ancestors)):
        current_new = _rebuild_parent(parent, current_old, current_new)
        current_old, touched = parent, touched + 1
    return current_new, touched

def _plan(kind, node, ancestors) -> Tuple[Any, ...]:
    """(chain, old, edit_range, text, mode, anchor) for an already-located target."""
    start = node.buffer_range[0]
    if kind == "replace":
        return ancestors, node, node.buffer_range, _FRAGMENT, "fragment", node
    if kind == "insert":
        return ancestors[:-1], ancestors[-1], (start, start), _FRAGMENT, "insert", node
    if kind == "delete":
        return ancestors, node, node.buffer_range, "", "drop", node
    if kind == "body":
        block = node.fields["body"]
        line = block.children[-1]
        return (tuple(ancestors) + (node, block), line, line.buffer_range,
                _BODY_STATEMENT, "fragment", node)
    name = node.fields["name"]
    return (tuple(ancestors) + (node,), name,
            name.buffer_range if kind == "identifier" else None, _NEW_NAME, "field", node)

def _apply(corpus, buffer, plan) -> _Effect:
    """Real buffer edit, real fragment reparse where needed, real path rebuild."""
    chain, old, edit, text, mode, anchor = plan
    payload = text.encode("utf-8")
    if edit is not None and buffer is not None:
        buffer.apply_edit(edit[0], edit[1], payload, ())
    extra = 0
    if mode in ("fragment", "insert"):
        fragment = corpus.plugin.parse_fragment(text)
        extra = sum(1 for _ in walk(fragment))
        new = _rebuild_parent(old, anchor, fragment, "insert") if mode == "insert" else fragment
    elif mode == "drop":
        new = None
    else:
        new = dataclasses.replace(old, fields={**dict(old.fields), "value": text})
    root, touched = _rebuild_path(chain, old, new)
    affected = touched + extra
    return _Effect(affected, len(payload),
                   _markers(corpus, affected, len(payload) if extra else 0), root)

def _mutation_case(kind):  # planned once against the middle method, never the edges
    def factory(corpus):
        plan = _plan(kind, *corpus.targets[len(corpus.targets) // 2])
        setup = (lambda: SourceBuffer(corpus.source)) if plan[2] is not None else None
        return setup, lambda buffer: _apply(corpus, buffer, plan)
    return factory

def _case_batch(corpus):
    """Eight mixed local operations on one buffer (descending offsets, so they
    compose) plus eight real subtree rebuilds."""
    step = max(1, len(corpus.targets) // _BATCH_OPERATIONS)
    ordered = sorted(corpus.targets[::step][:_BATCH_OPERATIONS],
                     key=lambda pair: pair[0].buffer_range[0], reverse=True)
    plans = [_plan(_BATCH_KINDS[index % len(_BATCH_KINDS)], node, ancestors)
             for index, (node, ancestors) in enumerate(ordered)]

    def run(buffer):
        affected = changed = 0
        for plan in plans:
            effect = _apply(corpus, buffer, plan)
            affected, changed = affected + effect.affected, changed + effect.changed
        return _Effect(affected, changed, _markers(corpus, affected, 0), buffer.serialize())
    return (lambda: SourceBuffer(corpus.source)), run

def _static_case(kind):
    """Load from disk, query, atomic save, and tree-file decode (load, no reparse)."""
    def factory(corpus):
        stem = corpus.key.replace(":", "_")

        def run(_):
            if kind == "load":
                data = corpus.path.read_bytes()
                return _Effect(corpus.nodes, len(data), _markers(corpus, corpus.nodes, len(data)),
                               corpus.plugin.parse_document(data))
            if kind == "query":
                found = TreeQueryEngine(corpus.document, corpus.plugin).query(corpus.selector)
                return _Effect(corpus.nodes, 0, _markers(corpus, corpus.nodes, 0), found)
            if kind == "decode":
                return _Effect(corpus.nodes, len(corpus.tree_bytes),
                               _markers(corpus, corpus.nodes, 0, True),
                               codec.decode(corpus.tree_bytes))
            output = corpus.plugin.generate_output(corpus.document)
            rendered = output.encode("utf-8") if isinstance(output, str) else output
            tree = codec.encode(corpus.document)
            file_txn.publish([file_txn.FileWrite(corpus.outdir / corpus.path.name, rendered),
                              file_txn.FileWrite(corpus.outdir / f"{stem}.tree.json", tree)],
                             corpus.outdir / f"{stem}.journal.json")
            return _Effect(corpus.nodes, len(rendered) + len(tree),
                           _markers(corpus, corpus.nodes, 0, True), rendered)
        return None, run
    return factory

_SCENARIOS: Tuple[Tuple[str, str, str, Any], ...] = (
    ("load_parse", instr.PHASE_PARSE, "any", _static_case("load")),
    ("query_select", instr.PHASE_QUERY, "any", _static_case("query")),
    ("mutate_replace", _MUTATE, "python", _mutation_case("replace")),
    ("mutate_insert", _MUTATE, "python", _mutation_case("insert")),
    ("mutate_delete", _MUTATE, "python", _mutation_case("delete")),
    ("mutate_attribute", _MUTATE, "python", _mutation_case("attribute")),
    ("mutate_body", _MUTATE, "python", _mutation_case("body")),
    ("mutate_identifier", _MUTATE, "python", _mutation_case("identifier")),
    ("batch_mixed", _MUTATE, "python", _case_batch),
    ("save_publish", instr.PHASE_SAVE, "any", _static_case("save")),
    ("load_tree_decode", instr.PHASE_LOAD, "any", _static_case("decode")))

def _execute(phase, run, state) -> _Effect:  # one instrumented phase invocation
    with instr.measure(phase) as scope:
        effect = run(state)
        scope.add_affected_nodes(effect.affected)
        scope.add_changed_text(effect.changed)
        scope.mark(*effect.markers)
    return effect

def _stats(samples, iterations, warmups) -> Dict[str, Any]:  # the measured distribution
    ordered = sorted(samples)
    median = statistics.median(ordered)
    return {"iterations": iterations, "warmups": warmups, "min_ns": ordered[0],
            "median_ns": median, "p95_ns": ordered[-(-95 * len(ordered) // 100) - 1],
            "max_ns": ordered[-1], "mean_ns": statistics.fmean(ordered),
            "stdev_ns": statistics.pstdev(ordered), "samples_ns": list(samples),
            "relative_spread": (ordered[-1] - ordered[0]) / median if median else 0.0}

def _counters(snapshot) -> Dict[str, Any]:  # per-phase totals, markers, {p029} verdict
    return {"phases": {name: {metric: getattr(counter, metric) for metric in instr.METRICS}
                       | {"markers": dict(counter.markers)}
                       for name, counter in snapshot.phases.items()},
            "structural_markers": list(snapshot.structural_markers()),
            "is_local_operation": snapshot.is_local_operation()}

def _measure_case(name, phase, corpus, factory, iterations, warmups) -> Dict[str, Any]:
    """Warm up, time the repetitions, isolate their counters, and render a mutation's
    rebuilt tree back to bytes as proof the measured work was real."""
    setup, run = factory(corpus)
    for _ in range(warmups):
        effect = _execute(phase, run, setup() if setup else None)
    before = instr.query_counters(scope=instr.SCOPE_THREAD)
    samples: List[int] = []
    for _ in range(iterations):
        state = setup() if setup else None
        started = perf_counter_ns()
        effect = _execute(phase, run, state)
        samples.append(perf_counter_ns() - started)
    delta = instr.query_counters(scope=instr.SCOPE_THREAD).delta_from(before)
    timing = _stats(samples, iterations, warmups)
    counters = _counters(delta) if instr.is_enabled() else None
    built = effect.artifact if phase == _MUTATE else None
    rendered = (corpus.plugin.generate_output(dataclasses.replace(corpus.document, root=built))
                if isinstance(built, Node) else built if isinstance(built, bytes) else None)
    return {"scenario": name, "corpus": corpus.key, "format_id": corpus.format_id, "phase": phase,
            "input": {"lines": corpus.lines, "bytes": len(corpus.source), "nodes": corpus.nodes},
            "timing_ns": timing, "ns_per_byte": timing["median_ns"] / len(corpus.source),
            "ns_per_node": timing["median_ns"] / corpus.nodes, "counters": counters,
            "rendered_bytes": None if rendered is None else len(rendered),
            "structural_check": None if phase != _MUTATE else {
                "required_local": True,
                "passed": counters["is_local_operation"] if counters else None}}

def run_benchmarks(*, sizes: Sequence[int] = DEFAULT_SIZES,
                   formats: Sequence[str] = DEFAULT_FORMATS,
                   iterations: int = DEFAULT_ITERATIONS, warmups: int = DEFAULT_WARMUPS,
                   seed: int = DEFAULT_SEED, instrumentation: bool = True,
                   workdir: Optional[Path] = None) -> Dict[str, Any]:
    """Run the suite, returning the report the module docstring describes."""
    if iterations < 5:
        raise ValueError(f"iterations must be at least 5 per {{p028}}, got {iterations}")
    started = perf_counter_ns()
    owned = workdir is None
    root = Path(tempfile.mkdtemp(prefix="tree-engine-bench-")) if owned else Path(workdir)
    outdir = root / "published"
    outdir.mkdir(parents=True, exist_ok=True)
    instr.enable(reset_counters=True) if instrumentation else (instr.disable(), instr.reset())
    try:
        corpora = [_build_corpus(name, size, root, outdir, seed)
                   for name in formats for size in sizes]
        results: Dict[str, Dict[str, Any]] = {}
        failures: List[str] = []
        for name, phase, applies, factory in _SCENARIOS:
            for corpus in corpora:
                if applies not in ("any", corpus.format_id):
                    continue
                record = _measure_case(name, phase, corpus, factory, iterations, warmups)
                results.setdefault(name, {})[corpus.key] = record
                if record["structural_check"] and record["structural_check"]["passed"] is False:
                    failures.append(f"{name}@{corpus.key}")
        elapsed = (perf_counter_ns() - started) / 1e9
        return {"schema": SCHEMA_ID, "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python_version": platform.python_version(), "platform": platform.platform(),
            "timer": "time.perf_counter_ns", "p95_method": "nearest-rank", "seed": seed,
            "sizes": list(sizes), "formats": list(formats), "iterations": iterations,
            "warmups": warmups, "instrumentation_enabled": bool(instrumentation),
            "tree_engine_path": str(Path(instr.__file__).resolve().parents[2]),
            "wall_clock_s": elapsed},
            "corpora": {c.key: {"format_id": c.format_id, "lines": c.lines,
                                "bytes": len(c.source), "nodes": c.nodes,
                                "tree_bytes": len(c.tree_bytes), "path": str(c.path),
                                "targets": len(c.targets)} for c in corpora},
            "results": results,
            "summary": {"scenarios": len(results), "corpora": len(corpora),
                        "measurements": sum(len(v) for v in results.values()),
                        "structural_failures": failures, "wall_clock_s": elapsed}}
    finally:
        instr.disable()
        if owned:
            shutil.rmtree(root, ignore_errors=True)

def _summarise(report, stream) -> None:  # short human summary beside the JSON payload
    meta = report["metadata"]
    out = [f"tree-engine benchmark suite -- {report['schema']}",
           f"  instrumentation={meta['instrumentation_enabled']} iterations={meta['iterations']}"
           f" warmups={meta['warmups']} wall_clock={meta['wall_clock_s']:.1f}s"]
    out += [f"  corpus {key}: {info['lines']} lines, {info['bytes']} bytes, {info['nodes']} nodes"
            for key, info in report["corpora"].items()]
    out.append(f"  {'scenario':<18}{'corpus':<14}{'median':>12}{'p95':>12}{'spread':>9} local")
    for scenario, per_corpus in report["results"].items():
        for key, record in per_corpus.items():
            check, timing = record["structural_check"], record["timing_ns"]
            out.append(f"  {scenario:<18}{key:<14}{timing['median_ns'] / 1e6:>10.3f}ms"
                       f"{timing['p95_ns'] / 1e6:>10.3f}ms{timing['relative_spread']:>9.3f}"
                       f"  {'-' if check is None else 'ok' if check['passed'] else 'FAIL'}")
    out.append(f"  structural failures: {report['summary']['structural_failures'] or 'none'}")
    print("\n".join(out), file=stream)

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="tree-engine benchmark suite")
    parser.add_argument("--sizes", default=",".join(str(n) for n in DEFAULT_SIZES))
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS))
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--no-instrumentation", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here, not to stdout")
    args = parser.parse_args(argv)
    report = run_benchmarks(sizes=[int(n) for n in args.sizes.split(",") if n],
                            formats=[f for f in args.formats.split(",") if f],
                            iterations=args.iterations,
                            instrumentation=not args.no_instrumentation)
    payload = json.dumps(report, indent=2, sort_keys=False)
    args.out.write_text(payload + "\n", encoding="utf-8") if args.out else print(payload)
    _summarise(report, sys.stderr)
    return 1 if report["summary"]["structural_failures"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
