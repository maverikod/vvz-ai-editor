"""Full-document reference-integrity validator (concept C-008).

Scope (concept C-008, the last of four ReferenceIntegrity siblings): this
module owns exactly one entry point, :func:`validate_full_document`, that
``export_tree``, ``generate_output``, and the storage-layer handoff must
call before producing output, per {p083}. Where the already-merged
``core/integrity.py`` (:func:`~tree_engine.core.integrity.validate_after_mutation`)
deliberately bounds its checks to changed nodes and their immediate
neighbours ({p082}), this module drives the *same* low-level primitives
across every node, id, and index entry of the document, plus the checks
that only make sense at whole-document scope: id/short_id uniqueness,
external-address syntax and resolver-based liveness, cycle detection, and
range/version consistency.

Reuse, not reimplementation: this module imports ``core/integrity.py``'s
own private per-item check functions (``_index_of``, ``_Scope``,
``_check_parent_child_symmetry``, ``_check_cache_conformance``,
``_check_backlinks``, ``_check_local_resolvability``) and drives each of
them once per node/edge/address instead of re-deriving equivalent
symmetry/cache/backlink/resolvability logic. Those functions already
raise :class:`~tree_engine.core.integrity.IntegrityError` on the first
mismatch of a given single-item scope; calling them per item, rather than
once over a scope covering the whole document, is what turns their
fail-fast behaviour into the aggregate-all-violations behaviour {p083}
requires without touching a line of their bodies. External-address syntax
reuses ``core/references.py``'s own round-trip helpers
(``node_address_to_string`` / ``parse_node_address``) rather than
reimplementing UUID-shape checking. The generation fast-path check for
cache and range/version conformance reuses the exact comparison
``core/reference_cache.py`` defines for {p084} (``cached_generation`` vs.
the live ``nodes_by_id`` entry's ``generation``).

Duck-typed ``document`` contract, extending the one ``integrity.py``
already uses: ``document`` is either a
:class:`~tree_engine.core.reference_cache.ReferenceIndex` itself, or any
object exposing one through a ``reference_index`` attribute. Three further
attributes are read only if present, each an independent, purely
additive extension point -- their absence never blocks validation, it only
narrows what gets checked:

* ``root`` -- a :class:`~tree_engine.core.nodes.Node` (per {p016}'s
  "explicit full check" case), walked to cross-check the raw node graph's
  own ``node_id`` values for duplicates the index's dict-keyed maps cannot
  represent by construction.
* ``ranges`` -- a mapping or iterable of range records, each either an
  object exposing ``node_id``/``generation`` or a ``(node_id,
  generation)`` pair, checked against the node's live generation.
* ``version`` and ``version_generations`` -- a document version marker
  plus the ``node_id -> generation`` snapshot it was computed from, that
  full validation confirms is still current.

This module performs no mutation, in any code path, of ``document``, its
index maps, or any cache entry -- including on the raising path -- and
implements no export/generate/storage I/O of its own; it is only the
validator those layers must call.

Source-of-truth requirement labels honored here: {p016}, {p042}, {p080},
{p081}, {p083}, {p084}.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.integrity import (
    IntegrityError,
    _Scope,
    _check_backlinks,
    _check_cache_conformance,
    _check_local_resolvability,
    _check_parent_child_symmetry,
    _index_of,
)
from tree_engine.core.nodes import walk as walk_nodes
from tree_engine.core.reference_cache import ReferenceIndex
from tree_engine.core.references import (
    InvalidNodeAddressError,
    is_external,
    is_local,
    node_address_to_string,
    parse_node_address,
)

__all__ = ["FullIntegrityError", "FullIntegrityReport", "validate_full_document"]

#: A resolver probes whether an external document is loaded. It takes the
#: target ``document_id`` and returns ``None`` when that document is not
#: loaded/unavailable (legal per {p083}), or -- when it is loaded -- an
#: object exposing membership for node ids, either directly (``in``) or via
#: a ``nodes_by_id`` mapping attribute, mirroring ``_index_of``'s own
#: duck typing.
DocumentResolver = Callable[[UUID], Optional[Any]]

Violation = Tuple[str, str]


class FullIntegrityError(IntegrityError):
    """Raised by :func:`validate_full_document` with every violation found.

    Subclasses ``integrity.py``'s :class:`~tree_engine.core.integrity.IntegrityError`
    so a caller already handling that type also catches this one, per the
    instruction to reuse the existing violation/error type rather than
    defining a parallel hierarchy. ``violations`` is the full, ordered
    tuple of ``(check, message)`` pairs found in a single run -- this
    error is only ever raised once all checks have run, never on the
    first mismatch. ``check`` reuses the exact vocabulary
    :class:`IntegrityError` already defines (``"symmetry"``,
    ``"cache-conformance"``, ``"backlink"``, ``"local-resolvability"``)
    for the checks that are full-scope replays of ``integrity.py``'s own,
    plus the full-document-only additions this module introduces:
    ``"uniqueness"``, ``"external-address"``, ``"cycle"``, and
    ``"range-version"``.
    """

    def __init__(self, violations: Iterable[Violation]) -> None:
        self.violations: Tuple[Violation, ...] = tuple(violations)
        lead_check = self.violations[0][0] if self.violations else "full-integrity"
        summary = "; ".join(message for _check, message in self.violations)
        super().__init__(lead_check, f"{len(self.violations)} violation(s): {summary}")


@dataclass(frozen=True)
class FullIntegrityReport:
    """Success summary of one :func:`validate_full_document` run.

    ``nodes_checked`` is the number of registered index entries examined
    by the structural checks; ``ids_checked`` is the number of raw
    node_id occurrences examined for the uniqueness check (from the
    ``root`` walk when supplied, otherwise the same as ``nodes_checked``);
    ``external_references_checked`` counts every external ``NodeAddress``
    examined, whether or not its document was loaded; ``unresolved_external``
    lists the syntactically-valid external references whose target
    document is not loaded -- informational per {p083}, never a violation.
    """

    nodes_checked: int
    ids_checked: int
    external_references_checked: int
    unresolved_external: Tuple[NodeAddress, ...]


def _record(violations: List[Violation], exc: IntegrityError) -> None:
    violations.append((exc.check, str(exc)))


def _check_uniqueness(document: Any, index: ReferenceIndex, violations: List[Violation]) -> int:
    """Duplicate node_id (via ``root``) and duplicate short_id ({p097})."""

    root = getattr(document, "root", None)
    ids_checked = len(index.nodes_by_id)
    if root is not None:
        seen = [node.node_id for node in walk_nodes(root) if getattr(node, "node_id", None) is not None]
        ids_checked = len(seen)
        for node_id, count in Counter(seen).items():
            if count > 1:
                violations.append((
                    "uniqueness",
                    f"node_id {node_id} appears {count} times in the document's node graph",
                ))

    by_short_id: Dict[Any, List[UUID]] = {}
    for node_id, short_id in index.node_id_to_short_id.items():
        by_short_id.setdefault(short_id, []).append(node_id)
    for short_id, node_ids in by_short_id.items():
        if len(node_ids) > 1:
            violations.append((
                "uniqueness",
                f"short_id {short_id!r} is used by {len(node_ids)} distinct node ids: "
                f"{sorted(str(n) for n in node_ids)}",
            ))
    return ids_checked


def _check_full_symmetry_and_cache(index: ReferenceIndex, violations: List[Violation]) -> None:
    """Drive ``integrity.py``'s per-item symmetry/backlink/cache checks over every entry."""

    for node_id in index.nodes_by_id:
        scope = _Scope(node_ids={node_id})
        try:
            _check_parent_child_symmetry(index, scope)
        except IntegrityError as exc:
            _record(violations, exc)
        try:
            _check_cache_conformance(index, scope)
        except IntegrityError as exc:
            _record(violations, exc)

    for source_id, targets in index.outgoing_refs.items():
        for address in targets:
            try:
                _check_backlinks(index, _Scope(outgoing_edges={(source_id, address)}))
            except IntegrityError as exc:
                _record(violations, exc)
    for target_id, sources in index.incoming_refs.items():
        for source_id in sources:
            try:
                _check_backlinks(index, _Scope(incoming_edges={(target_id, source_id)}))
            except IntegrityError as exc:
                _record(violations, exc)


