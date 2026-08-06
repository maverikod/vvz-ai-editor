"""Compatibility tests: the ported ``tree_engine`` engine vs. the legacy,
unchanged ``ai_editor`` implementation (concept C-022, G-028/T-001/A-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Model file: ``tests/query/test_compat_cst_query.py`` (G-018/T-001/A-007) --
same discipline: real source, real plugins on both sides, no mocks,
comparison limited to what is genuinely comparable, with an explicit note
wherever it is not. ``test_cst_query_scenarios_ported`` does NOT re-derive
that file's scenario matrix; it is a one-selector smoke check that this
file's own fixtures agree with it, pointing there for the full suite.

Two kinds of "same contract" apply. (1) load/save/insert/delete/replace/
identifier-change ({p027}): both engines expose a real edit path over the
same Python source -- a genuine comparison, detailed on
``test_ai_editor_load_save_insert_delete_replace_identifier_change_ported``.
(2) copy_subtree ({p078}) and move ({p079}): grep-verified, ``ai_editor``
has zero occurrences of a copy-subtree or move primitive -- its per-file
marker/mark-unmark model has no cross-document UUID4 node identity at all,
so there is nothing on the legacy side to compare against; these are new
port-only capabilities, pinned instead on real ``PythonFormatPlugin``-parsed
trees wherever the operation's own duck-typed contract allows it:
``copy_subtree`` is read-only and works directly on a real ``Document``;
``move`` needs caller-mutable nodes the immutable plugin tree has no
production adapter for yet (``move.py``'s docstring calls its two sibling
facilities "not yet importable modules" here), so those tests drive the
real ``move()`` against the minimal mutable contract it documents itself.
None of this re-derives the exhaustive matrices already owned by
``tests/core/test_subtree_copy.py``, ``tests/core/test_move.py`` and
``tests/core/test_move_cross_document.py`` -- each test here is the
smallest real slice proving this step's named behavior holds.

``tests/compat/`` needs no ``__init__.py``: no other ``test_ported_contract.py``
exists anywhere in the repository -- no basename collision to guard against
(unlike ``tests/storage/``/``tests/unit/``, which carry the marker for one).
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import UUID

import pytest

from ai_editor.cst_query.executor import query_source
from ai_editor.tree.handlers.python_handler import PythonHandler

from tree_engine.core.identity import NodeAddress
from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.move import MoveError, move
from tree_engine.core.move_references import reconcile_references
from tree_engine.core.subtree_copy import CopiedDocument, copy_subtree
from tree_engine.errors import ErrorCode
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.query.engine import TreeQueryEngine

PLUGIN = PythonFormatPlugin()

_EDIT_SOURCE = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"


def _def_marker(marked: str, func_name: str) -> int:
    """Extract the legacy ``# ___id___:N`` marker on a ``def <name>():`` line."""

    match = re.search(rf"def {func_name}\(\): # ___id___:(\d+)", marked)
    assert match is not None, marked
    return int(match.group(1))


def _rebuild_root(document: Any, new_children: Any) -> Any:
    """Rebuild a plugin-parsed immutable ``Document``'s root with new
    top-level children -- the bottom-up ``dataclasses.replace`` technique
    ``subtree_copy.py`` itself uses; no production code added, only the
    public dataclass fields plus stdlib ``dataclasses.replace``."""
    new_children = tuple(new_children)
    new_root = dataclasses.replace(
        document.root,
        children=new_children,
        fields={**document.root.fields, "body": new_children},
    )
    return dataclasses.replace(document, root=new_root)


def _facade(document: Any) -> Any:
    """Minimal read-only ``nodes_by_id``/``parent_index`` facade over a real
    plugin-parsed ``Document``, matching ``copy_subtree``'s own duck-typed
    contract (``PythonFormatPlugin``'s ``Document`` exposes no
    ``nodes_by_id`` -- the same gap already documented for ``drill_down``);
    wraps the real parsed tree, never fabricates node data."""
    nodes_by_id: Dict[UUID, Any] = {}
    parent_index: Dict[UUID, Optional[UUID]] = {}

    def _index(node: Any, parent_id: Optional[UUID]) -> None:
        nodes_by_id[node.node_id] = node
        parent_index[node.node_id] = parent_id
        for child in node.children:
            _index(child, node.node_id)

    _index(document.root, None)
    return SimpleNamespace(
        root=document.root, nodes_by_id=nodes_by_id, parent_index=parent_index,
        document_id=uuid.uuid4(), document_version=1,
    )


