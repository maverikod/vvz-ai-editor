"""Transactional batch execution and concurrency control (concept C-007).

Scope: this module owns :class:`TransactionBatch` (the request shape),
:class:`TransactionCoordinator` (validates, runs, commits or rolls back a
batch), and :class:`IsolatedTransactionState` (the private overlay one
touched document gets for one batch). It composes the already-merged
single-mutation operations -- never reimplementing what they already do --
and the already-merged :class:`~tree_engine.core.locking.DocumentLockCoordinator`
for per-document serialization and deterministic multi-document ordering.

Per {p012}/{rgi6}: a batch first checks request shape, ``expected_version``,
and static constraints -- once, not per operation -- then runs its
operations in order against an isolated transactional working state, where
operation N+1 sees the results of operations 1..N of the same batch. The
batch either publishes completely, as one public ``document_version``
increment, or rolls back completely; external readers never observe
anything in between. Per {p035}, a transaction spanning several documents
acquires all of their locks in ascending UUID4 order, releasing them only
after commit or rollback -- automatic merging is forbidden, and a stale
``expected_version`` is refused, never merged. Per {p016}, this module runs
at most one full-document control check per touched document, after the
whole batch -- never a check per element.

Isolation design (this file's own choice; {p012}/{rgi6} require "isolated
transactional working state" without dictating its mechanism): each touched
document gets a private, deep-copied overlay -- its own ``nodes_by_id``,
``short_id_index``, and ``root`` -- built once when the batch starts. Every
operation runs against that overlay only, via the same, already-merged
``insert``/``delete``/``replace_range`` (``operations.py``) and
``set_body``/``replace_node_id`` (``updates.py``) functions used everywhere
else in this concept -- this file adds no mutation logic, only the
overlay/publish/discard plumbing around them. The live document is never
written to until every operation and the closing full-document check
succeed; committing then just swaps the three overlay attributes onto it
and advances ``document_version`` by exactly one. Rolling back is declining
to publish: the live document was never touched, so every UUID4/short_id a
rolled-back operation minted lived only in the discarded overlay -- never
resolvable through the live document. Exactly one overlay per touched
document is ever live, and it never outlives its batch: not multi-version
storage, only a private, ephemeral working copy.

Duck-typed ``document``: ``nodes_by_id`` (mutable ``node_id -> node``),
optional ``short_id_index``/``document_id``/``root``, and
``document_version`` (an ``int`` counter read for ``expected_version`` and
written to publish the next one; ``version`` is an accepted read fallback,
mirroring ``subtree_copy.py``). Imports: ``insert``/``delete``/
``replace_range`` (``operations.py``) and ``set_body``/``replace_node_id``
(``updates.py``, where this worktree actually defines them) are the single
mutation operations a batch composes. ``DocumentLockCoordinator``
(``locking.py``) and ``validate_mutation`` (``validation.py``, both
indirectly via every operation above, and directly, once per touched
document, for the closing {p016} check) are reused unmodified. ``Document``
(``nodes.py``) types the documents a caller passes in.

Non-goals: no per-element full parses/checks, no automatic conflict
resolution/merging, no multi-version storage. Source-of-truth labels
honored here: {p012}, {p016}, {p035}, {rgi6}.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from uuid import UUID

from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.nodes import Document
from tree_engine.core.operations import delete, insert, replace_range
from tree_engine.core.updates import replace_node_id as _update_replace_node_id
from tree_engine.core.updates import set_body as _update_set_body
from tree_engine.core.validation import ValidationError, validate_mutation
from tree_engine.errors import ErrorCode

__all__ = [
    "TransactionError",
    "Operation",
    "TransactionBatch",
    "CommitResult",
    "IsolatedTransactionState",
    "TransactionCoordinator",
]

_OPERATION_KINDS = ("insert", "delete", "replace_range", "set_body", "replace_node_id")
_ABSENT = object()


class TransactionError(Exception):
    """Raised when a batch is refused outright or must be rolled back.

    ``code`` is the originating :class:`~tree_engine.errors.ErrorCode`
    (``DOCUMENT_VERSION_CONFLICT`` for a stale ``expected_version``,
    ``CONCURRENT_TREE_MODIFICATION`` for a post-batch integrity failure or
    an out-of-band change under the lock, or a shape-check code). ``errors``
    optionally carries the underlying
    :class:`~tree_engine.core.validation.ValidationError` list. Raising this
    always means no document touched by the batch was mutated.
    """

    def __init__(self, code: ErrorCode, message: str, errors: Sequence[ValidationError] = ()) -> None:
        self.code = code
        self.errors: List[ValidationError] = list(errors)
        super().__init__(f"[{code.value}] {message}")


@dataclass(frozen=True)
class Operation:
    """One entry of a :class:`TransactionBatch`: ``kind`` is one of
    ``_OPERATION_KINDS``; ``document_id`` is ``None`` for the batch's own
    document (the ordinary, single-document case); ``args``/``kwargs`` are
    forwarded verbatim to the matching operation function, against that
    document's overlay."""

    kind: str
    document_id: Optional[UUID] = None
    args: Tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class TransactionBatch:
    """One request: an ordered list of operations to run as a single unit.

    ``document_id`` is the batch's primary (and usually only) document.
    ``expected_versions`` maps each touched document_id to the
    ``document_version`` last observed by the caller; an absent id is not
    version-checked. Per {p012}, ``expected_version`` is checked once, at
    batch start -- never per operation. The builder methods each append one
    :class:`Operation` and return ``self`` for fluent assembly.
    """

    document_id: UUID
    expected_versions: Dict[UUID, Any] = field(default_factory=dict)
    operations: List[Operation] = field(default_factory=list)

    def _add(self, kind: str, *args: Any, document_id: Optional[UUID] = None, **kwargs: Any) -> "TransactionBatch":
        self.operations.append(Operation(kind=kind, document_id=document_id, args=args, kwargs=kwargs))
        return self

    def insert(self, incoming: Any, *, position: str, document_id: Optional[UUID] = None, **kwargs: Any) -> "TransactionBatch":
        return self._add("insert", incoming, position=position, document_id=document_id, **kwargs)

    def delete(self, targets: Any, *, document_id: Optional[UUID] = None) -> "TransactionBatch":
        return self._add("delete", targets, document_id=document_id)

    def replace_range(self, targets: Any, incoming: Any, *, document_id: Optional[UUID] = None, **kwargs: Any) -> "TransactionBatch":
        return self._add("replace_range", targets, incoming, document_id=document_id, **kwargs)

    def set_body(self, node: Any, body: Any, *, document_id: Optional[UUID] = None, **kwargs: Any) -> "TransactionBatch":
        return self._add("set_body", node, body, document_id=document_id, **kwargs)

    def replace_node_id(self, old_node_id: UUID, new_node_id: UUID, *, document_id: Optional[UUID] = None, **kwargs: Any) -> "TransactionBatch":
        return self._add("replace_node_id", old_node_id, new_node_id, document_id=document_id, **kwargs)


