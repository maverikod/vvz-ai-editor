"""Contract tests for tree_engine.core.validation.validate_mutation
(concept C-006, {p009}).

Covers the shared preflight pipeline every mutation operation must call
before touching a tree or index map: each of the five rejection
categories -- malformed UUID4, node_id conflict, incompatible
parent/position type, cycle formation, and an unresolvable reference --
in isolation and combined in one call; the short_id reassignment plan for
a fresh node and for a cross-document fragment where only conflicting
short_id values are planned; and the success path's precise
old_short_id -> new_short_id plan.

Deliberately excludes insert, delete, replace_range, reparse, and any
other mutation operation, and never asserts on tree or index-map
mutation: validate_mutation performs none, so there is nothing of that
kind to assert. Uses minimal duck-typed node/document stand-ins, matching
the structural contract documented on validate_mutation itself.
"""

from __future__ import annotations

import itertools
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence

from tree_engine.core.validation import (
    ShortIdReassignment,
    ValidationError,
    ValidationResult,
    validate_mutation,
)
from tree_engine.errors import ErrorCode


# ---------------------------------------------------------------------------
# Minimal duck-typed node/document stand-ins
# ---------------------------------------------------------------------------


class _Node:
    """Minimal node stand-in exposing only what validate_mutation reads."""

    def __init__(
        self,
        node_id: Any,
        *,
        short_id: Any = None,
        children: Optional[Sequence["_Node"]] = None,
        parent: Optional["_Node"] = None,
    ) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self.children: List["_Node"] = list(children) if children else []
        self.parent = parent


class _Document:
    """Minimal document stand-in exposing nodes_by_id and document_id."""

    def __init__(
        self,
        document_id: Optional[uuid.UUID] = None,
        nodes: Optional[Sequence[_Node]] = None,
    ) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[Any, _Node] = {n.node_id: n for n in (nodes or ())}


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _allocator(start: int = 1000) -> Callable[[], int]:
    """A next_short_id stand-in that yields increasing ints and records calls."""

    counter = itertools.count(start)
    calls: List[int] = []

    def _alloc() -> int:
        value = next(counter)
        calls.append(value)
        return value

    _alloc.calls = calls  # type: ignore[attr-defined]
    return _alloc


# ---------------------------------------------------------------------------
# (1) each rejection case in isolation, and a combined multi-failure case
# ---------------------------------------------------------------------------