def _bar_setup() -> Any:
    """A real parsed ``_EDIT_SOURCE`` document, its facade, and ``bar``'s
    own real node -- shared setup for the two ``preserve_ids`` tests."""

    document = PLUGIN.parse_document(_EDIT_SOURCE)
    facade = _facade(document)
    return facade, document.root.children[1]


def test_ai_editor_load_save_insert_delete_replace_identifier_change_ported() -> None:
    """Legacy load(``mark``)/save(``unmark``)/``op_insert``/``op_delete``/
    ``op_replace`` vs. ported ``parse_document``/``generate_output`` plus a
    bottom-up immutable rebuild (``_rebuild_root``), on identical real
    Python source, compared on what both genuinely share ({p027}): (1)
    load+save round-trips byte-identically before any edit; (2) after the
    identical edit sequence (insert a sibling, delete one, replace one's
    body) the deleted text is gone and the inserted text present on both
    outputs; (3) identifier stability ("identifier change" scope): a
    function untouched by a given edit keeps the SAME identifier across it
    on both engines -- legacy marker short_id, ported node_id/short_id.
    Exact VALUES are never compared (different id spaces) -- only the
    stability property is. Not comparable: exact whitespace/formatting
    around an edit point -- neither engine documents that as contract, so
    only content presence/absence is asserted for mutated portions.
    """
    # ---- legacy: load (mark), save (unmark) round trip ----
    handler = PythonHandler()
    marked = handler.mark(_EDIT_SOURCE)
    assert handler.unmark(marked) == _EDIT_SOURCE

    foo_sid = _def_marker(marked, "foo")
    bar_sid = _def_marker(marked, "bar")

    marked = handler.op_insert(
        marked, anchor_short_id=bar_sid, position="after",
        new_content="def baz():\n    return 3\n", next_free=max(foo_sid, bar_sid) + 3,
    )
    baz_sid_before = _def_marker(marked, "baz")
    marked = handler.op_delete(marked, short_id=foo_sid)
    marked = handler.op_replace(
        marked, short_id=bar_sid, new_content="def bar():\n    return 20\n"
    )
    baz_sid_after = _def_marker(marked, "baz")
    legacy_final = handler.unmark(marked)

    assert baz_sid_after == baz_sid_before  # untouched sibling: identifier stable
    assert "def foo" not in legacy_final
    assert "def baz" in legacy_final and "return 3" in legacy_final
    assert "return 20" in legacy_final

    # ---- ported: load (parse_document), save (generate_output) round trip ----
    document = PLUGIN.parse_document(_EDIT_SOURCE)
    assert PLUGIN.generate_output(document) == _EDIT_SOURCE.encode()

    foo_node, bar_node = document.root.children
    baz_node = PLUGIN.parse_fragment("def baz():\n    return 3\n")
    baz_identity_before = (baz_node.node_id, baz_node.short_id)

    document = _rebuild_root(document, (foo_node, bar_node, baz_node))  # insert baz
    document = _rebuild_root(document, (bar_node, baz_node))  # delete foo
    bar2_node = PLUGIN.parse_fragment("def bar():\n    return 20\n")
    document = _rebuild_root(document, (bar2_node, baz_node))  # replace bar
    ported_final = PLUGIN.generate_output(document).decode()

    assert (baz_node.node_id, baz_node.short_id) == baz_identity_before  # stable
    assert "def foo" not in ported_final
    assert "def baz" in ported_final and "return 3" in ported_final
    assert "return 20" in ported_final


def test_cst_query_scenarios_ported() -> None:
    """The exhaustive selector matrix comparing ``TreeQueryEngine`` against
    legacy ``query_source`` lives in ``tests/query/test_compat_cst_query.py``
    (G-018/T-001/A-007), not re-derived here: this is the one-selector proof
    this file's own fixtures agree with it -- match count and ``kind``."""
    matches_new = TreeQueryEngine(PLUGIN.parse_document(_EDIT_SOURCE), PLUGIN).query(
        "function"
    )
    matches_legacy = query_source(_EDIT_SOURCE, "function")

    assert len(matches_new) == len(matches_legacy) == 2
    assert {m.kind for m in matches_new} == {"function"}
    assert {m.kind for m in matches_legacy} == {"function"}


def test_copy_subtree_preserve_ids_false_new_uuids_and_mapping() -> None:
    """{p078}: ``preserve_ids=False`` mints a fresh UUID4 and a correct
    old->new map, on a real subtree (``bar``, via :func:`_facade`). No
    legacy comparison (see module docstring); exhaustive matrix:
    ``tests/core/test_subtree_copy.py``."""
    facade, bar_node = _bar_setup()
    copied = copy_subtree(facade, node_id=bar_node.node_id, preserve_ids=False)

    assert isinstance(copied, CopiedDocument)
    assert copied.root.node_id != bar_node.node_id
    assert copied.old_uuid_to_new_uuid[bar_node.node_id] == copied.root.node_id
    assert bar_node.node_id not in copied.nodes_by_id


