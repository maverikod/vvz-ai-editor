"""Pytest contracts for structured TreeNode (C-001) plus Sidecar (C-002) JSON payloads.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re

import pytest

from ai_editor.core.tree_temp.sidecar_payload import (
    SidecarDocument,
    dumps_sidecar,
    loads_sidecar,
    validate_sidecar_digest_format,
)
from ai_editor.core.tree_temp.tree_node import (
    TreeNode,
    new_uuid_str,
    validate_tree_instance,
)

SAMPLE_DIGEST = "0" * 64


def test_object_member_requires_non_empty_key() -> None:
    root = TreeNode(
        stable_id=new_uuid_str(), type="object", children=[], key=None, value=None
    )
    bad = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="",
        value=7,
        children=None,
    )
    root.children.append(bad)
    with pytest.raises(ValueError, match=re.escape("TreeNode_contract")):
        validate_tree_instance(bad, member_of_object=True)


def test_scalar_root_must_not_carry_key() -> None:
    node = TreeNode(
        stable_id=new_uuid_str(),
        type="string",
        key="forbidden",
        value="x",
        children=None,
    )
    with pytest.raises(ValueError, match="TreeNode_contract"):
        validate_tree_instance(node, member_of_object=False)


def test_each_scalar_kind_accepts_expected_value_shapes() -> None:
    cases: list[tuple[str, object]] = [
        ("string", "a"),
        ("number", 3),
        ("number", -1.25),
        ("boolean", True),
        ("boolean", False),
        ("null", None),
    ]
    for kind, val in cases:
        node = TreeNode(
            stable_id=new_uuid_str(),
            type=kind,  # type: ignore[arg-type]
            key=None,
            value=val,
            children=None,
        )
        validate_tree_instance(node, member_of_object=False)


def test_container_children_ordering_stable() -> None:
    first = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="first",
        value=1,
        children=None,
    )
    second = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="second",
        value=2,
        children=None,
    )
    root = TreeNode(
        stable_id=new_uuid_str(),
        type="object",
        key=None,
        value=None,
        children=[first, second],
    )
    doc = SidecarDocument(source_sha256=SAMPLE_DIGEST, root_nodes=[root])
    loaded = loads_sidecar(dumps_sidecar(doc)).root_nodes[0]
    keys = [c.key for c in (loaded.children or [])]
    assert keys == ["first", "second"]


def test_sidecar_digest_validation_rejects_non_hex() -> None:
    with pytest.raises(ValueError, match="digest_format"):
        validate_sidecar_digest_format("g" + "0" * 63)
    validate_sidecar_digest_format(SAMPLE_DIGEST)


def test_sidecar_roundtrip_preserves_comments_and_stable_ids() -> None:
    child = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="n",
        value=42,
        children=None,
        comment_inline="inline note",
    )
    root = TreeNode(
        stable_id=new_uuid_str(),
        type="object",
        key=None,
        value=None,
        children=[child],
        comment_before="//top",
    )
    doc = SidecarDocument(source_sha256=SAMPLE_DIGEST, root_nodes=[root])
    text = dumps_sidecar(doc)
    again = loads_sidecar(text)
    loaded_child = again.root_nodes[0].children[0]
    assert str(loaded_child.stable_id) == str(child.stable_id)
    assert loaded_child.comment_inline == child.comment_inline
    assert again.root_nodes[0].comment_before == root.comment_before


def test_root_encoding_single_object_vs_root_array_contract() -> None:
    a = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="a",
        value=1,
        children=None,
    )
    b = TreeNode(
        stable_id=new_uuid_str(),
        type="number",
        key="b",
        value=2,
        children=None,
    )
    obj_root = TreeNode(
        stable_id=new_uuid_str(),
        type="object",
        key=None,
        value=None,
        children=[a, b],
    )
    doc_a = SidecarDocument(source_sha256=SAMPLE_DIGEST, root_nodes=[obj_root])
    loaded_a = loads_sidecar(dumps_sidecar(doc_a)).root_nodes
    assert len(loaded_a) == 1
    assert str(loaded_a[0].type) == "object"

    n1 = TreeNode(
        stable_id=new_uuid_str(), type="number", key=None, value=1, children=None
    )
    n2 = TreeNode(
        stable_id=new_uuid_str(), type="number", key=None, value=2, children=None
    )
    doc_b = SidecarDocument(source_sha256=SAMPLE_DIGEST, root_nodes=[n1, n2])
    loaded_b = loads_sidecar(dumps_sidecar(doc_b)).root_nodes
    assert len(loaded_b) == 2
    vals: list[int] = []
    for cast_num in loaded_b:
        v = cast_num.value
        assert isinstance(v, (int, float))
        vals.append(int(v))
    assert sorted(vals) == [1, 2]


def test_empty_object_root_roundtrips() -> None:
    root = TreeNode(
        stable_id=new_uuid_str(),
        type="object",
        key=None,
        value=None,
        children=[],
    )
    doc = SidecarDocument(source_sha256=SAMPLE_DIGEST, root_nodes=[root])
    loaded = loads_sidecar(dumps_sidecar(doc)).root_nodes[0]
    assert loaded.type == "object"
    assert loaded.children is not None
    assert len(loaded.children) == 0
