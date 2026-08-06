"""Automatic post-mutation reparse of a single edited node (concept C-006,
{p098}, {p099}).

Scope: this module owns exactly one stage -- what happens *after* a node's
text content has already changed through ``set_body`` or a source-fragment
update, invoked by the sibling ``updates.py`` file immediately once that
change has been applied. It never decides *when* such a change occurs, and
it never applies one itself; it only decides what the format plugin's
``parse_fragment`` result means for the edited node's structure.

Fragment-level only -- never a whole-document reparse: this stage always
calls the injected ``parse_fragment`` callable, the fragment-level half of
``core/plugin_boundary.py``'s ``FormatBoundary`` (``source: str ->
Node``), and nothing here ever calls, references, or approximates the
whole-document counterpart (``FormatBoundary.parse_document``). A full
reparse of an entire file is a different, separately governed operation
(permitted only on initial load, an explicit full check, recovery from an
external change, or as the closing check of a completed batch) and is out
of scope for this file in every code path: calling
:func:`reparse_edited_node` any number of times for a batch of ``K`` edited
nodes triggers at most ``K`` fragment-level ``parse_fragment`` calls -- one
per node whose type admits nested structure -- and zero whole-document
parses, never a whole-document reparse per element and never one at all
from this module.

Consult-before-parse: per {p098}, ``parse_fragment`` is only invoked when
the caller-supplied ``admits_nested_structure`` predicate says the edited
node's type admits nested structure. That predicate is where a caller
consults the format plugin's declared ``capabilities`` and its node-kind
policy (``plugin_boundary.py`` does not yet define a concrete capability/
node-kind-policy surface in this worktree, so -- mirroring how
``validation.py`` already takes ``is_type_compatible`` and ``next_short_id``
as caller-injected callables for the same reason -- this file takes the
already-consulted decision as one injected callable rather than importing,
stubbing, or guessing at a plugin contract that is not merged yet). The
concrete parser itself is likewise never imported here: ``parse_fragment``
is an injected callable, satisfied later by a real plugin.

Three outcomes, per {p098}/{p099}:

* The node's type does not admit nested structure: ``parse_fragment`` is
  never called at all.
* ``parse_fragment`` returns a ``str``: a successful outcome meaning no
  recognized structure; the node remains textual and no child is routed
  anywhere.
* ``parse_fragment`` returns a structured object or a set of common-model
  nodes: the edited node keeps its own identity as the container, and
  every new child is preflighted via the sibling ``validation.py``'s
  :func:`~tree_engine.core.validation.validate_mutation` and then applied
  via the sibling ``operations.py``'s :func:`~tree_engine.core.operations.insert`
  -- the same shared preflight/atomic-apply pair every other mutation in
  this concept uses, so short_id assignment, index-map registration, and
  reference resolution happen exactly as they do for any other insert.

Failure, per {p099}: a raised exception or a return value that is not a
``str`` and not a recognizable node/node-sequence shape is reported as
:class:`ReparseError` carrying ``ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED``.
A return value shaped like structured content that nonetheless violates the
common-model contract (bad node shape, an empty node set, a batch-internal
node_id collision, or a new child that fails preflight against its new
parent) is reported as :class:`ReparseError` carrying
``ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR``. In both cases nothing from the
rejected parse result is ever written to the tree -- the whole batch of new
children is preflighted to completion before any one of them is applied --
and plain-text fallback is never substituted for a local mutation; the
caller (``updates.py``) is expected to catch :class:`ReparseError` and roll
the entire mutation back, since only it owns the text change this stage
was invoked to interpret.

This file duplicates nothing from its already-merged siblings: it imports
``validate_mutation``/``ValidationError`` from ``validation.py``,
``insert``/``MutationError``/``MutationResult`` from ``operations.py``, and
``generate_node_id`` from ``identity.py``, and otherwise stays duck-typed
about the tree/node shape exactly as those two files already are, so it
needs no change when the concrete live-tree/document type lands later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from tree_engine.core.identity import generate_node_id as _generate_node_id
from tree_engine.core.operations import MutationError, MutationResult, insert
from tree_engine.core.validation import ValidationError, validate_mutation
from tree_engine.errors import ErrorCode

__all__ = [
    "STATUS_SKIPPED",
    "STATUS_TEXTUAL",
    "STATUS_STRUCTURED",
    "ReparseError",
    "ReparseOutcome",
    "reparse_edited_node",
]

# ReparseOutcome.status values.
STATUS_SKIPPED = "skipped_no_nested_structure"
STATUS_TEXTUAL = "textual"
STATUS_STRUCTURED = "structured"


class ReparseError(Exception):
    """Raised instead of applying anything, per {p099}.

    ``code`` is either ``ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED`` (a raised
    exception or an unrecognized return type from ``parse_fragment``) or
    ``ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR`` (a recognizable-but-invalid
    common-model result). ``errors`` optionally carries the underlying
    :class:`~tree_engine.core.validation.ValidationError` list when the
    failure came from routing a new child through the shared preflight.
    """

    def __init__(self, code: ErrorCode, message: str, errors: Sequence[ValidationError] = ()) -> None:
        self.code = code
        self.errors: List[ValidationError] = list(errors)
        super().__init__(f"[{code.value}] {message}")


@dataclass(frozen=True)
class ReparseOutcome:
    """Result of one successful :func:`reparse_edited_node` call.

    ``node_id`` is the edited node's own, unchanged identity. ``text`` is
    populated only for :data:`STATUS_TEXTUAL`. ``applied`` is populated
    only for :data:`STATUS_STRUCTURED`: the ordered
    :class:`~tree_engine.core.operations.MutationResult` of each new child,
    in the order it was inserted.
    """

    status: str
    node_id: Any
    text: Optional[str] = None
    applied: Tuple[MutationResult, ...] = ()


# -- internal helpers --------------------------------------------------------


def _looks_like_common_model_node(value: Any) -> bool:
    """Minimal shape check for "a common-model node": a non-empty ``kind``
    string, and a ``children`` attribute that, when present, is an ordered
    sequence. Duck-typed on purpose -- mirrors the rest of this concept's
    already-merged files, none of which require a specific concrete node
    class."""

    kind = getattr(value, "kind", None)
    if not isinstance(kind, str) or not kind:
        return False
    children = getattr(value, "children", None)
    if children is not None and not isinstance(children, (list, tuple)):
        return False
    return True


def _validate_common_model_shape(root: Any) -> None:
    """Recursively confirm ``root`` and every descendant satisfies
    :func:`_looks_like_common_model_node`. Raises :class:`ReparseError`
    with ``FORMAT_PLUGIN_CONTRACT_ERROR`` at the first violation."""

    stack = [root]
    while stack:
        node = stack.pop()
        if not _looks_like_common_model_node(node):
            raise ReparseError(
                ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                f"parse_fragment result is not a valid common-model node: {node!r}",
            )
        stack.extend(getattr(node, "children", None) or ())


def _collect_fragment_nodes(root: Any) -> List[Any]:
    """Pre-order ``root`` and every descendant (mirrors ``operations.py``'s
    own ``_fragment_nodes``, duplicated rather than imported since it is a
    private helper of that module)."""

    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        stack = list(getattr(node, "children", None) or ()) + stack
    return ordered


def _classify_parse_result(raw_result: Any) -> List[Any]:
    """Turn a non-``str`` ``parse_fragment`` return into an ordered list of
    new root nodes ("a structured object or a set of common-model nodes").

    A single node-shaped object becomes a one-element list. A non-empty
    ``list``/``tuple`` is the explicit "set of nodes" form. Anything else
    -- not a recognizable node shape at all, or an empty sequence -- is
    rejected: an unrecognized shape never even claims to be structured
    content, so it is ``FORMAT_FRAGMENT_PARSE_FAILED``; an empty sequence
    claims to be a node set but holds no content, so it is
    ``FORMAT_PLUGIN_CONTRACT_ERROR``.
    """

    if isinstance(raw_result, (list, tuple)):
        if not raw_result:
            raise ReparseError(
                ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                "parse_fragment returned an empty node sequence",
            )
        return list(raw_result)
    if _looks_like_common_model_node(raw_result):
        return [raw_result]
    raise ReparseError(
        ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED,
        f"parse_fragment returned an unrecognized type: {type(raw_result).__name__}",
    )


def _assign_missing_identity(roots: Sequence[Any], generate_id: Callable[[], Any]) -> None:
    """Assign a fresh UUID4 ``node_id`` (per {p098}, "new child nodes...
    receive new UUID4s") to every node across ``roots`` that does not
    already carry one. A node that refuses the assignment (e.g. an
    immutable object that raises on attribute assignment) is a
    common-model contract violation, not a parser failure -- this engine's
    mutation pipeline requires new content to accept an assigned
    identity."""

    for root in roots:
        for node in _collect_fragment_nodes(root):
            if getattr(node, "node_id", None) is None:
                try:
                    node.node_id = generate_id()
                except (AttributeError, TypeError) as exc:
                    raise ReparseError(
                        ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                        f"node does not accept an assigned node_id: {node!r}",
                    ) from exc


def _check_no_duplicate_node_ids(nodes: Sequence[Any]) -> None:
    """Guard against a node_id repeated within the same parsed batch, which
    ``validate_mutation`` cannot see on its own since each call only checks
    one root against the document (mirrors ``operations.replace_range``'s
    own same-batch collision guard)."""

    seen: set = set()
    for node in nodes:
        raw_id = getattr(node, "node_id", None)
        if raw_id is not None and raw_id in seen:
            raise ReparseError(
                ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                f"node_id repeated among parsed children: {raw_id!r}",
            )
        seen.add(raw_id)


# -- public entry point -------------------------------------------------------


def reparse_edited_node(
    document: Any,
    edited_node: Any,
    edited_text: str,
    *,
    source_format_id: str,
    admits_nested_structure: Callable[[Any], bool],
    parse_fragment: Callable[..., Any],
    generate_node_id: Callable[[], Any] = _generate_node_id,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None,
    next_short_id: Optional[Callable[[], Any]] = None,
) -> ReparseOutcome:
    """Run the {p098}/{p099} post-mutation reparse stage for one node whose
    text content was just changed by ``set_body`` or a source-fragment
    update in the sibling ``updates.py`` file.

    Args:
        document: the target document, read only via ``document.nodes_by_id``
            and passed through, unread otherwise, to ``validate_mutation``
            and ``insert``.
        edited_node: the node whose text just changed. Its own identity is
            never modified by this function; new children, if any, are
            attached under it.
        edited_text: the node's new text content, exactly as just written
            by ``set_body``/the source-fragment update -- this file does
            not read it from anywhere else.
        source_format_id: the format id passed through to ``parse_fragment``.
        admits_nested_structure: caller-supplied predicate, already having
            consulted the format plugin's capabilities and node-kind
            policy, deciding whether ``edited_node``'s type may hold nested
            structure at all. ``parse_fragment`` is never called when this
            returns falsy.
        parse_fragment: the injected fragment parser, called as
            ``parse_fragment(edited_text, source_format_id=source_format_id)``,
            mirroring ``FormatBoundary.parse_fragment``'s signature. Never
            imported or stubbed by this module -- always caller-supplied.
        generate_node_id: the fresh-UUID4 allocator for new children,
            defaulting to ``identity.generate_node_id``.
        is_type_compatible, references, loaded_documents, used_short_ids,
            next_short_id: threaded through, unchanged, to every
            ``validate_mutation``/``insert`` call this function makes --
            same meaning as on those two functions.

    Returns:
        A :class:`ReparseOutcome` describing which of the three {p098}
        outcomes occurred.

    Raises:
        ReparseError: on any of the {p099} rejection conditions. Nothing is
            written to ``document`` in that case.
    """

    node_id = getattr(edited_node, "node_id", None)

    if not admits_nested_structure(edited_node):
        return ReparseOutcome(status=STATUS_SKIPPED, node_id=node_id)

    try:
        raw_result = parse_fragment(edited_text, source_format_id=source_format_id)
    except Exception as exc:
        raise ReparseError(
            ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED,
            f"parse_fragment raised for node {node_id!r}: {exc}",
        ) from exc

    if isinstance(raw_result, str):
        return ReparseOutcome(status=STATUS_TEXTUAL, node_id=node_id, text=raw_result)

    roots = _classify_parse_result(raw_result)
    for root in roots:
        _validate_common_model_shape(root)

    _assign_missing_identity(roots, generate_node_id)

    all_new_nodes: List[Any] = []
    for root in roots:
        all_new_nodes.extend(_collect_fragment_nodes(root))
    _check_no_duplicate_node_ids(all_new_nodes)

    # Preflight the whole batch to completion first -- a dry run, with
    # next_short_id withheld so no allocator side effect happens here --
    # so that either every new root is admissible or none of them are ever
    # written to the tree. The real allocator only runs once, below, during
    # the actual apply pass.
    dry_errors: List[ValidationError] = []
    for root in roots:
        result = validate_mutation(
            document, root, parent=edited_node, position="last_child",
            is_type_compatible=is_type_compatible, references=references,
            loaded_documents=loaded_documents, used_short_ids=used_short_ids,
            next_short_id=None,
        )
        dry_errors.extend(result.errors)
    if dry_errors:
        raise ReparseError(
            ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
            "parsed content failed preflight validation against its new parent",
            errors=dry_errors,
        )

    # Every root passed the dry run; apply each through the same atomic
    # insert path every other mutation in this concept uses.
    applied: List[MutationResult] = []
    for root in roots:
        try:
            applied.append(
                insert(
                    document, root, position="last_child", parent=edited_node,
                    is_type_compatible=is_type_compatible, references=references,
                    loaded_documents=loaded_documents, used_short_ids=used_short_ids,
                    next_short_id=next_short_id,
                )
            )
        except MutationError as exc:
            raise ReparseError(
                ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                "parsed content failed atomic application after passing preflight",
                errors=exc.errors,
            ) from exc

    return ReparseOutcome(status=STATUS_STRUCTURED, node_id=node_id, applied=tuple(applied))
