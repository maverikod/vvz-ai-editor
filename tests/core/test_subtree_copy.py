"""Contract tests for ``tree_engine.core.subtree_copy.copy_subtree`` (C-019, {p078}).

Covers both identity modes documented on the module: ``preserve_ids=False``
(fresh UUID4 per copied node) and ``preserve_ids=True`` (every UUID4 kept,
under a brand-new ``document_id``); reference rewriting for internal vs.
external targets in both modes; that an incoming reference authored by a
node outside the copied subtree is never reflected in the copy; and that
the returned :class:`CopiedDocument` is fully independent of its source,
both structurally and under later mutation of either side.

A minimal mutable duck-typed ``_Node``/``_Document`` pair stands in for the
real tree types, matching the structural contract documented on
``copy_subtree`` itself (``node_id``, ``children``, ``short_id``,
``references``, ``parent_id`` on a node; ``nodes_by_id``, ``root``,
``document_id``, ``document_version``, ``parent_index`` on a document).

Fixture tree, used by every test in this file::

    root
      +-- branch            references -> outside (external, {p073}/{p074})
      |     +-- leaf1
      |     +-- leaf2       references -> leaf1   (internal)
      +-- outside            references -> leaf1   (incoming, into the branch)

``copy_subtree`` is exercised with ``node_id=branch.node_id`` (a partial
subtree) in most tests, plus one whole-tree case (``node_id=None``) and one
narrower single-leaf case, to also cover the {p077} traversal-boundary
requirement.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional
from uuid import UUID

from tree_engine.core.identity import NodeAddress
from tree_engine.core.subtree_copy import CopiedDocument, copy_subtree


def _uuid() -> UUID:
    return uuid.uuid4()


class _Node:
    """Minimal mutable duck-typed node stand-in.

    Exposes exactly the attributes ``copy_subtree`` reads/clones:
    ``node_id``, ``children``, ``short_id``, ``references``, ``parent_id``.
    """

    def __init__(
        self,
        node_id: Optional[UUID] = None,
        *,
        short_id: Optional[int] = None,
        children: Optional[List["_Node"]] = None,
        references: Optional[List[NodeAddress]] = None,
        parent_id: Optional[UUID] = None,
    ) -> None:
        self.node_id = node_id if node_id is not None else _uuid()
        self.short_id = short_id
        self.children: List["_Node"] = list(children) if children else []
        self.references: List[NodeAddress] = list(references) if references else []
        self.parent_id = parent_id


class _Document:
    """Minimal duck-typed document stand-in exposing ``nodes_by_id``,
    ``root``, ``document_id``, ``document_version``, and ``parent_index``."""

    def __init__(
        self, root: _Node, *, document_id: Optional[UUID] = None, document_version: int = 1
    ) -> None:
        self.document_id = document_id if document_id is not None else _uuid()
        self.document_version = document_version
        self.root = root
        self.nodes_by_id: Dict[UUID, _Node] = {}
        self.parent_index: Dict[UUID, Optional[UUID]] = {}
        self._index(root, None)

    def _index(self, node: _Node, parent_id: Optional[UUID]) -> None:
        node.parent_id = parent_id
        self.nodes_by_id[node.node_id] = node
        self.parent_index[node.node_id] = parent_id
        for child in node.children:
            self._index(child, node.node_id)


def _build_tree():
    leaf1 = _Node()
    outside = _Node()
    leaf2 = _Node(references=[NodeAddress(node_id=leaf1.node_id)])
    branch = _Node(children=[leaf1, leaf2], references=[NodeAddress(node_id=outside.node_id)])
    outside.references = [NodeAddress(node_id=leaf1.node_id)]  # incoming, into the branch
    root = _Node(children=[branch, outside])
    return root, {
        "root": root,
        "branch": branch,
        "leaf1": leaf1,
        "leaf2": leaf2,
        "outside": outside,
    }


class TestCopySubtreePreserveIdsFalse:
    def test_copy_subtree_preserve_ids_false_fresh_uuids(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)
        branch_ids = {nodes["branch"].node_id, nodes["leaf1"].node_id, nodes["leaf2"].node_id}

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=False)

        assert isinstance(copied, CopiedDocument)
        new_ids = set(copied.nodes_by_id.keys())
        assert new_ids.isdisjoint(branch_ids)
        assert set(copied.old_uuid_to_new_uuid.keys()) == branch_ids
        assert set(copied.old_uuid_to_new_uuid.values()) == new_ids
        assert copied.root.node_id == copied.old_uuid_to_new_uuid[nodes["branch"].node_id]

        new_leaf2 = copied.nodes_by_id[copied.old_uuid_to_new_uuid[nodes["leaf2"].node_id]]
        assert len(new_leaf2.references) == 1
        rewritten = new_leaf2.references[0]
        assert rewritten.document_id is None
        assert rewritten.node_id == copied.old_uuid_to_new_uuid[nodes["leaf1"].node_id]
        assert rewritten.node_id != nodes["leaf1"].node_id

    def test_copy_subtree_preserve_ids_false_external_refs(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=False)

        assert len(copied.root.references) == 1
        ext_ref = copied.root.references[0]
        assert ext_ref.document_id == doc.document_id
        assert ext_ref.node_id == nodes["outside"].node_id  # unchanged target id

    def test_copy_subtree_preserve_ids_false_no_incoming_refs(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)
        outside_refs_before = list(nodes["outside"].references)

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=False)

        # "outside" is not part of the copied subtree at all, so nothing of
        # its authored reference into the branch is present in the copy.
        assert nodes["outside"].node_id not in copied.nodes_by_id
        assert len(copied.nodes_by_id) == 3  # branch, leaf1, leaf2 only

        # the source is read-only: the incoming reference is untouched.
        assert nodes["outside"].references == outside_refs_before
        assert nodes["outside"].references[0].node_id == nodes["leaf1"].node_id


class TestCopySubtreePreserveIdsTrue:
    def test_copy_subtree_preserve_ids_true_uuid_preserved(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)
        branch_id = nodes["branch"].node_id

        copied = copy_subtree(doc, node_id=branch_id, preserve_ids=True)

        assert copied.root.node_id == branch_id
        assert set(copied.nodes_by_id.keys()) == {
            branch_id,
            nodes["leaf1"].node_id,
            nodes["leaf2"].node_id,
        }
        assert copied.old_uuid_to_new_uuid == {
            branch_id: branch_id,
            nodes["leaf1"].node_id: nodes["leaf1"].node_id,
            nodes["leaf2"].node_id: nodes["leaf2"].node_id,
        }
        assert copied.document_id != doc.document_id  # new document identity
        assert copied.document_version == 1
        assert copied.origin_document_id == doc.document_id
        assert copied.origin_parent_id == doc.parent_index[branch_id]

        short_ids = {copied.short_id_map.get_short_id(nid) for nid in copied.nodes_by_id}
        assert short_ids == {1, 2, 3}  # freshly assigned in the copy's own map

    def test_copy_subtree_preserve_ids_true_rewritten_internal_refs(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=True)

        new_leaf2 = copied.nodes_by_id[nodes["leaf2"].node_id]
        assert len(new_leaf2.references) == 1
        ref = new_leaf2.references[0]
        assert ref.document_id is None  # now local to the copy's own new document
        assert ref.node_id == nodes["leaf1"].node_id  # same UUID4, preserved

    def test_copy_subtree_preserve_ids_true_external_refs(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=True)

        ext_ref = copied.root.references[0]
        assert ext_ref.document_id == doc.document_id
        assert ext_ref.node_id == nodes["outside"].node_id


class TestCopySubtreeIsolation:
    def test_copy_subtree_isolation_independent_objects(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root, document_version=7)

        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=False)

        assert copied.nodes_by_id is not doc.nodes_by_id
        assert copied.root is not nodes["branch"]
        original_object_ids = {id(nodes["branch"]), id(nodes["leaf1"]), id(nodes["leaf2"])}
        assert all(id(n) not in original_object_ids for n in copied.nodes_by_id.values())
        assert copied.document_version == 1
        assert copied.document_version != doc.document_version
        assert copied.short_id_map is not None

    def test_copy_subtree_isolation_mutation_independence(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)
        copied = copy_subtree(doc, node_id=nodes["branch"].node_id, preserve_ids=False)

        source_child_count_before = len(nodes["branch"].children)
        copy_child_count_before = len(copied.root.children)

        extra_in_copy = _Node()
        copied.root.children.append(extra_in_copy)
        copied.nodes_by_id[extra_in_copy.node_id] = extra_in_copy
        assert len(nodes["branch"].children) == source_child_count_before  # source untouched

        extra_in_source = _Node()
        nodes["branch"].children.append(extra_in_source)
        doc.nodes_by_id[extra_in_source.node_id] = extra_in_source
        assert len(copied.root.children) == copy_child_count_before + 1  # copy untouched
        assert extra_in_source.node_id not in copied.nodes_by_id
        assert extra_in_copy.node_id not in doc.nodes_by_id

        new_leaf1 = copied.nodes_by_id[copied.old_uuid_to_new_uuid[nodes["leaf1"].node_id]]
        new_leaf1.short_id = 999
        assert nodes["leaf1"].short_id != 999

    def test_copy_subtree_partial_subtree(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)

        copied = copy_subtree(doc, node_id=nodes["leaf2"].node_id, preserve_ids=False)

        assert len(copied.nodes_by_id) == 1  # leaf2 alone; its own children (none) only
        assert copied.old_uuid_to_new_uuid == {nodes["leaf2"].node_id: copied.root.node_id}
        # leaf2's former-internal reference to leaf1 is now outside this
        # narrower subtree, so it is preserved as an explicit external ref.
        assert copied.root.references[0].document_id == doc.document_id
        assert copied.root.references[0].node_id == nodes["leaf1"].node_id

    def test_copy_subtree_full_tree(self) -> None:
        root, nodes = _build_tree()
        doc = _Document(root)

        copied = copy_subtree(doc, node_id=None, preserve_ids=False)

        assert len(doc.nodes_by_id) == 5  # root, branch, leaf1, leaf2, outside
        assert len(copied.nodes_by_id) == 5
        assert copied.root.node_id != root.node_id
        assert set(copied.old_uuid_to_new_uuid.keys()) == set(doc.nodes_by_id.keys())