class TestValidationRejectsEachInvalidCaseWithDistinctErrorCode:
    def test_malformed_uuid4_is_invalid_selector(self) -> None:
        document = _Document()
        incoming = _Node("not-a-uuid4-at-all")

        result = validate_mutation(document, incoming)

        assert result.success is False
        assert result.short_id_plan == []
        assert [e.code for e in result.errors] == [ErrorCode.INVALID_SELECTOR]
        assert isinstance(result.errors[0], ValidationError)
        assert result.errors[0].node_id == "not-a-uuid4-at-all"

    def test_uuid_with_wrong_version_is_invalid_selector(self) -> None:
        # A syntactically valid UUID that is not version 4 must still be
        # rejected as a malformed identifier per {p009}'s UUID4 requirement.
        not_v4 = uuid.uuid1()
        document = _Document()
        incoming = _Node(not_v4)

        result = validate_mutation(document, incoming)

        assert [e.code for e in result.errors] == [ErrorCode.INVALID_SELECTOR]

    def test_existing_node_id_is_node_id_conflict(self) -> None:
        existing = _Node(_new_id())
        document = _Document(nodes=[existing])
        incoming = _Node(existing.node_id)

        result = validate_mutation(document, incoming)

        assert result.success is False
        assert [e.code for e in result.errors] == [ErrorCode.NODE_ID_CONFLICT]
        assert result.errors[0].node_id == existing.node_id

    def test_type_incompatible_with_parent_position_is_invalid_parent_type(self) -> None:
        document = _Document()
        parent = _Node(_new_id())
        incoming = _Node(_new_id())
        seen_calls: List[Any] = []

        def is_type_compatible(p: Any, position: Optional[str], node: Any) -> bool:
            seen_calls.append((p, position, node))
            return False

        result = validate_mutation(
            document,
            incoming,
            parent=parent,
            position="last_child",
            is_type_compatible=is_type_compatible,
        )

        assert result.success is False
        assert [e.code for e in result.errors] == [ErrorCode.INVALID_PARENT_TYPE]
        assert seen_calls == [(parent, "last_child", incoming)]

    def test_reattaching_under_own_descendant_is_cycle_detected(self) -> None:
        # incoming shares a node_id with an ancestor of the chosen parent:
        # attaching it there would make that ancestor its own descendant.
        # Kept out of document.nodes_by_id so this exercises the cycle
        # check alone, not NODE_ID_CONFLICT as well.
        incoming_id = _new_id()
        grandparent = _Node(incoming_id)
        parent = _Node(_new_id(), parent=grandparent)
        document = _Document()
        incoming = _Node(incoming_id)

        result = validate_mutation(document, incoming, parent=parent, position="last_child")

        assert result.success is False
        assert [e.code for e in result.errors] == [ErrorCode.CYCLE_DETECTED]

    def test_unresolvable_local_reference_is_unresolved_reference(self) -> None:
        document = _Document()
        incoming = _Node(_new_id())
        dangling_ref = _new_id()

        result = validate_mutation(document, incoming, references=[dangling_ref])

        assert result.success is False
        assert [e.code for e in result.errors] == [ErrorCode.UNRESOLVED_REFERENCE]
        assert result.errors[0].node_id == dangling_ref

    def test_unresolvable_cross_document_reference_is_unresolved_reference(self) -> None:
        document = _Document()
        incoming = _Node(_new_id())
        other_document_id = _new_id()
        ref = SimpleNamespace(node_id=_new_id(), document_id=other_document_id)

        # other_document_id is entirely absent from loaded_documents.
        result = validate_mutation(document, incoming, references=[ref], loaded_documents={})

        assert result.success is False
        assert [e.code for e in result.errors] == [ErrorCode.UNRESOLVED_REFERENCE]

    def test_resolvable_reference_produces_no_error(self) -> None:
        target = _Node(_new_id())
        document = _Document(nodes=[target])
        incoming = _Node(_new_id())

        result = validate_mutation(document, incoming, references=[target.node_id])

        assert result.success is True
        assert result.errors == []

    def test_all_five_failure_categories_together_each_report_distinct_code(self) -> None:
        # A single call where each failure category is triggered by a
        # different part of the incoming fragment / call, exercised in
        # {p009}'s six-stage check order: (1) a malformed id on the
        # fragment root, (2) a conflicting id on its child, (3)
        # parent/position incompatibility, (4) a cycle via an ancestor
        # reusing the root's raw (malformed) id, (5) an unresolved
        # reference.
        conflicting = _Node(_new_id())
        document = _Document(nodes=[conflicting])

        malformed_raw = "still-not-a-uuid4"
        child = _Node(conflicting.node_id)
        root = _Node(malformed_raw, children=[child])

        ancestor = _Node(malformed_raw)  # raw id matches the root's malformed id
        parent = _Node(_new_id(), parent=ancestor)

        dangling_ref = _new_id()

        result = validate_mutation(
            document,
            root,
            parent=parent,
            position="last_child",
            is_type_compatible=lambda p, pos, n: False,
            references=[dangling_ref],
        )

        assert result.success is False
        assert [e.code for e in result.errors] == [
            ErrorCode.INVALID_SELECTOR,
            ErrorCode.NODE_ID_CONFLICT,
            ErrorCode.INVALID_PARENT_TYPE,
            ErrorCode.CYCLE_DETECTED,
            ErrorCode.UNRESOLVED_REFERENCE,
        ]
        assert result.short_id_plan == []


# ---------------------------------------------------------------------------
# (2) short_id reassignment planning: fresh nodes and cross-document
#     fragments, where only missing/conflicting short_id values are planned
# ---------------------------------------------------------------------------