def _resolver_target(loaded: Any) -> Any:
    return getattr(loaded, "nodes_by_id", loaded)


def _check_local_and_external(
    index: ReferenceIndex,
    resolver: Optional[DocumentResolver],
    violations: List[Violation],
) -> Tuple[int, Tuple[NodeAddress, ...]]:
    """Full local resolvability ({p081}) plus external syntax/liveness ({p083})."""

    external_checked = 0
    unresolved: List[NodeAddress] = []

    for source_id, targets in index.outgoing_refs.items():
        for address in targets:
            if is_local(address):
                try:
                    _check_local_resolvability(index, _Scope(loose_addresses={address}))
                except IntegrityError as exc:
                    _record(violations, exc)
                continue

            external_checked += 1
            try:
                parse_node_address(node_address_to_string(address))
            except InvalidNodeAddressError as exc:
                violations.append((
                    "external-address",
                    f"node {source_id}'s external reference {address!r} is malformed: {exc}",
                ))
                continue

            if resolver is None:
                unresolved.append(address)
                continue

            loaded = resolver(address.document_id)
            if loaded is None:
                unresolved.append(address)
                continue
            if address.node_id not in _resolver_target(loaded):
                violations.append((
                    "external-address",
                    f"node {source_id}'s external reference {address!r} points at a "
                    "loaded document that does not contain that node_id",
                ))

    return external_checked, tuple(unresolved)