@dataclass(frozen=True)
class CommitResult:
    """Outcome of one successful :meth:`TransactionCoordinator.execute`
    call. ``document_versions`` maps each touched document_id to its
    ``(old_version, new_version)`` pair -- ``new_version`` is always exactly
    one past ``old_version``, regardless of how many operations touched
    that document. ``results`` is the ordered, per-operation return value,
    in batch order."""

    document_versions: Mapping[UUID, Tuple[Any, Any]]
    results: Tuple[Any, ...]


@dataclass
class IsolatedTransactionState:
    """The private, in-memory overlay one document gets for one batch.
    Every operation runs against ``proxy`` -- never ``document`` itself --
    so operation N+1 sees every mutation operations 1..N already made (same
    overlay objects, mutated in place), while ``document`` stays
    byte-identical to its pre-batch state until
    :meth:`TransactionCoordinator.commit` publishes it."""

    document_id: Optional[UUID]
    document: Any
    proxy: Any
    starting_version: Any


class _OverlayDocument:
    """Minimal duck-typed document proxy the mutation operations run
    against: only the attributes those functions actually read or write."""

    __slots__ = ("document_id", "nodes_by_id", "short_id_index", "root")

    def __init__(self, *, document_id: Any, nodes_by_id: Any, short_id_index: Any, root: Any) -> None:
        self.document_id = document_id
        self.nodes_by_id = nodes_by_id
        self.short_id_index = short_id_index
        self.root = root


