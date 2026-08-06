"""Unit tests for tree_engine.core.identity.

Scoped strictly to node_id behavior ({p013}) and replace_node_id /
AddressRemap ({p109}). Deliberately excludes short_id lifecycle,
normalize_node_address, and NodeAddress serialization, which are owned by
sibling test modules. Uses a minimal in-memory document/tree builder
defined locally below; the node/document stand-ins never expose short_id
or reference-index attributes.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest

from tree_engine.core.identity import (
    AddressRemap,
    NodeAddress,
    NodeIdentityError,
    assign_node_id,
    replace_node_id,
)


class _Node:
    """Minimal mutable node stand-in exposing only what identity.py reads."""

    def __init__(self, node_id: uuid.UUID, content: Any = None) -> None:
        self.node_id = node_id
        self.content = content
        self.generation = 0


class _Document:
    """Minimal in-memory document exposing nodes_by_id and document_id."""

    def __init__(self, document_id: Optional[uuid.UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[uuid.UUID, _Node] = {}

    def add_node(self, content: Any = None) -> _Node:
        node_id = assign_node_id(None)
        node = _Node(node_id=node_id, content=content)
        self.nodes_by_id[node_id] = node
        return node


@pytest.fixture
def document() -> _Document:
    return _Document()


@pytest.fixture
def small_tree(document: _Document) -> Dict[str, Any]:
    """A tiny 3-node tree: one root and two children, addressed by label."""

    root = document.add_node(content={"label": "root", "value": 1})
    child_a = document.add_node(content={"label": "child_a", "value": 2})
    child_b = document.add_node(content={"label": "child_b", "value": 3})
    return {
        "document": document,
        "root": root,
        "child_a": child_a,
        "child_b": child_b,
    }


# ---------------------------------------------------------------------------
# (1) node_id stability across an unrelated edit
# ---------------------------------------------------------------------------


def test_node_id_stable_on_unrelated_edit(small_tree: Dict[str, Any]) -> None:
    root = small_tree["root"]
    child_a = small_tree["child_a"]
    child_b = small_tree["child_b"]

    pre_edit_ids = {
        "root": root.node_id,
        "child_a": child_a.node_id,
        "child_b": child_b.node_id,
    }

    # Mutate only child_a's content/attributes. Per {p013} identifiers of
    # unchanged nodes are preserved with no global old/new tree remap, so
    # every *other* node's node_id must be identical to its pre-edit uuid4.
    child_a.content = {"label": "child_a", "value": 999}
    child_a.node_id = assign_node_id(existing_id=child_a.node_id)

    assert root.node_id == pre_edit_ids["root"]
    assert child_b.node_id == pre_edit_ids["child_b"]
    assert child_a.node_id == pre_edit_ids["child_a"]


# ---------------------------------------------------------------------------
# (2) node_id stability across a no-op edit / reload
# ---------------------------------------------------------------------------


def test_node_id_stable_on_reload_or_noop_edit(small_tree: Dict[str, Any]) -> None:
    root = small_tree["root"]
    original_id = root.node_id

    # No-op edit: re-set the same content value and re-derive the node_id
    # the way a reload/save-without-change path would.
    root.content = dict(root.content)
    root.node_id = assign_node_id(existing_id=root.node_id)

    assert root.node_id == original_id


# ---------------------------------------------------------------------------
# (3) fresh node ids are valid, unique uuid4s
# ---------------------------------------------------------------------------


def test_new_node_uuid4_is_valid_and_unique(document: _Document) -> None:
    existing_ids = {document.add_node().node_id for _ in range(5)}

    n = 150
    new_ids: List[uuid.UUID] = [document.add_node().node_id for _ in range(n)]

    for node_id in new_ids:
        assert isinstance(node_id, uuid.UUID)
        assert node_id.version == 4
        assert node_id.variant == uuid.RFC_4122

    assert len(set(new_ids)) == n
    assert existing_ids.isdisjoint(set(new_ids))


# ---------------------------------------------------------------------------
# (4) replace_node_id updates the canonical id
# ---------------------------------------------------------------------------


def test_replace_node_id_updates_canonical_id(document: _Document) -> None:
    node = document.add_node(content="hello")
    old_id = node.node_id
    new_id = uuid.uuid4()

    replace_node_id(document, old_id, new_id)

    assert new_id in document.nodes_by_id
    assert document.nodes_by_id[new_id] is node
    assert old_id not in document.nodes_by_id


# ---------------------------------------------------------------------------
# (5) replace_node_id updates internal mappings atomically/consistently
# ---------------------------------------------------------------------------


def test_replace_node_id_atomic_internal_mappings(document: _Document) -> None:
    replaced = document.add_node(content="target")
    bystander = document.add_node(content="bystander")
    old_id = replaced.node_id
    bystander_id = bystander.node_id
    new_id = uuid.uuid4()

    replace_node_id(document, old_id, new_id)

    # The canonical mapping resolves the node only under the new id.
    assert document.nodes_by_id.get(old_id) is None
    assert document.nodes_by_id.get(new_id) is replaced
    # No duplicate entry: exactly one key in the mapping refers to this node.
    keys_pointing_at_node = [
        key for key, value in document.nodes_by_id.items() if value is replaced
    ]
    assert keys_pointing_at_node == [new_id]

    # The node's own node_id attribute (a second lookup path) agrees.
    assert replaced.node_id == new_id
    # {p084}: the per-entry generation counter is incremented by one.
    assert replaced.generation == 1

    # An unrelated node's mapping entry is left completely untouched.
    assert document.nodes_by_id.get(bystander_id) is bystander
    assert bystander.node_id == bystander_id
    assert bystander.generation == 0


# ---------------------------------------------------------------------------
# (6) replace_node_id rejects invalid/duplicate targets without mutation
# ---------------------------------------------------------------------------


def test_replace_node_id_rejects_invalid_or_duplicate_target(
    document: _Document,
) -> None:
    node = document.add_node(content="stays")
    other = document.add_node(content="already-here")
    old_id = node.node_id
    other_id = other.node_id

    pre_call_keys = set(document.nodes_by_id.keys())
    pre_call_node_id = node.node_id
    pre_call_generation = node.generation

    with pytest.raises(NodeIdentityError):
        replace_node_id(document, old_id, "not-a-valid-uuid")

    with pytest.raises(NodeIdentityError):
        replace_node_id(document, old_id, other_id)

    # Full pre-call state is unchanged: no partial mutation on either
    # failure path.
    assert set(document.nodes_by_id.keys()) == pre_call_keys
    assert document.nodes_by_id[old_id] is node
    assert node.node_id == pre_call_node_id
    assert node.generation == pre_call_generation
    assert document.nodes_by_id[other_id] is other


# ---------------------------------------------------------------------------
# (7) replace_node_id returns an AddressRemap with correct addresses
# ---------------------------------------------------------------------------


def test_replace_node_id_returns_address_remap(document: _Document) -> None:
    node = document.add_node(content="remap-me")
    old_id = node.node_id
    new_id = uuid.uuid4()

    remap = replace_node_id(document, old_id, new_id)

    assert isinstance(remap, AddressRemap)
    assert remap.old == NodeAddress(document_id=document.document_id, node_id=old_id)
    assert remap.new == NodeAddress(document_id=document.document_id, node_id=new_id)
    assert remap.old.document_id == remap.new.document_id


# ---------------------------------------------------------------------------
# (8) AddressRemap document_id consistency across multiple replacements
# ---------------------------------------------------------------------------


def test_address_remap_document_id_consistency(document: _Document) -> None:
    node_one = document.add_node(content="one")
    node_two = document.add_node(content="two")

    remap_one = replace_node_id(document, node_one.node_id, uuid.uuid4())
    remap_two = replace_node_id(document, node_two.node_id, uuid.uuid4())

    assert remap_one.old.document_id == document.document_id
    assert remap_one.new.document_id == document.document_id
    assert remap_two.old.document_id == document.document_id
    assert remap_two.new.document_id == document.document_id
