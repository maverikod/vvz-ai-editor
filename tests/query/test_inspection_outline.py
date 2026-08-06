"""Contract tests for the ``model_outline`` response schema (concept C-018).

Covers G-019/T-001/A-004: ``tree_engine.query.outline`` -- the meta header
(``OutlineMeta``), the flat preorder node record (``OutlineNodeRecord``),
the collapsed-subtree stub record (``OutlineStubRecord``), the per-field
truncation contract (``TruncatedField``), the whole-response truncation and
continuation contract (``OutlineTruncation``), and the one assembly helper
(``build_outline_response``).

Per this atomic step's own prompt, every fixture header/node/stub record is
built by hand in this file, rather than produced by the sibling
``drill_down`` inspection operation (owned by a different unit, absent from
this worktree). "By hand" means the ``outline.py`` dataclasses are
constructed with explicit keyword arguments here -- the input values
themselves are not invented: every ``node_id``, ``short_id``, ``type``,
child count, and source-preview byte below is read off real
``tree_engine.core.nodes.Node`` instances produced by actually parsing a
real file of this repository (``src/tree_engine/errors.py``) through the
real ``tree_engine.plugins.python.plugin.PythonFormatPlugin``, which
already assigns a genuine UUID4 ``node_id``/positive-int ``short_id`` pair
to every node during import.

Out of scope, per this atomic step's prompt: ``drill_down``'s own
traversal, depth control, auto-expansion, and address resolution -- a
sibling test file this unit does not own.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Optional

import pytest

from tree_engine.core.address import NodeAddressView, build_node_address_view
from tree_engine.core.nodes import Node, walk
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.query import outline as outline_module
from tree_engine.query.outline import (
    OutlineMeta,
    OutlineNodeRecord,
    OutlineResponse,
    OutlineStubRecord,
    OutlineTruncation,
    TruncatedField,
    build_outline_response,
)

# --------------------------------------------------------------------------
# Fixture: a real Document, parsed by the real Python plugin from a real
# file of this repository -- never a hand-built toy Node graph.
# --------------------------------------------------------------------------

_SOURCE_FILE = Path(__file__).resolve().parents[2] / "src" / "tree_engine" / "errors.py"
_SOURCE_BYTES = _SOURCE_FILE.read_bytes()

_DOCUMENT = PythonFormatPlugin().parse_document(_SOURCE_BYTES.decode("utf-8"))
_ROOT = _DOCUMENT.root
_ALL_NODES = list(walk(_ROOT))

_CLASS_NODES = [n for n in _ALL_NODES if str(n.kind) == "python:ClassDef"]
_FUNC_NODES = [n for n in _ALL_NODES if str(n.kind) == "python:FunctionDef"]

assert str(_ROOT.kind) == "python:Module"
assert len(_CLASS_NODES) >= 2, "fixture source must define at least two classes"
assert len(_FUNC_NODES) >= 1, "fixture source must define at least one function"
assert _ROOT.node_id is not None and _ROOT.short_id is not None, (
    "the real plugin is expected to assign node_id/short_id during import"
)


def _addr(node: Node) -> NodeAddressView:
    return build_node_address_view(node.node_id, node.short_id)


def _short_id_hex(node: Node) -> str:
    return f"0x{int(node.short_id):x}"


def _child_index(parent: Node, node: Node) -> int:
    for index, child in enumerate(parent.children):
        if child is node:
            return index
    raise AssertionError("node is not a direct child of parent in the real tree")


def _name_field_value(node: Node) -> str:
    """The node's real display name off its own ``name`` field, when it has
    one (``ClassDef``/``FunctionDef``), else its kind string."""

    name_field = node.fields.get("name")
    if isinstance(name_field, Node):
        value = name_field.fields.get("value")
        if isinstance(value, str):
            return value
    return str(node.kind)


def _preview_bytes(node: Node) -> bytes:
    if node.buffer_range is None:
        return b""
    start, end = node.buffer_range
    return _SOURCE_BYTES[start:end]


def _record_from_node(
    node: Node,
    parent: Optional[Node],
    *,
    depth: int,
    expanded: bool = True,
    auto_expanded: bool = False,
    truncated: bool = False,
) -> OutlineNodeRecord:
    """Hand-build one ``OutlineNodeRecord`` from a real, already-parsed node."""

    preview = _preview_bytes(node)
    return OutlineNodeRecord(
        node_id=node.node_id,
        short_id_hex=_short_id_hex(node),
        depth=depth,
        parent_id=parent.node_id if parent is not None else None,
        parent_short_id_hex=_short_id_hex(parent) if parent is not None else None,
        child_index=_child_index(parent, node) if parent is not None else 0,
        type=str(node.kind),
        name_or_value=_name_field_value(node),
        attributes={"child_count": len(node.children)},
        child_count=len(node.children),
        shown_child_count=len(node.children),
        subtree_bytes=len(preview) if preview else None,
        source_preview=TruncatedField(value=preview.decode("utf-8", "ignore")),
        expanded=expanded,
        auto_expanded=auto_expanded,
        truncated=truncated,
    )


def _stub_from_node(node: Node) -> OutlineStubRecord:
    """Hand-build one ``OutlineStubRecord`` for a real, unexpanded subtree."""

    preview = _preview_bytes(node)
    return OutlineStubRecord(
        node_id=node.node_id,
        short_id_hex=_short_id_hex(node),
        type=str(node.kind),
        child_count=len(node.children),
        subtree_node_count=len(list(walk(node))),
        subtree_bytes=len(preview) if preview else None,
    )


# OutlineMeta -- the single response header
def test_outline_meta_header_fields():
    viewed = _addr(_ROOT)
    meta = OutlineMeta(
        viewed=viewed, depth=2, expand_below_bytes=8192,
        document_version="doc-v1", node_count=3, response_bytes=512,
    )

    assert meta.viewed == viewed
    assert meta.viewed.node_id == str(_ROOT.node_id)
    assert meta.viewed.short_id_hex == _short_id_hex(_ROOT)
    assert (meta.depth, meta.expand_below_bytes, meta.document_version) == (2, 8192, "doc-v1")
    assert (meta.node_count, meta.response_bytes) == (3, 512)


# OutlineNodeRecord -- the flat preorder node record
def test_outline_node_record_fields():
    node, parent = _CLASS_NODES[0], _ROOT
    expected_name = _name_field_value(node)
    expected_child_index = _child_index(parent, node)
    preview_text = _preview_bytes(node).decode("utf-8", "ignore")

    record = OutlineNodeRecord(
        node_id=node.node_id,
        short_id_hex=_short_id_hex(node),
        depth=1,
        parent_id=parent.node_id,
        parent_short_id_hex=_short_id_hex(parent),
        child_index=expected_child_index,
        type=str(node.kind),
        name_or_value=expected_name,
        attributes={"bases": len(node.fields["bases"])},
        child_count=len(node.children),
        shown_child_count=len(node.children),
        subtree_bytes=len(preview_text.encode("utf-8")),
        source_preview=TruncatedField(value=preview_text, field_truncated=False),
        expanded=True,
        auto_expanded=False,
        truncated=False,
    )

    assert (record.node_id, record.short_id_hex, record.depth) == (node.node_id, _short_id_hex(node), 1)
    assert (record.parent_id, record.parent_short_id_hex) == (parent.node_id, _short_id_hex(parent))
    assert (record.child_index, record.type, record.name_or_value) == (
        expected_child_index, "python:ClassDef", expected_name,
    )
    assert record.attributes == {"bases": len(node.fields["bases"])}
    assert (record.child_count, record.shown_child_count) == (len(node.children), len(node.children))
    assert record.subtree_bytes == len(preview_text.encode("utf-8"))
    assert (record.source_preview.value, record.source_preview.field_truncated) == (preview_text, False)
    assert (record.expanded, record.auto_expanded, record.truncated) == (True, False, False)

    # The two computed-address properties, exercised against the real {p021}
    # helper every other node-view assembler in the engine is expected to use.
    assert record.address == build_node_address_view(node.node_id, node.short_id)
    assert record.parent == build_node_address_view(parent.node_id, parent.short_id)

    # The viewed node itself, with no shown parent in the response: absence
    # of one half of the {p021} pair implies absence of the other.
    viewed_record = _record_from_node(_ROOT, None, depth=0)
    assert (viewed_record.parent_id, viewed_record.parent_short_id_hex) == (None, None)
    assert viewed_record.parent is None


# OutlineStubRecord -- the collapsed-subtree stub, for nodes beyond depth
def test_outline_stub_record_fields_and_expandable_flag():
    node = _CLASS_NODES[1]
    subtree_node_count = len(list(walk(node)))
    preview = _preview_bytes(node)

    stub = OutlineStubRecord(
        node_id=node.node_id,
        short_id_hex=_short_id_hex(node),
        type=str(node.kind),
        child_count=len(node.children),
        subtree_node_count=subtree_node_count,
        subtree_bytes=len(preview),
    )

    assert (stub.node_id, stub.short_id_hex, stub.type) == (node.node_id, _short_id_hex(node), "python:ClassDef")
    assert (stub.child_count, stub.subtree_node_count, stub.subtree_bytes) == (
        len(node.children), subtree_node_count, len(preview),
    )
    assert stub.expandable is True
    assert stub.address == build_node_address_view(node.node_id, node.short_id)

    # `expandable` is declared `init=False`: a stub can never be built
    # claiming a collapsed subtree is not expandable.
    with pytest.raises(TypeError):
        OutlineStubRecord(
            node_id=node.node_id,
            short_id_hex=_short_id_hex(node),
            type=str(node.kind),
            child_count=0,
            subtree_node_count=0,
            subtree_bytes=None,
            expandable=False,  # type: ignore[call-arg]
        )


# TruncatedField -- the per-field truncation contract
def test_per_field_truncation_contract():
    node = _ROOT
    full_bytes = _SOURCE_BYTES
    cut_preview = full_bytes[:40].decode("utf-8", "ignore")
    truncated_preview = TruncatedField(
        value=cut_preview, field_truncated=True, original_field_bytes=len(full_bytes)
    )
    untouched_attr = TruncatedField(value="ok", field_truncated=False, original_field_bytes=None)
    big_original = "x" * 5000
    truncated_attr = TruncatedField(
        value=big_original[:64], field_truncated=True, original_field_bytes=len(big_original)
    )

    record = OutlineNodeRecord(
        node_id=node.node_id,
        short_id_hex=_short_id_hex(node),
        depth=0,
        parent_id=None,
        parent_short_id_hex=None,
        child_index=0,
        type=str(node.kind),
        name_or_value=_name_field_value(node),
        attributes={"docstring": untouched_attr, "huge_attr": truncated_attr},
        child_count=len(node.children),
        shown_child_count=len(node.children),
        subtree_bytes=len(full_bytes),
        source_preview=truncated_preview,
        expanded=True,
        auto_expanded=False,
        truncated=True,
    )

    # The one wrapped field carries its cut contract...
    assert (record.source_preview.field_truncated, record.source_preview.original_field_bytes) == (
        True, len(full_bytes),
    )
    assert record.source_preview.value == cut_preview
    # ...while a sibling optional field, wrapped separately, is untouched...
    assert (record.attributes["docstring"].field_truncated, record.attributes["docstring"].original_field_bytes) == (
        False, None,
    )
    # ...and a third, independently wrapped field can be cut on its own.
    assert (record.attributes["huge_attr"].field_truncated, record.attributes["huge_attr"].original_field_bytes) == (
        True, len(big_original),
    )
    # Mandatory address/structural fields are never wrapped in TruncatedField.
    for mandatory in (record.node_id, record.short_id_hex, record.type, record.child_count):
        assert not isinstance(mandatory, TruncatedField)
    assert (record.node_id, record.type) == (node.node_id, "python:Module")


# OutlineTruncation -- whole-response truncation and continuation
def test_whole_response_truncation_and_continuation():
    continuation_node = _CLASS_NODES[1]
    continuation_addr = _addr(continuation_node)

    truncation = OutlineTruncation(
        truncated=True, omitted_nodes=7, omitted_bytes=4096, continuation=continuation_addr,
    )

    assert (truncation.truncated, truncation.omitted_nodes, truncation.omitted_bytes) == (True, 7, 4096)
    assert truncation.continuation == continuation_addr
    assert (truncation.continuation.node_id, truncation.continuation.short_id_hex) == (
        str(continuation_node.node_id), _short_id_hex(continuation_node),
    )

    # The ordinary, untruncated case: continuation defaults to None.
    ordinary = OutlineTruncation(truncated=False, omitted_nodes=0, omitted_bytes=0)
    assert ordinary.continuation is None

    meta = OutlineMeta(
        viewed=_addr(_ROOT), depth=1, expand_below_bytes=8192,
        document_version="doc-v1", node_count=1, response_bytes=100,
    )
    node_record = _record_from_node(_CLASS_NODES[0], _ROOT, depth=1)
    response = build_outline_response(meta, [node_record], truncation)

    assert isinstance(response, OutlineResponse)
    assert response.truncation is truncation
    assert response.truncation.continuation == continuation_addr
    assert isinstance(response.nodes, tuple)
    assert response.nodes == (node_record,)


# short_id_hex is always paired with node_id, never a substitute for it
def test_short_id_hex_never_substitutes_for_node_id():
    node = _CLASS_NODES[0]
    record = _record_from_node(node, _ROOT, depth=1)

    assert (record.node_id, record.short_id_hex) == (node.node_id, _short_id_hex(node))
    assert record.node_id != record.short_id_hex
    assert record.short_id_hex.startswith("0x")
    assert (record.address.node_id, record.address.short_id_hex) == (str(node.node_id), record.short_id_hex)

    stub_node = _CLASS_NODES[1]
    stub = _stub_from_node(stub_node)

    assert (stub.node_id, stub.short_id_hex) == (stub_node.node_id, _short_id_hex(stub_node))
    assert stub.node_id != stub.short_id_hex
    assert (stub.address.node_id, stub.address.short_id_hex) == (str(stub_node.node_id), stub.short_id_hex)


# The module performs no traversal or address resolution of its own
def test_outline_module_performs_no_traversal():
    # Two real node records plus one real stub, assembled deliberately out
    # of the tree's actual preorder position (the second class before the
    # first, plus an unrelated function's stub) to prove
    # build_outline_response neither walks the tree, nor resolves
    # addresses, nor reorders or revalidates what it is handed.
    record_a = _record_from_node(_CLASS_NODES[1], _ROOT, depth=1)
    stub = _stub_from_node(_FUNC_NODES[0])
    record_b = _record_from_node(_CLASS_NODES[0], _ROOT, depth=1)
    given_nodes = [record_a, stub, record_b]

    meta = OutlineMeta(
        viewed=_addr(_ROOT), depth=1, expand_below_bytes=0,
        document_version="stale-on-purpose",
        node_count=999,  # deliberately mismatched vs. len(given_nodes)
        response_bytes=1,
    )
    truncation = OutlineTruncation(truncated=False, omitted_nodes=0, omitted_bytes=0)

    response = build_outline_response(meta, given_nodes, truncation)

    # Order preserved exactly as given -- never resorted into preorder.
    assert response.nodes == (record_a, stub, record_b)
    # node_count is never recomputed or validated against len(nodes): this
    # module only threads through what its caller already computed.
    assert response.meta.node_count == 999
    assert response.meta.node_count != len(response.nodes)

    # And, structurally: the module's own namespace never acquired a
    # tree-walking primitive (it would have to import one to call it), while
    # it does reuse the real {p021} address-view type.
    for absent_name in ("walk", "iter_children", "Node", "Document"):
        assert not hasattr(outline_module, absent_name), (
            f"outline.py unexpectedly has {absent_name!r} in its namespace"
        )
    assert outline_module.NodeAddressView is NodeAddressView
    source = inspect.getsource(outline_module)
    assert "walk(" not in source
    assert "iter_children(" not in source