class TestValidationPlansShortIdAssignmentForNewAndForeignNodes:
    def test_new_node_without_short_id_gets_planned_value_from_allocator(self) -> None:
        document = _Document()
        incoming = _Node(_new_id())  # short_id defaults to None
        alloc = _allocator(start=500)

        result = validate_mutation(document, incoming, next_short_id=alloc)

        assert result.success is True
        assert result.short_id_plan == [
            ShortIdReassignment(node_id=incoming.node_id, old_short_id=None, new_short_id=500)
        ]
        assert alloc.calls == [500]  # type: ignore[attr-defined]

    def test_missing_short_id_without_allocator_still_plans_entry_with_none(self) -> None:
        # Per the module's own contract: no next_short_id supplied means no
        # value is invented locally, but the entry is still recorded.
        document = _Document()
        incoming = _Node(_new_id())

        result = validate_mutation(document, incoming)

        assert result.success is True
        assert result.short_id_plan == [
            ShortIdReassignment(node_id=incoming.node_id, old_short_id=None, new_short_id=None)
        ]

    def test_cross_document_fragment_reassigns_only_conflicting_short_ids(self) -> None:
        # A fragment carried over from another document: one node's
        # short_id is free in the target document and must be left
        # completely untouched, one collides with a short_id already used
        # there, and one arrives with no short_id at all. Only the latter
        # two may appear in the plan.
        free_id, conflicting_id, missing_id = _new_id(), _new_id(), _new_id()
        free_child = _Node(free_id, short_id=10)
        conflicting_child = _Node(conflicting_id, short_id=20)
        missing_child = _Node(missing_id, short_id=None)
        root = _Node(
            _new_id(),
            short_id=30,
            children=[free_child, conflicting_child, missing_child],
        )

        document = _Document()
        alloc = _allocator(start=900)

        result = validate_mutation(
            document,
            root,
            used_short_ids=[20],  # only 20 collides in the target document
            next_short_id=alloc,
        )

        assert result.success is True
        plan_by_node = {entry.node_id: entry for entry in result.short_id_plan}
        assert len(result.short_id_plan) == 2
        assert free_id not in plan_by_node
        assert root.node_id not in plan_by_node
        assert plan_by_node[conflicting_id] == ShortIdReassignment(
            node_id=conflicting_id, old_short_id=20, new_short_id=900
        )
        assert plan_by_node[missing_id] == ShortIdReassignment(
            node_id=missing_id, old_short_id=None, new_short_id=901
        )
        assert alloc.calls == [900, 901]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# (3) success path: exact old_short_id -> new_short_id remap plan
# ---------------------------------------------------------------------------


class TestValidationSuccessReturnsCorrectRemapPlan:
    def test_valid_fragment_returns_success_with_precise_remap_plan(self) -> None:
        document = _Document()
        child = _Node(_new_id())  # no short_id -> needs reassignment
        root = _Node(_new_id(), short_id=5, children=[child])
        alloc = _allocator(start=1)

        result = validate_mutation(
            document,
            root,
            used_short_ids=[5],  # root's own short_id collides too
            next_short_id=alloc,
        )

        assert isinstance(result, ValidationResult)
        assert result.success is True
        assert result.errors == []
        assert result.short_id_plan == [
            ShortIdReassignment(node_id=root.node_id, old_short_id=5, new_short_id=1),
            ShortIdReassignment(node_id=child.node_id, old_short_id=None, new_short_id=2),
        ]

    def test_valid_fragment_with_no_short_id_conflicts_plans_nothing(self) -> None:
        document = _Document()
        incoming = _Node(_new_id(), short_id=42)

        result = validate_mutation(document, incoming, used_short_ids=[])

        assert result.success is True
        assert result.errors == []
        assert result.short_id_plan == []

    def test_full_call_with_parent_position_and_resolved_reference_succeeds(self) -> None:
        # Exercises the success path with every optional dimension engaged
        # at once: a real parent/position, a passing type-compatibility
        # check, and a reference that resolves locally.
        target = _Node(_new_id())
        parent = _Node(_new_id())
        document = _Document(nodes=[target, parent])
        incoming = _Node(_new_id())
        alloc = _allocator(start=77)

        result = validate_mutation(
            document,
            incoming,
            parent=parent,
            position="child_index",
            index=0,
            is_type_compatible=lambda p, pos, n: True,
            references=[target.node_id],
            next_short_id=alloc,
        )

        assert result.success is True
        assert result.errors == []
        assert result.short_id_plan == [
            ShortIdReassignment(node_id=incoming.node_id, old_short_id=None, new_short_id=77)
        ]