def test_copy_subtree_preserve_ids_true_uuid_preservation() -> None:
    """{p078}: ``preserve_ids=True`` keeps every UUID4 unchanged under a new
    ``document_id``, on the same real subtree. No legacy comparison (see
    module docstring); exhaustive matrix: ``tests/core/test_subtree_copy.py``."""
    facade, bar_node = _bar_setup()
    copied = copy_subtree(facade, node_id=bar_node.node_id, preserve_ids=True)

    assert copied.root.node_id == bar_node.node_id
    assert copied.document_id != facade.document_id
    assert copied.origin_document_id == facade.document_id
    assert copied.origin_parent_id == facade.parent_index[bar_node.node_id]


def test_copy_subtree_isolation_and_external_reference_preservation() -> None:
    """{p078}: a reference to a node left outside the copied subtree is
    preserved as an explicit external ``NodeAddress``; the copy is a fully
    independent object graph. No legacy comparison (see module docstring);
    exhaustive matrix: ``tests/core/test_subtree_copy.py``."""
    document = PLUGIN.parse_document(_EDIT_SOURCE)
    foo_node, bar_node = document.root.children
    ref_to_foo = NodeAddress(node_id=foo_node.node_id)
    bar_with_ref = dataclasses.replace(bar_node, references=(ref_to_foo,))
    document = _rebuild_root(document, (foo_node, bar_with_ref))
    facade = _facade(document)

    copied = copy_subtree(facade, node_id=bar_with_ref.node_id, preserve_ids=False)

    assert len(copied.root.references) == 1
    ext_ref = copied.root.references[0]
    assert ext_ref.document_id == facade.document_id
    assert ext_ref.node_id == foo_node.node_id  # target id unchanged, outside subtree

    assert copied.root is not bar_with_ref  # independent object
    assert copied.nodes_by_id is not facade.nodes_by_id
    assert bar_with_ref.references == (ref_to_foo,)  # source node untouched


def test_copy_subtree_cross_document() -> None:
    """{p078}: a whole-document copy (``node_id=None``, needing only
    ``document.root`` -- no facade needed) is safe to graft into a second,
    independently parsed real document: no shared identity, no lingering
    tie to its origin. No legacy comparison (see module docstring);
    exhaustive matrix: ``tests/core/test_subtree_copy.py``."""
    source_doc = PLUGIN.parse_document(_EDIT_SOURCE)
    target_doc = PLUGIN.parse_document("def other():\n    pass\n")

    copied = copy_subtree(source_doc, node_id=None, preserve_ids=False)
    grafted = _rebuild_root(
        target_doc, tuple(target_doc.root.children) + tuple(copied.root.children)
    )
    output = PLUGIN.generate_output(grafted)

    assert b"def other" in output and b"def foo" in output and b"def bar" in output
    source_ids = {n.node_id for n in source_doc.root.children}
    assert {n.node_id for n in copied.root.children}.isdisjoint(source_ids)


# move ({p079}): real move()/reconcile_references/DocumentLockCoordinator
# entry points, minimal mutable duck-typed nodes (move.py's own documented
# contract -- see module docstring). No legacy comparison: ai_editor has no
# move primitive at all.


@dataclasses.dataclass
class _MoveNode:
    node_id: UUID
    short_id: Any = None
    children: List["_MoveNode"] = dataclasses.field(default_factory=list)
    parent: Optional["_MoveNode"] = None
    references: Any = ()
    buffer_range: Any = None


@dataclasses.dataclass
class _MoveDoc:
    document_id: UUID = dataclasses.field(default_factory=uuid.uuid4)
    nodes_by_id: Dict[UUID, _MoveNode] = dataclasses.field(default_factory=dict)
    short_id_index: Dict[Any, UUID] = dataclasses.field(default_factory=dict)


def _register(document: _MoveDoc, *roots: _MoveNode) -> None:
    stack = list(roots)
    while stack:
        node = stack.pop()
        document.nodes_by_id[node.node_id] = node
        if node.short_id is not None:
            document.short_id_index[node.short_id] = node.node_id
        stack.extend(node.children)


def _chain(*short_ids: Any, node_ids: Any = None, document_id: Any = None):
    """A registered ``_MoveDoc`` with one root and one short_id-tagged child
    per ``short_ids`` entry (none -> an empty root). Shared setup for the
    move tests below."""

    document = _MoveDoc(document_id=document_id) if document_id else _MoveDoc()
    ids = node_ids or [uuid.uuid4() for _ in short_ids]
    root = _MoveNode(uuid.uuid4())
    root.children = [_MoveNode(i, short_id=s, parent=root) for i, s in zip(ids, short_ids)]
    _register(document, root)
    return document, root, root.children


