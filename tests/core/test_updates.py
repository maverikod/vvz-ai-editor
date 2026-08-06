"""Contract tests for tree_engine.core.updates: set_attribute, set_body,
set_source_fragment, and replace_node_id (concept C-006, {p011}, {p038},
{p109}).

Covers: set_attribute's export-field and non-export-field cases, asserting
the admissibility classification followed is the one already defined by
node_types.py's ExportFieldMixin (used directly here, never duplicated);
set_body accepting text, a single node, and a sequence of nodes, rejection
of a body inadmissible for the parent's type on both the text and the
node/sequence path, and indentation preservation with untouched siblings;
the shared reparse hand-off used by both set_body and set_source_fragment,
successful and rejected (rollback plus the reparse stage's own error code
surfacing unchanged); and replace_node_id's UUID4 rewrite across
parent/child object links, semantic references and nodes_by_id, its
returned AddressRemap, its supplied-documents-only reach, and its
before-any-mutation collision guard.

Deliberately excludes insert, delete, replace_range and the internal
reparse decision logic -- those belong to test_operations.py and
test_reparse.py.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from tree_engine.core.identity import AddressRemap, NodeAddress, NodeIdentityError
from tree_engine.core.node_types import (
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.operations import MutationError
from tree_engine.core.reparse import (
    STATUS_SKIPPED,
    STATUS_STRUCTURED,
    STATUS_TEXTUAL,
    ReparseError,
)
from tree_engine.core.updates import replace_node_id, set_attribute, set_body, set_source_fragment
from tree_engine.errors import ErrorCode


# ---------------------------------------------------------------------------
# Minimal duck-typed stand-ins, mirrored from test_operations.py/test_reparse.py
# ---------------------------------------------------------------------------


class _Node:
    def __init__(
        self,
        node_id: Any,
        *,
        short_id: Any = None,
        kind: str = "node",
        content: str = "",
        children: Optional[Sequence["_Node"]] = None,
        parent: Optional["_Node"] = None,
        references: Sequence[Any] = (),
    ) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self.kind = kind
        self.content = content
        self.children: List["_Node"] = list(children) if children else []
        self.parent = parent
        self.references: Tuple[Any, ...] = tuple(references)


class _Document:
    def __init__(self, document_id: Optional[uuid.UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[Any, Any] = {}
        self.short_id_index: Dict[Any, Any] = {}


def _register(document: _Document, *roots: _Node) -> None:
    stack = list(roots)
    while stack:
        node = stack.pop()
        document.nodes_by_id[node.node_id] = node
        if node.short_id is not None:
            document.short_id_index[node.short_id] = node.node_id
        stack.extend(node.children)


def _never_parse(text: str, *, source_format_id: str) -> str:
    raise AssertionError("parse_fragment must not be called")


# ---------------------------------------------------------------------------
# set_attribute: export-field admissibility deferred to node_types.py, plus
# a non-export field.
# ---------------------------------------------------------------------------


class TestSetAttributeExportFieldPolicy:
    def test_export_accepted_on_a_type_node_types_marks_applicable(self) -> None:
        node = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a")
        document = _Document()
        document.nodes_by_id[node.node_id] = node
        assert node._export_applicable is True  # the classification under test

        result = set_attribute(document, node, "export", True)

        assert result.node_id == node.node_id
        assert node.export is True

    def test_export_rejected_on_a_type_node_types_marks_inapplicable(self) -> None:
        node = PreprocessorDirectiveNode(start_byte=0, end_byte=1, content="#x")
        document = _Document()
        document.nodes_by_id[node.node_id] = node
        assert node._export_applicable is False  # the classification under test

        with pytest.raises(MutationError) as excinfo:
            set_attribute(document, node, "export", True)

        # Same ErrorCode the node's own ExportNotApplicableError carries --
        # updates.py wraps it, it does not classify anything itself.
        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_PARENT_TYPE]
        assert node.export is False  # nothing mutated on the rejected path

    def test_non_export_field_is_set_without_any_export_style_gate(self) -> None:
        node = VariableDeclaratorNode(start_byte=0, end_byte=1, content="old", name="a")
        document = _Document()
        document.nodes_by_id[node.node_id] = node

        result = set_attribute(document, node, "content", "new")

        assert node.content == "new"
        assert result.short_id == node.short_id


# ---------------------------------------------------------------------------
# set_body: text / single node / sequence of nodes, admissibility rejection,
# indentation preservation, untouched siblings.
# ---------------------------------------------------------------------------


class TestSetBodyAcceptsTextNodeAndSequence:
    def _parent_with_children(self) -> Tuple[_Node, _Node, _Node, _Document]:
        parent = _Node(uuid.uuid4(), short_id="P", content="    old body")
        sibling = _Node(uuid.uuid4(), short_id="S", content="sibling text", parent=parent)
        old_child = _Node(uuid.uuid4(), short_id="OLD", content="old child", parent=parent)
        parent.children = [old_child]
        document = _Document()
        _register(document, parent, sibling)
        return parent, sibling, old_child, document

    def test_text_body_preserves_indentation_and_leaves_siblings_untouched(self) -> None:
        parent, sibling, old_child, document = self._parent_with_children()
        parent.content = "    return old()"

        outcome = set_body(
            document, parent, "return new()",
            admits_nested_structure=lambda node: False, parse_fragment=_never_parse,
        )

        assert parent.content == "    return new()"  # own indentation kept
        assert sibling.content == "sibling text"  # untouched neighbor
        assert outcome.reparse.status == STATUS_SKIPPED
        assert outcome.mutation.node_id == parent.node_id

    def test_single_node_body_replaces_children_and_is_never_reparsed(self) -> None:
        parent, sibling, old_child, document = self._parent_with_children()
        new_node = _Node(uuid.uuid4(), short_id="NEW", kind="stmt")

        outcome = set_body(
            document, parent, new_node,
            admits_nested_structure=lambda node: False, parse_fragment=_never_parse,
            is_type_compatible=lambda p, pos, incoming: True,
        )

        assert parent.children == [new_node]
        assert new_node.parent is parent
        assert old_child.node_id not in document.nodes_by_id
        assert document.nodes_by_id[new_node.node_id] is new_node
        assert sibling.content == "sibling text"
        assert outcome.reparse is None
        assert outcome.mutation.removed == (NodeAddress(document_id=document.document_id, node_id=old_child.node_id),)
        assert outcome.mutation.inserted == (NodeAddress(document_id=document.document_id, node_id=new_node.node_id),)

    def test_sequence_body_replaces_children_in_order(self) -> None:
        parent, sibling, old_child, document = self._parent_with_children()
        first = _Node(uuid.uuid4(), short_id="N1", kind="stmt")
        second = _Node(uuid.uuid4(), short_id="N2", kind="stmt")

        outcome = set_body(
            document, parent, [first, second],
            admits_nested_structure=lambda node: False, parse_fragment=_never_parse,
            is_type_compatible=lambda p, pos, incoming: True,
        )

        assert parent.children == [first, second]
        assert first.parent is parent and second.parent is parent
        assert outcome.mutation.inserted == (
            NodeAddress(document_id=document.document_id, node_id=first.node_id),
            NodeAddress(document_id=document.document_id, node_id=second.node_id),
        )
        assert sibling.content == "sibling text"

    def test_text_body_rejected_for_incompatible_parent_type_mutates_nothing(self) -> None:
        parent, sibling, old_child, document = self._parent_with_children()
        parent.content = "unchanged"

        with pytest.raises(MutationError) as excinfo:
            set_body(
                document, parent, "rejected text",
                admits_nested_structure=lambda node: False, parse_fragment=_never_parse,
                is_type_compatible=lambda node, field, value: False,
            )

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_PARENT_TYPE]
        assert parent.content == "unchanged"

    def test_node_body_rejected_for_incompatible_parent_type_leaves_children_untouched(self) -> None:
        parent, sibling, old_child, document = self._parent_with_children()
        rejected = _Node(uuid.uuid4(), short_id="REJ", kind="stmt")

        with pytest.raises(MutationError) as excinfo:
            set_body(
                document, parent, rejected,
                admits_nested_structure=lambda node: False, parse_fragment=_never_parse,
                is_type_compatible=lambda p, pos, incoming: False,
            )

        assert [e.code for e in excinfo.value.errors] == [ErrorCode.INVALID_PARENT_TYPE]
        assert parent.children == [old_child]  # completely untouched
        assert old_child.node_id in document.nodes_by_id
        assert rejected.node_id not in document.nodes_by_id


# ---------------------------------------------------------------------------
# set_body / set_source_fragment: the shared reparse hand-off, success and
# rejection/rollback with the reparse stage's own ErrorCode preserved.
# ---------------------------------------------------------------------------


def _target_document() -> Tuple[_Node, _Document]:
    target = _Node(uuid.uuid4(), short_id="T", kind="container", content="old text")
    document = _Document()
    _register(document, target)
    return target, document


_UPDATE_FUNCS = [set_body, set_source_fragment]


@pytest.mark.parametrize("update_fn", _UPDATE_FUNCS, ids=lambda f: f.__name__)
class TestSetBodyAndSourceFragmentReparseHandoff:
    def test_successful_reparse_handoff_surfaces_the_reparse_outcome(self, update_fn) -> None:
        target, document = _target_document()

        outcome = update_fn(
            document, target, "new text",
            admits_nested_structure=lambda node: True,
            parse_fragment=lambda text, *, source_format_id: text.upper(),
        )

        assert target.content == "new text"  # no shared indentation to keep here
        assert outcome.reparse.status == STATUS_TEXTUAL
        assert outcome.reparse.text == "NEW TEXT"
        assert outcome.mutation.node_id == target.node_id

    @pytest.mark.parametrize(
        "parser, expected_code",
        [
            (lambda text, *, source_format_id: (_ for _ in ()).throw(RuntimeError("boom")), ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED),
            (lambda text, *, source_format_id: [], ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR),
        ],
        ids=["parser_raises", "parser_returns_empty_node_set"],
    )
    def test_rejected_reparse_handoff_rolls_back_and_surfaces_reparse_error_code(
        self, update_fn, parser, expected_code
    ) -> None:
        target, document = _target_document()
        original_text = target.content

        with pytest.raises(ReparseError) as excinfo:
            update_fn(
                document, target, "attempted new text",
                admits_nested_structure=lambda node: True, parse_fragment=parser,
            )

        assert excinfo.value.code == expected_code  # reparse.py's own code, unchanged
        assert target.content == original_text  # the whole update rolled back
        assert target.children == []
        assert document.nodes_by_id == {target.node_id: target}


# ---------------------------------------------------------------------------
# replace_node_id: identity rewrite, references, AddressRemap, supplied-only
# reach, collision guard.
# ---------------------------------------------------------------------------


class TestReplaceNodeIdRewritesAndReturnsAddressRemap:
    def _build(self):
        old_id, new_id = uuid.uuid4(), uuid.uuid4()
        target = _Node(old_id, short_id="T1")
        parent = _Node(uuid.uuid4(), short_id="P")
        parent.children = [target]
        target.parent = parent
        unrelated_id = uuid.uuid4()
        unrelated = _Node(unrelated_id, short_id="U")
        sibling = _Node(
            uuid.uuid4(), short_id="S",
            references=(NodeAddress(document_id=None, node_id=old_id), NodeAddress(document_id=None, node_id=unrelated_id)),
        )
        parent.children.append(sibling)
        document = _Document()
        _register(document, parent, sibling, unrelated)
        return old_id, new_id, target, parent, sibling, unrelated, document

    def test_rewrites_nodes_by_id_short_id_index_links_and_local_references(self) -> None:
        old_id, new_id, target, parent, sibling, unrelated, document = self._build()

        remap = replace_node_id(document, old_id, new_id)

        assert target.node_id == new_id
        assert old_id not in document.nodes_by_id
        assert document.nodes_by_id[new_id] is target
        assert document.short_id_index["T1"] == new_id  # short_id itself unchanged, only its target
        assert parent.children[0] is target  # parent/child object link naturally follows
        assert parent.children[0].node_id == new_id
        assert sibling.references == (
            NodeAddress(document_id=None, node_id=new_id),
            NodeAddress(document_id=None, node_id=unrelated.node_id),  # untouched, different node
        )
        assert remap == AddressRemap(
            old=NodeAddress(document_id=document.document_id, node_id=old_id),
            new=NodeAddress(document_id=document.document_id, node_id=new_id),
        )

    def test_retargets_explicit_references_only_in_supplied_loaded_documents(self) -> None:
        old_id, new_id, target, parent, sibling, unrelated, document = self._build()

        other_doc = _Document()
        explicit_ref_node = _Node(
            uuid.uuid4(), references=(NodeAddress(document_id=document.document_id, node_id=old_id),),
        )
        # A same-valued *local* reference in this other document names a node
        # local to it, never the renamed one -- left alone regardless of
        # whether the document is supplied.
        locally_shadowed_node = _Node(uuid.uuid4(), references=(NodeAddress(document_id=None, node_id=old_id),))
        _register(other_doc, explicit_ref_node, locally_shadowed_node)

        unsupplied_doc = _Document()
        unsupplied_ref_node = _Node(
            uuid.uuid4(), references=(NodeAddress(document_id=document.document_id, node_id=old_id),),
        )
        _register(unsupplied_doc, unsupplied_ref_node)

        replace_node_id(document, old_id, new_id, loaded_documents={other_doc.document_id: other_doc})

        assert explicit_ref_node.references == (NodeAddress(document_id=document.document_id, node_id=new_id),)
        assert locally_shadowed_node.references == (NodeAddress(document_id=None, node_id=old_id),)
        # Never visited -- left untouched by design, not because it failed to match.
        assert unsupplied_ref_node.references == (NodeAddress(document_id=document.document_id, node_id=old_id),)

    def test_refuses_a_colliding_new_id_before_any_mutation(self) -> None:
        old_id, new_id, target, parent, sibling, unrelated, document = self._build()
        colliding_id = unrelated.node_id  # already present in nodes_by_id
        before_keys = frozenset(document.nodes_by_id)
        before_refs = sibling.references
        before_short_index = dict(document.short_id_index)

        with pytest.raises(NodeIdentityError):
            replace_node_id(document, old_id, colliding_id)

        assert target.node_id == old_id  # nothing mutated
        assert frozenset(document.nodes_by_id) == before_keys
        assert sibling.references == before_refs
        assert document.short_id_index == before_short_index