def _check_cycles(index: ReferenceIndex, violations: List[Violation]) -> None:
    """Detect forbidden reference cycles in the parent/child structure ({p083}).

    Iterative three-colour DFS over ``child_index`` so it never depends on
    Python's recursion limit. Runs across every node in ``nodes_by_id``
    (not just those reachable from a single root) so a cycle in a
    detached fragment is still caught. On finding a back-edge it records
    the cycle and keeps scanning -- it does not stop at the first one.
    """

    color: Dict[UUID, int] = {}
    for start in index.nodes_by_id:
        if color.get(start, 0) != 0:
            continue
        path = [start]
        color[start] = 1
        stack = [(start, iter(index.get_children(start)))]
        while stack:
            node_id, children = stack[-1]
            advanced = False
            for child_id in children:
                if child_id not in index.nodes_by_id:
                    continue
                state = color.get(child_id, 0)
                if state == 0:
                    color[child_id] = 1
                    path.append(child_id)
                    stack.append((child_id, iter(index.get_children(child_id))))
                    advanced = True
                    break
                if state == 1:
                    cycle = path[path.index(child_id):] + [child_id]
                    violations.append((
                        "cycle",
                        "forbidden reference cycle detected: "
                        + " -> ".join(str(n) for n in cycle),
                    ))
            if not advanced:
                stack.pop()
                path.pop()
                color[node_id] = 2


def _range_fields(entry: Any) -> Optional[Tuple[UUID, int]]:
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[0], entry[1]
    node_id = getattr(entry, "node_id", None)
    generation = getattr(entry, "generation", None)
    if node_id is None or generation is None:
        return None
    return node_id, generation


def _iter_range_entries(ranges: Any) -> Iterable[Any]:
    if hasattr(ranges, "values"):
        return ranges.values()
    return ranges


def _check_ranges_and_version(document: Any, index: ReferenceIndex, violations: List[Violation]) -> None:
    """Range and document-version consistency against live generations ({p084}, {p083})."""

    ranges = getattr(document, "ranges", None)
    if ranges:
        for entry in _iter_range_entries(ranges):
            fields = _range_fields(entry)
            if fields is None:
                continue
            node_id, recorded_generation = fields
            live_generation = index.get_generation(node_id)
            if live_generation is None or live_generation != recorded_generation:
                violations.append((
                    "range-version",
                    f"range for node {node_id} is stale: recorded generation "
                    f"{recorded_generation!r}, live generation {live_generation!r}",
                ))

    version = getattr(document, "version", None)
    version_generations = getattr(document, "version_generations", None)
    if version is not None and version_generations:
        for node_id, recorded_generation in version_generations.items():
            live_generation = index.get_generation(node_id)
            if live_generation is None or live_generation != recorded_generation:
                violations.append((
                    "range-version",
                    f"document version {version!r} is inconsistent: node {node_id} "
                    f"recorded generation {recorded_generation!r}, live generation "
                    f"{live_generation!r}",
                ))


def validate_full_document(
    document: Any,
    *,
    resolver: Optional[DocumentResolver] = None,
) -> FullIntegrityReport:
    """Validate the whole document's reference integrity before export ({p083}).

    Read-only in every branch: never mutates ``document``, its index
    maps, or any cache entry, whether it returns normally or raises.
    Runs, aggregating every violation rather than stopping at the first:
    id/short_id uniqueness, full local resolvability, external-address
    syntax and resolver-based liveness, direct-object cache conformance,
    full parent/child and incoming/outgoing symmetry, cycle absence, and
    range/version consistency. Raises :class:`FullIntegrityError` if any
    check found a violation; otherwise returns a :class:`FullIntegrityReport`.
    """

    index = _index_of(document)
    violations: List[Violation] = []

    ids_checked = _check_uniqueness(document, index, violations)
    _check_full_symmetry_and_cache(index, violations)
    external_checked, unresolved_external = _check_local_and_external(index, resolver, violations)
    _check_cycles(index, violations)
    _check_ranges_and_version(document, index, violations)

    if violations:
        raise FullIntegrityError(violations)

    return FullIntegrityReport(
        nodes_checked=len(index.nodes_by_id),
        ids_checked=ids_checked,
        external_references_checked=external_checked,
        unresolved_external=unresolved_external,
    )
