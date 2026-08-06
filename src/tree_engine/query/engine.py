"""Top-level entry point of the ported cst_query engine (concept C-009,
atomic step G-018/T-001/A-004).

Scope, per {p005}, {p018}, {p019}, {p020}, and {p040}: composes four
already-finished pieces -- the unchanged legacy selector parser/AST and the
three sibling modules delivered earlier under this tactical step (T-001)
-- into the one query entry point a caller invokes. No new selector syntax,
no new predicate/combinator/pseudo-selector semantics:

* ``ai_editor.cst_query.parser.parse_selector``/``ai_editor.cst_query.ast``
  are imported unchanged, used exactly as the legacy executor
  (``ai_editor.cst_query.executor``) used them -- this module mirrors that
  executor's ``query_source``/``_eval_query``/``_apply_step``/
  ``_apply_combinator`` shape, walking the common tree instead of a LibCST
  index. A malformed selector's ``QueryParseError`` propagates untouched
  from the parser -- never caught or wrapped here.
* ``TreeTraversalAdapter.iter_nodes`` supplies every node this module ever
  sees: one raw, role-tagged, pre-order walk, indexed once by ``node_id``
  for predicate lookup, ancestor-chain combinator checks, and assembly.
* Node-type matching reuses the adapter's own proven rule for what it
  already covers -- a standard role (from ``resolve_semantic_role``, never
  re-derived) or an exact literal ``kind`` string, per {p018} -- and adds
  only the one legacy capability the adapter's public surface has no room
  for: the ``"Type:*"`` prefix/suffix type *pattern* {p018} requires stay
  preserved (the reused parser still emits a ``node_type`` ending in
  ``":*"`` for it). Modeled on the legacy executor's own wildcard branch:
  case-insensitive ``kind`` prefix/suffix, or role equality when the
  pattern's stem itself names a standard role.
* ``evaluate_predicates`` filters each step's type-matched candidates by
  their already-parsed ``Predicate`` tuple, reading attributes off the raw
  node ({p019}).
* ``build_query_match`` is the sole assembler of every returned record
  ({p021}), called once per indexed node while indexing (the same
  ``to_hex``/``build_node_address_view`` pairing the adapter's own
  ``iter_matching_nodes`` uses), so every match here is shaped identically
  to one the adapter would build.

Combinators ({p020}: descendant, direct child) and ``:first``/``:last``/
``:nth`` are evaluated over the ordered step chain, mirroring the legacy
executor: each step's candidates are matched independently over the whole
indexed tree, then narrowed to those related to the previous step's
survivors by the combinator between them (child: immediate parent must
survive; descendant: any ancestor must survive), pseudos applied last per
step. The legacy ``:not(...)`` pseudo (not enumerated among this step's
required pseudo-selectors, but present in the reused AST) is still honored
for full parity: evaluated by recursing into this same machinery with the
candidate universe narrowed to just the one node under test, mirroring
``_eval_query([node], step.not_selector)``.

Never reparses the source: every lookup reads the already-built
``Document``/``Node`` graph from one ``iter_nodes()`` walk, per {p040}.
On-request source inclusion renders a matched node's text via the loaded
plugin's duck-typed ``render_fragment`` (the same "if callable, use it"
convention ``resolve_semantic_role`` established for ``role_for``) --
regenerating text from the already-parsed tree via the plugin's own code
generator, never by reparsing -- falling back to the node's own stored
``content`` field (as ``tree_engine.core.node_types`` wrappers use it), and
to ``None`` if neither applies.

Where this module detects, only after the reused parser already
succeeded, that the resulting chain has no executable first step (a
``Query`` with no ``SelectorStep`` -- unreachable through
``parse_selector`` on real text, but reachable by a caller driving
:meth:`TreeQueryEngine.execute` directly with a hand-built ``Query``), it
raises the same unchanged ``QueryParseError`` with
``ErrorCode.INVALID_SELECTOR`` in its ``details`` payload -- the
convention the sibling predicate module already established -- rather
than a second exception type.

Out of scope, owned by sibling artifacts under this tactical step: new
predicate/combinator syntax, tree traversal internals (delegated to the
adapter), and predicate evaluation internals.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from tree_engine.query.selector import (
    Combinator,
    PseudoKind,
    Query,
    QueryParseError,
    SelectorStep,
    parse_selector,
)

from tree_engine.core.address import build_node_address_view
from tree_engine.core.nodes import Document, Node
from tree_engine.core.short_id import to_hex
from tree_engine.errors import ErrorCode
from tree_engine.query.adapter import TreeTraversalAdapter
from tree_engine.query.predicates import evaluate_predicates
from tree_engine.query.results import QueryMatch, build_query_match

__all__ = [
    "TreeQueryEngine",
    "query",
]

# The four standard semantic roles a "Type:*" pattern's stem, or a bare
# node-type selector, may name instead of a literal kind string -- kept in
# lockstep with ``tree_engine.query.adapter``'s own alias set ({p018}).
_STANDARD_ROLE_NAMES = frozenset({"function", "method", "class", "module"})

# One indexed entry per node: the raw node (for predicate reads and
# node-type matching), its ancestor chain as a root-to-parent tuple of
# ``str(node_id)`` (for combinator checks), its resolved semantic role
# (from the adapter, never re-derived here), and its already-assembled
# ``QueryMatch`` (built once per node while indexing, per {p021}).
_IndexEntry = Tuple[Node, Tuple[str, ...], str, QueryMatch]
_NodeIndex = Mapping[str, _IndexEntry]

# One candidate mid-evaluation: the node's own id, its ancestor id chain,
# and the already-assembled ``QueryMatch`` the results module produced.
_Candidate = Tuple[str, Tuple[str, ...], QueryMatch]


def _unexecutable_selector_error(reason: str) -> QueryParseError:
    """Build the shared legacy exception for a post-parse unexecutable chain.

    Always the same, unchanged ``QueryParseError`` -- never a subclass --
    carrying ``ErrorCode.INVALID_SELECTOR`` in its existing ``details``
    dict, exactly as ``tree_engine.query.predicates`` already does for its
    own post-parse rejections.
    """

    return QueryParseError(
        f"selector step chain is not executable: {reason}",
        details={"error_code": ErrorCode.INVALID_SELECTOR},
    )


def _require_executable(parsed_query: Query) -> None:
    """Reject a parsed ``Query`` with no executable first step.

    Not reachable through ``parse_selector`` on any real selector text --
    its own transformer already refuses to build a ``Query`` with no first
    step -- but a caller driving :meth:`TreeQueryEngine.execute` directly
    with a hand-built ``Query`` (bypassing text parsing entirely) can reach
    this, so it is checked here rather than assumed impossible.
    """

    if not isinstance(parsed_query, Query) or not isinstance(parsed_query.first, SelectorStep):
        raise _unexecutable_selector_error("no executable first step")


def _index_document(adapter: TreeTraversalAdapter) -> _NodeIndex:
    """Walk the whole document exactly once, via the adapter, and pre-build
    every node's {p021} result record plus the bookkeeping later steps need.

    The single full traversal any query needs: node-type/predicate
    filtering reads the raw node and role; combinator evaluation reads the
    ancestor id chain; final assembly reuses the already-built
    ``QueryMatch`` (via the sibling results module's own constructor)
    rather than re-deriving it per step.
    """

    index: Dict[str, _IndexEntry] = {}
    for node, ancestors, role in adapter.iter_nodes():
        ancestor_ids = tuple(str(ancestor.node_id) for ancestor in ancestors)
        parent_path = tuple(
            build_node_address_view(ancestor.node_id, ancestor.short_id) for ancestor in ancestors
        )
        match = build_query_match(node, role, to_hex(node.short_id), parent_path)
        index[str(node.node_id)] = (node, ancestor_ids, role, match)
    return index


def _node_type_matches(node: Node, role: str, node_type: Optional[str]) -> bool:
    """True when ``node`` (already tagged with ``role``) satisfies ``node_type``.

    Byte-for-byte the same rule ``tree_engine.query.adapter`` already
    applies for the cases it covers -- ``None``/``"*"`` matches everything;
    one of the four standard role names matches by role equality; anything
    else matches only the node's own literal ``kind`` string -- plus the
    one legacy capability that adapter has no public surface for: a
    ``"Type:*"`` prefix/suffix pattern (produced by the reused parser's own
    ``node_type`` transformer). Modeled on the legacy executor's own
    wildcard branch: an empty stem matches everything; a stem naming a
    standard role matches by role; any other stem matches
    case-insensitively as a prefix or suffix of the node's ``kind``.
    """

    if node_type is None or node_type == "*":
        return True
    if node_type.endswith(":*"):
        stem = node_type[:-2].strip().lower()
        if not stem:
            return True
        if stem in _STANDARD_ROLE_NAMES:
            return role == stem
        kind = str(node.kind).lower()
        return kind.startswith(stem) or kind.endswith(stem)
    normalized = node_type.lower()
    if normalized in _STANDARD_ROLE_NAMES:
        return role == normalized
    return str(node.kind) == node_type


def _apply_pseudos(candidates: List[_Candidate], pseudos: Sequence[Any]) -> List[_Candidate]:
    """Apply ``:first``/``:last``/``:nth`` in order, mirroring the legacy
    executor's ``_apply_step``, which always narrows *after* type/predicate/
    ``:not`` filtering has already produced the full matched list for this
    step. ``:not`` itself never appears here: the reused parser routes it
    into ``SelectorStep.not_selector`` instead of ``SelectorStep.pseudos``.
    """

    for pseudo in pseudos:
        if pseudo.kind == PseudoKind.FIRST:
            candidates = candidates[:1]
        elif pseudo.kind == PseudoKind.LAST:
            candidates = candidates[-1:] if candidates else []
        elif pseudo.kind == PseudoKind.NTH:
            index = pseudo.index if pseudo.index is not None else 0
            candidates = [candidates[index]] if 0 <= index < len(candidates) else []
    return candidates


def _not_excludes(index: _NodeIndex, not_selector: Query, node_id: str) -> bool:
    """True when ``not_selector`` matches ``node_id`` (the owning
    ``:not(...)`` step must then exclude it), mirroring the legacy
    executor's ``_eval_query([node], step.not_selector)``: the sub-query's
    candidate universe is narrowed to just this one node throughout.
    """

    return bool(_run_query(index, not_selector, universe=frozenset({node_id})))


def _step_candidates(
    index: _NodeIndex, step: SelectorStep, universe: Optional[FrozenSet[str]]
) -> List[_Candidate]:
    """Resolve one selector step's surviving candidates over ``index``.

    In legacy order: type-match (see :func:`_node_type_matches`);
    restrict to ``universe`` when narrowing for a ``:not(...)`` sub-query
    (``None`` means "the whole document", the ordinary case); filter by
    this step's predicates via the sibling predicate module; filter by
    ``:not(...)`` when present; finally narrow by any
    ``:first``/``:last``/``:nth``.
    """

    survivors: List[_Candidate] = []
    for node_id, (node, ancestor_ids, role, match) in index.items():
        if universe is not None and node_id not in universe:
            continue
        if not _node_type_matches(node, role, step.node_type):
            continue
        if not evaluate_predicates(step.predicates, node):
            continue
        if step.not_selector is not None and _not_excludes(index, step.not_selector, node_id):
            continue
        survivors.append((node_id, ancestor_ids, match))
    return _apply_pseudos(survivors, step.pseudos)


def _apply_combinator(
    prev: List[_Candidate], next_candidates: List[_Candidate], combinator: Combinator
) -> List[_Candidate]:
    """Narrow ``next_candidates`` to those related to a ``prev`` survivor
    by ``combinator``, exactly mirroring the legacy executor's
    ``_apply_combinator``: direct child compares only the immediate parent
    (the last entry of the ancestor id chain); descendant and recursive
    descendant (both space- and ``//``-spelled in the legacy grammar) admit
    a match anywhere in the ancestor chain.
    """

    if not prev or not next_candidates:
        return []
    prev_ids = {node_id for node_id, _ancestors, _match in prev}
    if combinator == Combinator.CHILD:
        return [c for c in next_candidates if c[1] and c[1][-1] in prev_ids]
    return [c for c in next_candidates if any(ancestor_id in prev_ids for ancestor_id in c[1])]


def _run_query(
    index: _NodeIndex, parsed_query: Query, *, universe: Optional[FrozenSet[str]] = None
) -> List[_Candidate]:
    """Evaluate every step of ``parsed_query`` in order, exactly mirroring
    the legacy executor's ``_eval_query``: the first step's candidates come
    from the whole (or, under ``:not(...)``, the narrowed) universe, and
    each subsequent step's candidates are narrowed again by the combinator
    that precedes it.
    """

    current = _step_candidates(index, parsed_query.first, universe)
    for combinator, step in parsed_query.rest:
        next_candidates = _step_candidates(index, step, universe)
        current = _apply_combinator(current, next_candidates, combinator)
    return current


def _render_source(plugin: Any, node: Node) -> Optional[str]:
    """Render ``node``'s own source text on request, never by reparsing.

    Prefers a duck-typed, callable ``plugin.render_fragment`` (the same
    "if callable, use it" convention ``tree_engine.query.adapter
    .resolve_semantic_role`` already established for ``role_for``): this
    regenerates the one node's text from the already-parsed tree through
    the format plugin's own code generator, never through the document's
    source-parsing entry point. Falls back to the node's own stored
    ``content`` field -- the convention already used by
    ``tree_engine.core.node_types`` extension wrappers -- when no such
    renderer is available, and to ``None`` when neither applies.
    """

    renderer = getattr(plugin, "render_fragment", None)
    if callable(renderer):
        rendered = renderer(node)
        if isinstance(rendered, str):
            return rendered
    fields = getattr(node, "fields", None)
    if isinstance(fields, Mapping):
        content = fields.get("content")
        if isinstance(content, str):
            return content
    return None


def _finalize(
    candidates: List[_Candidate], index: _NodeIndex, plugin: Any, include_source: bool
) -> List[QueryMatch]:
    """Turn surviving candidates into the ordered ``QueryMatch`` list.

    Each candidate's ``QueryMatch`` was already assembled by the sibling
    results module while indexing; this function performs no further shape
    computation beyond, on request, attaching rendered ``source`` text via
    ``dataclasses.replace`` -- never rebuilding any other field.
    """

    if not include_source:
        return [match for _node_id, _ancestors, match in candidates]
    results: List[QueryMatch] = []
    for node_id, _ancestors, match in candidates:
        node = index[node_id][0]
        results.append(replace(match, source=_render_source(plugin, node)))
    return results


class TreeQueryEngine:
    """Binds one already-loaded ``Document`` and its format plugin to the
    full ported cst_query engine (concept C-009): the reused legacy
    selector parser, the sibling traversal adapter, the sibling predicate
    evaluator, and the sibling result-record model, composed into one
    ``query``/``execute`` entry point.

    ``document`` and ``plugin`` are handed straight to a new
    :class:`~tree_engine.query.adapter.TreeTraversalAdapter`, stored
    exactly as that adapter already documents: the caller is expected to
    have already loaded the document's tree and resolved its format
    plugin, e.g. via ``tree_engine.plugins.selection``.
    """

    def __init__(self, document: Document, plugin: Any) -> None:
        self._adapter = TreeTraversalAdapter(document, plugin)

    @property
    def adapter(self) -> TreeTraversalAdapter:
        """The ``TreeTraversalAdapter`` bound to this engine's document/plugin."""

        return self._adapter

    def query(self, selector: str, *, include_source: bool = False) -> List[QueryMatch]:
        """Parse ``selector`` (via the reused, unchanged legacy parser) and
        run it. A malformed ``selector`` propagates
        ``ai_editor.core.exceptions.QueryParseError`` straight from the
        parser, untouched.
        """

        parsed_query = parse_selector(selector)
        return self.execute(parsed_query, include_source=include_source)

    def execute(self, parsed_query: Query, *, include_source: bool = False) -> List[QueryMatch]:
        """Run an already-parsed legacy ``Query`` against this engine's
        document, without ever reparsing its source text ({p040}).

        Raises the legacy ``QueryParseError`` (``details["error_code"] is
        ErrorCode.INVALID_SELECTOR``) when ``parsed_query`` has no
        executable first step -- see :func:`_require_executable`. Returns
        the ordered list of surviving :class:`~tree_engine.query.results
        .QueryMatch` records, source text attached only when
        ``include_source`` is true.
        """

        _require_executable(parsed_query)
        index = _index_document(self._adapter)
        candidates = _run_query(index, parsed_query)
        return _finalize(candidates, index, self._adapter.plugin, include_source)


def query(
    document: Document,
    plugin: Any,
    selector: str,
    *,
    include_source: bool = False,
) -> List[QueryMatch]:
    """Module-level convenience wrapper: ``TreeQueryEngine(document,
    plugin).query(selector, include_source=include_source)``, for a caller
    that does not need to keep the engine instance around.
    """

    return TreeQueryEngine(document, plugin).query(selector, include_source=include_source)
