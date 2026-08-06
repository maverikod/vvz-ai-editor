"""Contract tests for ``tree_engine.core.subtree_apply.apply_subtree`` (C-019, {p076}/{p078}).

Covers the explicit replace/apply return path that is the counterpart of
``copy_subtree`` (see ``test_subtree_copy.py`` for the copy half, not
retested here): ``expected_version`` enforcement; that the shared C-006
``validate_mutation`` preflight actually runs and gates the write; the
``NODE_ID_CONFLICT`` accept/reject split between a legitimate
identity-preserving replace and a genuine foreign collision, in both
``preserve_ids`` modes; the returned short_id remap, including that a free
candidate short_id survives untouched while a conflicting one is
reassigned; and that a rejected apply leaves the target completely
unchanged.

Fixtures are declared directly in this file: a minimal mutable duck-typed
``_Node``/``_Document`` pair matching the structural contract documented on
``apply_subtree`` and ``validate_mutation`` (``node_id``, ``children``,
``short_id``, ``parent_id`` on a node; ``nodes_by_id``, ``document_id``,
``document_version``, ``parent_index``, ``short_id_map``, ``short_id_index``
on a document). Real ``copy_subtree``/``ShortIdMap`` objects are used
throughout -- only the one pathological UUID4-collision scenario
(``test_apply_subtree_fresh_uuid_mode_conflict_detected``) forces an id by
hand, since a real UUID4 clash cannot be produced deterministically.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.short_id import ShortIdMap
from tree_engine.core.subtree_apply import (
    ApplySubtreeResult,
    NodeIDConflictError,
    SubtreeApplyError,
    apply_subtree,
)
from tree_engine.core.subtree_copy import copy_subtree
from tree_engine.errors import ErrorCode


def _uuid() -> UUID:
    return uuid.uuid4()


class _Node:
    """Minimal mutable duck-typed node stand-in: ``node_id``, ``children``,
    ``short_id``, ``parent_id`` -- exactly what ``apply_subtree`` and the
    shared ``validate_mutation`` preflight read or write."""

    def __init__(
        self,
        node_id: Optional[UUID] = None,
        *,
        short_id: Optional[int] = None,
        children: Optional[List["_Node"]] = None,
        parent_id: Optional[UUID] = None,
    ) -> None:
        self.node_id = node_id if node_id is not None else _uuid()
        self.short_id = short_id
        self.children: List["_Node"] = list(children) if children else []
        self.parent_id = parent_id


class _Document:
    """Minimal mutable duck-typed document stand-in exposing every attribute
    ``apply_subtree`` consults: ``nodes_by_id``, ``document_id``,
    ``document_version``, ``parent_index``, ``short_id_map``,
    ``short_id_index``, ``root``."""

    def __init__(
        self, root: _Node, *, document_id: Optional[UUID] = None, document_version: int = 1
    ) -> None:
        self.document_id = document_id if document_id is not None else _uuid()
        self.document_version = document_version
        self.root = root
        self.nodes_by_id: Dict[UUID, _Node] = {}
        self.parent_index: Dict[UUID, Optional[UUID]] = {}
        self.short_id_index: Dict[int, UUID] = {}
        self.short_id_map = ShortIdMap()
        self._index(root, None)

    def _index(self, node: _Node, parent_id: Optional[UUID]) -> None:
        node.parent_id = parent_id
        self.nodes_by_id[node.node_id] = node
        self.parent_index[node.node_id] = parent_id
        if node.short_id is not None:
            self.short_id_index[node.short_id] = node.node_id
        for child in node.children:
            self._index(child, node.node_id)

    def snapshot(self) -> Tuple[Dict[UUID, Tuple[Optional[int], Optional[UUID], Tuple[UUID, ...]]], int]:
        """Structural snapshot for a "left completely untouched" assertion."""

        structure = {
            nid: (n.short_id, n.parent_id, tuple(c.node_id for c in n.children))
            for nid, n in self.nodes_by_id.items()
        }
        return structure, self.document_version


def _small_doc_with_branch() -> Tuple[_Document, _Node, _Node, _Node]:
    """``root`` -> [``branch`` -> [``leaf``]], every node carrying a real
    short_id allocated through the target's own ``short_id_map``."""

    leaf = _Node()
    branch = _Node(children=[leaf])
    root = _Node(children=[branch])
    doc = _Document(root)
    for node in (root, branch, leaf):
        node.short_id = doc.short_id_map.allocate(node.node_id)
        doc.short_id_index[node.short_id] = node.node_id
    return doc, root, branch, leaf