def _read_version(document: Any) -> Any:
    current = getattr(document, "document_version", _ABSENT)
    if current is _ABSENT:
        current = getattr(document, "version", None)
    return current


def _bump_version(document: Any, current: Any) -> Any:
    new_version = (current + 1) if isinstance(current, int) else 1
    document.document_version = new_version
    return new_version


def _clone_state(document: Any) -> IsolatedTransactionState:
    """Build the private overlay for one document ({rgi6}): one shared memo
    across ``nodes_by_id``/``short_id_index``/``root`` so the cloned object
    graph keeps the same internal identity relationships (a cloned child's
    cloned ``parent`` is the same object as the cloned parent's entry in
    the cloned ``nodes_by_id``) that the original graph had."""

    memo: Dict[int, Any] = {}
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    short_id_index = getattr(document, "short_id_index", None)
    root = getattr(document, "root", None)
    cloned_nodes = copy.deepcopy(nodes_by_id, memo)
    cloned_short_index = copy.deepcopy(short_id_index, memo) if isinstance(short_id_index, dict) else short_id_index
    cloned_root = copy.deepcopy(root, memo) if root is not None else None
    proxy = _OverlayDocument(
        document_id=getattr(document, "document_id", None),
        nodes_by_id=cloned_nodes,
        short_id_index=cloned_short_index,
        root=cloned_root,
    )
    return IsolatedTransactionState(
        document_id=getattr(document, "document_id", None),
        document=document,
        proxy=proxy,
        starting_version=_read_version(document),
    )


def _check_expected_version(document: Any, expected_version: Any) -> None:
    if expected_version is None:
        return
    current = _read_version(document)
    if current != expected_version:
        raise TransactionError(
            ErrorCode.DOCUMENT_VERSION_CONFLICT,
            f"expected_version {expected_version!r} does not match current "
            f"document_version {current!r}; automatic merging is forbidden, "
            "so this batch is refused rather than merged",
        )


def _full_document_check(proxy: Any) -> None:
    """The single, closing {p016} control check for a completed batch: one
    ``validate_mutation`` call over the whole final overlay tree, never one
    per element. The overlay's own root is checked against a throwaway,
    empty-map stand-in document, so this call is purely diagnostic -- it
    validates every node id in the overlay -- and never reports a false
    conflict against the overlay's own already-registered content."""

    if proxy.root is None:
        return
    stand_in = _OverlayDocument(document_id=proxy.document_id, nodes_by_id={}, short_id_index=None, root=None)
    result = validate_mutation(stand_in, proxy.root, parent=None, position=None)
    if not result.success:
        raise TransactionError(
            ErrorCode.CONCURRENT_TREE_MODIFICATION,
            "post-batch full-document control check failed",
            errors=result.errors,
        )


def _validate_shape(batch: TransactionBatch) -> None:
    if not isinstance(batch, TransactionBatch):
        raise TransactionError(ErrorCode.INVALID_SELECTOR, "batch must be a TransactionBatch instance")
    if batch.document_id is None:
        raise TransactionError(ErrorCode.INVALID_SELECTOR, "batch.document_id is required")
    if not batch.operations:
        raise TransactionError(ErrorCode.INVALID_SELECTOR, "a batch must contain at least one operation")
    for op in batch.operations:
        if op.kind not in _OPERATION_KINDS:
            raise TransactionError(ErrorCode.INVALID_SELECTOR, f"unrecognized operation kind: {op.kind!r}")


def _touched_document_ids(batch: TransactionBatch) -> Set[UUID]:
    touched = {batch.document_id}
    touched.update(batch.expected_versions.keys())
    for op in batch.operations:
        touched.add(op.document_id or batch.document_id)
    return touched


def _execute_operation(op: Operation, proxy: Any, loaded_documents: Mapping[UUID, Any]) -> Any:
    if op.kind == "delete":
        return delete(proxy, *op.args)
    kwargs = dict(op.kwargs)
    kwargs.setdefault("loaded_documents", loaded_documents)
    if op.kind == "insert":
        return insert(proxy, *op.args, **kwargs)
    if op.kind == "replace_range":
        return replace_range(proxy, *op.args, **kwargs)
    if op.kind == "set_body":
        return _update_set_body(proxy, *op.args, **kwargs)
    return _update_replace_node_id(proxy, *op.args, **kwargs)


