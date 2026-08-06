"""Contract tests for the cross-document reference and index-map behavior
of tree_engine.core.move + tree_engine.core.move_references (concept
C-020, {p039}, {p079}, {p080}, {p081}).

Covers: the three NodeAddress rewrite directions a cross-document move
performs -- a subtree-internal reference, an outgoing reference to a node
left behind in the source, and an incoming reference from a node left
behind in the source, all rewritten to correct explicit addresses -- plus
a third *loaded* document's incoming reference retargeted the same way and
a document never passed via ``loaded_documents`` left completely alone;
both documents' index maps (``nodes_by_id``, ``short_id_index``,
parent/child links) refreshed synchronously and consistently for the
affected nodes, together with the fact that -- per move_references.py's
own contract -- ``node.references`` already IS the canonical
object-reference representation here (there is no separate cache to fall
out of sync); and a mid-move failure (discovered after the structural
relocation has already happened, during reference reconciliation) rolling
back to leave both documents exactly as they were, with no partial
reference conversion or partial index-map update surviving.

Deliberately excludes the intra-tree move case and the basic UUID4
identity-preservation / lock-ordering assertions -- those belong to the
sibling test_move.py file, per this step's own scope.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from tree_engine.core.identity import NodeAddress
from tree_engine.core.move import move
from tree_engine.core.move_references import ReferenceDelta, reconcile_references


# ---------------------------------------------------------------------------
# Minimal duck-typed node/document stand-ins, mirrored from
# test_operations.py / test_updates.py, with ``references`` added.
# ---------------------------------------------------------------------------


class _Node:
    def __init__(
        self,
        node_id: Any,
        *,
        short_id: Any = None,
        children: Optional[Sequence["_Node"]] = None,
        parent: Optional["_Node"] = None,
        buffer_range: Optional[Tuple[int, int]] = None,
        references: Sequence[Any] = (),
    ) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self.children: List["_Node"] = list(children) if children else []
        self.parent = parent
        self.buffer_range = buffer_range
        self.references: Tuple[Any, ...] = tuple(references)


class _Document:
    def __init__(self, document_id: Optional[uuid.UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[Any, _Node] = {}
        self.short_id_index: Dict[Any, Any] = {}


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _register(document: _Document, *roots: _Node) -> None:
    stack = list(roots)
    while stack:
        node = stack.pop()
        document.nodes_by_id[node.node_id] = node
        if node.short_id is not None:
            document.short_id_index[node.short_id] = node.node_id
        stack.extend(node.children)


def _snapshot(document: _Document) -> Dict[str, Any]:
    """Snapshot of every node, both index maps, and every reference tuple:
    byte-for-byte proof a rollback left nothing partially applied."""
    nodes = {
        node_id: (
            node.short_id,
            node.parent.node_id if node.parent is not None else None,
            tuple(c.node_id for c in node.children),
            node.buffer_range,
            node.references,
        )
        for node_id, node in document.nodes_by_id.items()
    }
    return {
        "keys": frozenset(document.nodes_by_id.keys()),
        "nodes": nodes,
        "short_id_index": dict(document.short_id_index),
    }


def _build_cross_document_fixture():
    """Source + target documents, a third *loaded* document, and a fourth
    document deliberately never passed via ``loaded_documents``. The move
    itself is not performed here -- each test runs it and asserts a
    different facet of the outcome."""

    src_doc = _Document()
    tgt_doc = _Document()
    extra_doc = _Document()  # third LOADED document
    outside_doc = _Document()  # NOT passed via loaded_documents

    src_root = _Node(_id(), buffer_range=(0, 100))
    moved_parent = _Node(_id(), parent=src_root, short_id=10, buffer_range=(0, 40))
    moved_child = _Node(_id(), parent=moved_parent, short_id=11, buffer_range=(0, 20))
    moved_parent.children = [moved_child]
    remaining = _Node(_id(), parent=src_root, short_id=12, buffer_range=(40, 100))
    src_root.children = [moved_parent, remaining]

    # internal: both endpoints move together.
    moved_parent.references = (NodeAddress(node_id=moved_child.node_id),)
    # outgoing: moved -> left behind in the source.
    moved_child.references = (NodeAddress(node_id=remaining.node_id),)
    # incoming: a node staying in the source, pointing at a moved node.
    remaining.references = (NodeAddress(node_id=moved_parent.node_id),)

    _register(src_doc, src_root)

    tgt_root = _Node(_id(), buffer_range=(0, 10))
    _register(tgt_doc, tgt_root)

    # third loaded document: an incoming reference into the moved subtree.
    extra_node = _Node(
        _id(), references=(NodeAddress(document_id=src_doc.document_id, node_id=moved_parent.node_id),),
    )
    _register(extra_doc, extra_node)

    # never loaded: an equally-shaped incoming reference this module has no
    # way to reach, so it must be left exactly as it was.
    outside_node = _Node(
        _id(), references=(NodeAddress(document_id=src_doc.document_id, node_id=moved_parent.node_id),),
    )
    _register(outside_doc, outside_node)

    return dict(
        src_doc=src_doc, tgt_doc=tgt_doc, extra_doc=extra_doc, outside_doc=outside_doc,
        src_root=src_root, moved_parent=moved_parent, moved_child=moved_child,
        remaining=remaining, tgt_root=tgt_root, extra_node=extra_node, outside_node=outside_node,
        loaded_documents={extra_doc.document_id: extra_doc},
    )


def _run_move(fx: Dict[str, Any]):
    return move(
        fx["src_doc"], fx["moved_parent"].node_id, position="last_child",
        target_document=fx["tgt_doc"], parent=fx["tgt_root"].node_id,
        loaded_documents=fx["loaded_documents"],
        reconcile_references=reconcile_references,
    )


# ---------------------------------------------------------------------------
# The three NodeAddress rewrite directions, plus third-document retargeting
# and the never-loaded document's isolation.
# ---------------------------------------------------------------------------


def test_cross_document_reference_conversion_internal_incoming_outgoing() -> None:
    fx = _build_cross_document_fixture()
    _run_move(fx)

    moved_parent, moved_child = fx["moved_parent"], fx["moved_child"]
    remaining, extra_node, outside_node = fx["remaining"], fx["extra_node"], fx["outside_node"]
    src_doc, tgt_doc = fx["src_doc"], fx["tgt_doc"]

    # internal: moved_parent -> moved_child now carries the target's document_id.
    assert moved_parent.references == (
        NodeAddress(document_id=tgt_doc.document_id, node_id=moved_child.node_id),
    )

    # outgoing: moved_child -> remaining (left behind) becomes external, naming the source.
    assert moved_child.references == (
        NodeAddress(document_id=src_doc.document_id, node_id=remaining.node_id),
    )

    # incoming, from the source's own remaining node.
    assert remaining.references == (
        NodeAddress(document_id=tgt_doc.document_id, node_id=moved_parent.node_id),
    )

    # incoming, from a third *loaded* document -- also retargeted.
    assert extra_node.references == (
        NodeAddress(document_id=tgt_doc.document_id, node_id=moved_parent.node_id),
    )

    # a document never supplied via loaded_documents is left completely untouched.
    assert outside_node.references == (
        NodeAddress(document_id=src_doc.document_id, node_id=moved_parent.node_id),
    )


# ---------------------------------------------------------------------------
# Both documents' index maps refreshed synchronously; node.references is
# already the canonical object-reference representation (no separate cache
# to fall out of sync, per move_references.py's own contract).
# ---------------------------------------------------------------------------


def test_cross_document_index_map_and_cache_sync() -> None:
    fx = _build_cross_document_fixture()
    result = _run_move(fx)

    src_doc, tgt_doc = fx["src_doc"], fx["tgt_doc"]
    moved_parent, moved_child, remaining = fx["moved_parent"], fx["moved_child"], fx["remaining"]

    # nodes_by_id: moved subtree fully migrated, remaining stays in source.
    assert moved_parent.node_id not in src_doc.nodes_by_id
    assert moved_child.node_id not in src_doc.nodes_by_id
    assert tgt_doc.nodes_by_id[moved_parent.node_id] is moved_parent
    assert tgt_doc.nodes_by_id[moved_child.node_id] is moved_child
    assert remaining.node_id in src_doc.nodes_by_id

    # short_id index follows the same migration, synchronously.
    assert 10 not in src_doc.short_id_index
    assert 11 not in src_doc.short_id_index
    assert tgt_doc.short_id_index[10] == moved_parent.node_id
    assert tgt_doc.short_id_index[11] == moved_child.node_id

    # parent/child links updated in both documents.
    assert moved_parent.parent is fx["tgt_root"]
    assert [c.node_id for c in fx["tgt_root"].children] == [moved_parent.node_id]
    assert [c.node_id for c in fx["src_root"].children] == [remaining.node_id]

    # "object-reference cache" == canonical NodeAddress: per
    # move_references.py's own contract there is no separate cache --
    # node.references already IS the canonical representation, so the
    # rewritten value observed here is both at once, by construction.
    assert all(isinstance(addr, NodeAddress) for addr in moved_parent.references)
    assert all(isinstance(addr, NodeAddress) for addr in moved_child.references)
    assert all(isinstance(addr, NodeAddress) for addr in remaining.references)

    assert isinstance(result.reference_delta, ReferenceDelta)
    changed_nodes = {change.node for change in result.reference_delta.changes}
    assert changed_nodes == {moved_parent, moved_child, remaining, fx["extra_node"]}


# ---------------------------------------------------------------------------
# A mid-move failure -- discovered only after the structural relocation has
# already happened, while reconciling references -- rolls back completely:
# no partial reference conversion, no partial index-map update survives.
# ---------------------------------------------------------------------------


def test_cross_document_move_full_rollback_on_failure() -> None:
    fx = _build_cross_document_fixture()
    src_doc, tgt_doc = fx["src_doc"], fx["tgt_doc"]
    moved_parent, remaining, src_root = fx["moved_parent"], fx["remaining"], fx["src_root"]

    before_src = _snapshot(src_doc)
    before_tgt = _snapshot(tgt_doc)

    def _failing_reconcile(**kwargs: Any) -> Any:
        # Reconciliation is attempted only after the structural relocation
        # already happened; failing here -- before any reference is
        # touched -- is exactly the "discovered partway through" case.
        raise RuntimeError("simulated reconciliation failure")

    with pytest.raises(RuntimeError):
        move(
            src_doc, moved_parent.node_id, position="last_child",
            target_document=tgt_doc, parent=fx["tgt_root"].node_id,
            loaded_documents=fx["loaded_documents"],
            reconcile_references=_failing_reconcile,
        )

    assert _snapshot(src_doc) == before_src
    assert _snapshot(tgt_doc) == before_tgt
    assert moved_parent.parent is src_root  # structural relocation fully undone
    assert moved_parent.node_id in src_doc.nodes_by_id
    assert moved_parent.node_id not in tgt_doc.nodes_by_id
    assert moved_parent.references == (NodeAddress(node_id=fx["moved_child"].node_id),)  # unrewritten
    assert remaining.references == (NodeAddress(node_id=moved_parent.node_id),)  # unrewritten