def test_apply_subtree_checks_expected_version() -> None:
    doc, root, branch, leaf = _small_doc_with_branch()
    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=True)
    before = doc.snapshot()

    with pytest.raises(SubtreeApplyError) as excinfo:
        apply_subtree(doc, copy, expected_version=doc.document_version + 1)
    assert excinfo.value.code == ErrorCode.DOCUMENT_VERSION_CONFLICT
    assert doc.snapshot() == before  # rejected before anything was applied

    result = apply_subtree(doc, copy, expected_version=doc.document_version)
    assert isinstance(result, ApplySubtreeResult)
    assert doc.nodes_by_id[branch.node_id] is copy.root


def test_apply_subtree_runs_shared_insertion_validation() -> None:
    doc, root, branch, leaf = _small_doc_with_branch()
    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=True)
    before = doc.snapshot()
    calls: List[Tuple] = []

    def is_type_compatible(parent, position, incoming) -> bool:
        calls.append((parent, position, incoming))
        return False  # force the shared C-006 preflight to reject

    with pytest.raises(SubtreeApplyError) as excinfo:
        apply_subtree(doc, copy, is_type_compatible=is_type_compatible)

    assert excinfo.value.code == ErrorCode.INVALID_PARENT_TYPE
    assert calls == [(root, "child_index", copy.root)]  # preflight was actually invoked
    assert doc.snapshot() == before  # rejected before any write


def test_apply_subtree_preserve_ids_true_conflict_allowed_for_same_logical_node() -> None:
    doc, root, branch, leaf = _small_doc_with_branch()
    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=True)
    assert copy.root.node_id == branch.node_id  # identity preserved
    assert copy.origin_document_id == doc.document_id
    assert copy.origin_parent_id == root.node_id

    result = apply_subtree(doc, copy)

    assert result.node_id == branch.node_id
    assert doc.nodes_by_id[branch.node_id] is copy.root  # accepted, not a conflict
    assert doc.nodes_by_id[branch.node_id] is not branch  # a new object replaced the old one


def test_apply_subtree_preserve_ids_true_conflict_rejected_for_other_node() -> None:
    doc, root, branch, leaf = _small_doc_with_branch()
    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=True)

    # A wholly separate document that happens to already contain an
    # unrelated node reusing `branch`'s UUID4 -- not the logical node the
    # copy was taken from (different document_id -> no origin match).
    unrelated = _Node(node_id=branch.node_id)
    foreign_root = _Node(children=[unrelated])
    foreign_doc = _Document(foreign_root)
    for node in (foreign_root, unrelated):
        node.short_id = foreign_doc.short_id_map.allocate(node.node_id)
    before = foreign_doc.snapshot()

    with pytest.raises(NodeIDConflictError) as excinfo:
        apply_subtree(foreign_doc, copy)

    assert excinfo.value.code == ErrorCode.NODE_ID_CONFLICT
    assert foreign_doc.snapshot() == before  # left byte-identical