def test_move_uuid_preservation_and_atomic_updates() -> None:
    """{p079}: an intra-document move preserves the moved node's UUID4 and
    atomically relocates it. Exhaustive matrix: ``tests/core/test_move.py``."""
    doc = _MoveDoc()
    parent_a = _MoveNode(uuid.uuid4())
    parent_b = _MoveNode(uuid.uuid4())
    moved = _MoveNode(uuid.uuid4(), short_id=7, parent=parent_a)
    parent_a.children = [moved]
    _register(doc, parent_a, parent_b)
    moved_id_before = moved.node_id

    result = move(doc, moved.node_id, position="last_child", parent=parent_b.node_id)

    assert result.node_id == moved_id_before  # UUID4 preserved
    assert moved in parent_b.children and moved not in parent_a.children
    assert moved.parent is parent_b


def test_move_cross_document_lock_ordering_and_reference_conversion() -> None:
    """{p079}: one minimal cross-document move through the real
    ``DocumentLockCoordinator`` and ``reconcile_references``: deterministic
    ascending document_id lock order (source deliberately UUID-greater than
    target), plus the outgoing reference-conversion direction. Full matrix:
    ``tests/core/test_move_cross_document.py``."""
    tgt_doc, tgt_root, _unused = _chain(document_id=uuid.UUID(int=1))
    src_doc, _src_root, (moved, remaining) = _chain(1, 2, document_id=uuid.UUID(int=2))
    moved.references = (NodeAddress(node_id=remaining.node_id),)  # outgoing once moved

    coordinator = DocumentLockCoordinator()
    seen_orders: List[List[UUID]] = []

    def _tracking_lock(document_ids: Any) -> Any:
        seen_orders.append(list(document_ids))
        return coordinator.acquire_locks(document_ids)

    move(
        src_doc, moved.node_id, position="last_child", target_document=tgt_doc,
        parent=tgt_root.node_id, lock_coordinator=_tracking_lock,
        reconcile_references=reconcile_references,
    )

    assert len(seen_orders) == 1
    assert seen_orders[0] == sorted(seen_orders[0], key=lambda d: d.int)  # ascending
    assert moved.references == (
        NodeAddress(document_id=src_doc.document_id, node_id=remaining.node_id),
    )


def test_move_short_id_reassignment_and_rollback_on_conflict() -> None:
    """{p079}: target-document short_id reassignment (free preserved,
    conflicting reassigned via the caller allocator, exact remap returned),
    plus full rollback -- both documents left unchanged -- on
    ``NODE_ID_CONFLICT``. Exhaustive matrix: ``tests/core/test_move.py``."""
    src_doc, _src_root, (free_node, conflicting_node) = _chain(7, 3)
    tgt_doc, tgt_root, (existing,) = _chain(3)  # short_id 3 already occupied

    calls = iter([101])
    result = move(
        src_doc, [free_node.node_id, conflicting_node.node_id], position="last_child",
        target_document=tgt_doc, parent=tgt_root.node_id,
        used_short_ids=list(tgt_doc.short_id_index.keys()), next_short_id=lambda: next(calls),
    )

    assert free_node.short_id == 7  # free in target: preserved untouched
    assert conflicting_node.short_id == 101  # conflicting: reassigned
    remap_by_node = {entry.node_id: entry for entry in result.remap}
    assert free_node.node_id not in remap_by_node
    assert remap_by_node[conflicting_node.node_id].new_short_id == 101
    assert existing.short_id == 3  # target's own entry untouched

    # --- rollback on NODE_ID_CONFLICT: same node_id already present in target ---
    conflicting_id = uuid.uuid4()
    src_doc2, src_root2, (moved2,) = _chain(9, node_ids=[conflicting_id])
    tgt_doc2, tgt_root2, _colliding = _chain(99, node_ids=[conflicting_id])
    src_before, tgt_before = dict(src_doc2.nodes_by_id), dict(tgt_doc2.nodes_by_id)

    with pytest.raises(MoveError) as excinfo:
        move(
            src_doc2, moved2.node_id, position="last_child",
            target_document=tgt_doc2, parent=tgt_root2.node_id,
        )

    assert [e.code for e in excinfo.value.errors] == [ErrorCode.NODE_ID_CONFLICT]
    assert src_doc2.nodes_by_id == src_before
    assert tgt_doc2.nodes_by_id == tgt_before
    assert moved2.parent is src_root2  # never detached