class TransactionCoordinator:
    """Validates, runs, and commits/rolls back one :class:`TransactionBatch`
    at a time, serialized per document via a shared
    :class:`~tree_engine.core.locking.DocumentLockCoordinator` ({p035})."""

    def __init__(self, lock_coordinator: Optional[DocumentLockCoordinator] = None) -> None:
        self._locks = lock_coordinator or DocumentLockCoordinator()

    @property
    def lock_coordinator(self) -> DocumentLockCoordinator:
        return self._locks

    def execute(self, documents: Mapping[UUID, Document], batch: TransactionBatch) -> CommitResult:
        """Run ``batch`` against ``documents`` (``document_id -> document``,
        covering at least every id the batch touches). Order: static shape
        check -> acquire every touched lock in ascending UUID4 order ->
        check ``expected_version`` per document, once -> clone one overlay
        per document -> run every operation against its target overlay,
        each seeing prior operations' overlay writes -> one closing
        full-document check per touched document -> commit or roll back,
        all under the same held locks, with no partial publication.
        """

        _validate_shape(batch)
        touched_ids = _touched_document_ids(batch)
        missing = touched_ids - set(documents.keys())
        if missing:
            raise TransactionError(
                ErrorCode.NODE_NOT_FOUND,
                f"documents not supplied for touched ids: {sorted(missing, key=str)}",
            )

        with self._locks.acquire_locks(touched_ids) as locked_ids:
            for document_id in locked_ids:
                _check_expected_version(documents[document_id], batch.expected_versions.get(document_id))
            states = {document_id: _clone_state(documents[document_id]) for document_id in locked_ids}
            try:
                results = self._run_operations(batch, states)
                for state in states.values():
                    _full_document_check(state.proxy)
                versions = self.commit(states)
            except Exception:
                self.rollback(states)
                raise
        return CommitResult(document_versions=versions, results=tuple(results))

    def execute_single(self, document: Document, batch: TransactionBatch) -> CommitResult:
        """Convenience wrapper for the common single-document batch."""
        return self.execute({batch.document_id: document}, batch)

    def _run_operations(self, batch: TransactionBatch, states: Mapping[UUID, IsolatedTransactionState]) -> List[Any]:
        overlays = {document_id: state.proxy for document_id, state in states.items()}
        results: List[Any] = []
        for op in batch.operations:
            target_id = op.document_id or batch.document_id
            results.append(_execute_operation(op, states[target_id].proxy, overlays))
        return results

    def commit(self, states: Mapping[UUID, IsolatedTransactionState]) -> Dict[UUID, Tuple[Any, Any]]:
        """Publish every touched document's overlay and advance its public
        ``document_version`` by exactly one ({rgi6}). Two passes, so no
        document is ever partially published: first every state is
        re-checked against its own ``starting_version`` (defensive -- the
        held lock already rules out another transaction changing it, so
        this only fires if something bypassed the coordinator); only once
        every state clears that check does the second pass swap in the
        overlays and bump versions.
        """

        for document_id, state in states.items():
            if _read_version(state.document) != state.starting_version:
                raise TransactionError(
                    ErrorCode.CONCURRENT_TREE_MODIFICATION,
                    f"document {document_id} changed underneath an active transaction",
                )
        versions: Dict[UUID, Tuple[Any, Any]] = {}
        for document_id, state in states.items():
            document = state.document
            document.nodes_by_id = state.proxy.nodes_by_id
            document.short_id_index = state.proxy.short_id_index
            document.root = state.proxy.root
            versions[document_id] = (state.starting_version, _bump_version(document, state.starting_version))
        return versions

    def rollback(self, states: Mapping[UUID, IsolatedTransactionState]) -> None:
        """Discard every touched document's overlay ({rgi6}). Every
        operation this batch ran only ever mutated ``state.proxy`` -- a
        private, unpublished clone -- so rolling back is simply declining
        to publish it: ``state.document`` was never written to on any path
        reaching this method, so it stays byte-identical to its pre-batch
        snapshot, and no UUID4/short_id an operation's overlay-only writes
        introduced is ever reachable from ``state.document``."""
        dict(states).clear()