def test_apply_subtree_fresh_uuid_mode_uses_origin_map_for_identity() -> None:
    doc, root, branch, leaf = _small_doc_with_branch()
    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=False)
    assert copy.root.node_id != branch.node_id  # fresh id, not preserved
    assert copy.old_uuid_to_new_uuid[branch.node_id] == copy.root.node_id

    result = apply_subtree(doc, copy)

    assert result.node_id == copy.root.node_id
    assert branch.node_id not in doc.nodes_by_id  # old origin subtree removed
    assert leaf.node_id not in doc.nodes_by_id
    assert doc.nodes_by_id[copy.root.node_id] is copy.root
    assert result.removed == NodeAddress(document_id=doc.document_id, node_id=branch.node_id)
    assert result.inserted == NodeAddress(document_id=doc.document_id, node_id=copy.root.node_id)


def test_apply_subtree_fresh_uuid_mode_conflict_detected() -> None:
    branch = _Node()
    victim = _Node()
    root = _Node(children=[branch, victim])
    doc = _Document(root)
    for node in (root, branch, victim):
        node.short_id = doc.short_id_map.allocate(node.node_id)

    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=False)
    assert copy.old_uuid_to_new_uuid == {branch.node_id: copy.root.node_id}

    # A real UUID4 clash cannot be produced deterministically: force the
    # pathological case by hand, matching {p073}'s "essentially never
    # collides" carve-out -- the fresh copy id happens to equal an
    # unrelated existing node's id in the target document.
    copy.root.node_id = victim.node_id
    copy.old_uuid_to_new_uuid[branch.node_id] = victim.node_id
    before = doc.snapshot()

    with pytest.raises(NodeIDConflictError) as excinfo:
        apply_subtree(doc, copy)

    assert excinfo.value.code == ErrorCode.NODE_ID_CONFLICT
    assert doc.snapshot() == before


def test_apply_subtree_returns_short_id_remap() -> None:
    child = _Node()
    branch = _Node(children=[child])
    sibling = _Node()  # pre-occupies short_id 2 in the target
    root = _Node(children=[branch, sibling])
    doc = _Document(root)
    doc.short_id_map.merge_insert({sibling.node_id: 2})
    sibling.short_id = 2
    doc.short_id_index[2] = sibling.node_id

    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=False)
    new_branch_id = copy.old_uuid_to_new_uuid[branch.node_id]
    new_child_id = copy.old_uuid_to_new_uuid[child.node_id]
    # The copy's own fresh ShortIdMap assigns candidates 1 (root) and 2 (child).
    assert copy.short_id_map.get_short_id(new_branch_id) == 1
    assert copy.short_id_map.get_short_id(new_child_id) == 2

    result = apply_subtree(doc, copy)

    # candidate 1 was free in the target: kept untouched, no remap entry.
    assert doc.nodes_by_id[new_branch_id].short_id == 1
    # candidate 2 collided with `sibling`'s short_id: reassigned, and
    # returned in the remap.
    assert doc.nodes_by_id[new_child_id].short_id == 3
    assert result.short_id_remap == {2: 3}
    assert sibling.short_id == 2  # the unrelated node's own short_id is untouched


def test_apply_subtree_rejects_without_publishing_on_conflict() -> None:
    branch = _Node()
    victim = _Node()
    root = _Node(children=[branch, victim])
    doc = _Document(root)
    for node in (root, branch, victim):
        node.short_id = doc.short_id_map.allocate(node.node_id)

    copy = copy_subtree(doc, node_id=branch.node_id, preserve_ids=False)
    copy.root.node_id = victim.node_id
    copy.old_uuid_to_new_uuid[branch.node_id] = victim.node_id
    before_structure, before_version = doc.snapshot()

    with pytest.raises(NodeIDConflictError):
        apply_subtree(doc, copy)

    after_structure, after_version = doc.snapshot()
    assert after_structure == before_structure  # not one node was touched
    assert after_version == before_version  # document_version unchanged
    assert doc.nodes_by_id[branch.node_id] is branch  # original object, still live
    assert doc.nodes_by_id[victim.node_id] is victim  # still the pre-existing object, not spliced over
