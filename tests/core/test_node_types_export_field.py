"""Unit tests for the ``export`` field contract on the C-003 extension node
types (tree_engine.core.node_types), per {p044}: ``export`` is a
first-class boolean field of the stable node contract, not an arbitrary
entry a caller stumbles into.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the ``export`` field only -- default value, readability, the
``set_attribute``/``get_attribute`` API, first-class-field status, the
``matches`` search predicate, serialize round-trip, ``copy``, ``move_to``,
explicit rejection on inapplicable node types, and synchronous index-map
reflection. Construction/round-trip of node shape in general (identity,
byte range, content, declarator order/separators, argument children,
traversal) is out of scope here -- see the sibling ``test_node_types.py``.

Note on clause 4 ("not smuggled into generic attributes"): the base
``Node`` contract keeps exactly one per-field data store (``Node.fields``),
and ``node_types.py`` documents plainly that ``export`` lives there
alongside ``content``/``name``/declarator data -- there is no second,
structurally distinct "attributes" mapping on ``Node`` to keep it out of.
The thing this clause can actually guard is the wrapper's own instance
state: ``export`` is exposed only through the dedicated ``.export``
property and the validated ``get_attribute``/``set_attribute`` pair, never
as a loose entry a caller could stumble into on the wrapper's own
``__dict__`` (which is what "generic attribute store" means at the Python
object level -- the plain instance-attribute bag, as opposed to a
descriptor-backed first-class property). That is what is verified below.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tree_engine.core.node_types import (
    AnnotationNode,
    ExportNotApplicableError,
    PreprocessorDirectiveNode,
    VariableDeclarationNode,
    VariableDeclaratorNode,
)
from tree_engine.core.nodes import NodeSchemaError
from tree_engine.errors import ErrorCode

ACCEPTING_TYPES = (VariableDeclarationNode, VariableDeclaratorNode)
REJECTING_TYPES = (PreprocessorDirectiveNode, AnnotationNode)
ALL_TYPES = ACCEPTING_TYPES + REJECTING_TYPES


def _build(cls, **extra):
    """Construct a minimal, valid instance of any of the four extension
    node types, with just enough type-specific required data."""
    kwargs = {"start_byte": 0, "end_byte": 1, "content": "x"}
    if cls is VariableDeclaratorNode:
        kwargs["name"] = "x"
    if cls is VariableDeclarationNode:
        kwargs["declarators"] = ()
        kwargs["separators"] = ()
    kwargs.update(extra)
    return cls(**kwargs)


@pytest.mark.parametrize("node_cls", ALL_TYPES, ids=lambda c: c.__name__)
def test_export_default_false(node_cls) -> None:
    node = _build(node_cls)
    assert node.export is False


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
def test_export_readable(node_cls) -> None:
    # Readable when set at construction.
    constructed = _build(node_cls, export=True)
    assert constructed.export is True

    # Readable when set via the setter.
    via_setter = _build(node_cls)
    via_setter.set_attribute("export", True)
    assert via_setter.export is True
    assert via_setter.get_attribute("export") is True


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
def test_export_set_attribute_toggle(node_cls) -> None:
    node = _build(node_cls)
    assert node.export is False

    node.set_attribute("export", True)
    assert node.export is True

    node.set_attribute("export", False)
    assert node.export is False


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
def test_export_not_in_generic_attributes(node_cls) -> None:
    node = _build(node_cls)
    node.set_attribute("export", True)
    assert node.export is True

    # `export` is a descriptor-backed property on the class, not a loose
    # entry on the wrapper's own instance __dict__ (the generic
    # instance-attribute store a caller would stumble into via plain
    # attribute assignment). See module docstring note above.
    assert "export" not in vars(node)
    assert "export" not in node.__dict__

    # It is reachable only through the dedicated, validated accessors.
    assert node.get_attribute("export") == node.export


def test_export_search_predicate() -> None:
    a = VariableDeclaratorNode(start_byte=0, end_byte=1, content="a", name="a", export=True)
    b = VariableDeclaratorNode(start_byte=3, end_byte=4, content="b", name="b", export=False)
    c = VariableDeclaratorNode(start_byte=6, end_byte=7, content="c", name="c", export=True)
    decl = VariableDeclarationNode(
        start_byte=0, end_byte=7, content="a, b, c",
        declarators=(a, b, c), separators=(", ", ", "),
    )

    exported = [d for d in decl.declarators if d.matches(export=True)]
    not_exported = [d for d in decl.declarators if d.matches(export=False)]

    assert [d.name for d in exported] == ["a", "c"]
    assert [d.name for d in not_exported] == ["b"]


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
def test_export_preserved_import_export_roundtrip(node_cls) -> None:
    # True case.
    true_node = _build(node_cls)
    true_node.set_attribute("export", True)
    true_data = true_node.to_dict()
    assert true_data["fields"]["export"] is True
    rebuilt_true = node_cls.from_dict(true_data)
    assert rebuilt_true.export is True

    # False case, reached via an explicit True -> False transition so the
    # persisted key is genuinely False rather than merely absent -- this
    # rules out a bug that silently drops falsy values and only appears
    # to work because the default also happens to be False.
    false_node = _build(node_cls)
    false_node.set_attribute("export", True)
    false_node.set_attribute("export", False)
    false_data = false_node.to_dict()
    assert false_data["fields"]["export"] is False
    rebuilt_false = node_cls.from_dict(false_data)
    assert rebuilt_false.export is False


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
@pytest.mark.parametrize("value", [True, False], ids=["export-true", "export-false"])
def test_export_preserved_copy(node_cls, value) -> None:
    original = _build(node_cls)
    original.set_attribute("export", value)

    copy = original.copy()
    assert copy.export is value

    # Mutating the source afterward must not affect the already-taken copy.
    original.set_attribute("export", not value)
    assert copy.export is value
    assert original.export is not value


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
@pytest.mark.parametrize("value", [True, False], ids=["export-true", "export-false"])
def test_export_preserved_move(node_cls, value) -> None:
    node = _build(node_cls)
    node.set_attribute("export", value)
    new_parent = uuid4()

    moved = node.move_to(new_parent)

    assert moved is node
    assert node.parent_id == new_parent
    assert node.export is value


@pytest.mark.parametrize("node_cls", REJECTING_TYPES, ids=lambda c: c.__name__)
def test_export_rejected_on_inapplicable_node(node_cls) -> None:
    node = _build(node_cls)

    with pytest.raises(ExportNotApplicableError) as excinfo:
        node.set_attribute("export", True)

    assert isinstance(excinfo.value, NodeSchemaError)
    assert excinfo.value.code == ErrorCode.INVALID_PARENT_TYPE
    assert node.export is False

    # Setting False on a rejecting type is a documented silent no-op, not
    # a further error -- confirm it stays False and raises nothing.
    node.set_attribute("export", False)
    assert node.export is False


@pytest.mark.parametrize("node_cls", ACCEPTING_TYPES, ids=lambda c: c.__name__)
def test_export_index_map_sync_no_stale_read(node_cls) -> None:
    index_map: dict[UUID, bool] = {}

    def hook(node, field_name, value) -> None:
        if field_name == "export":
            index_map[node.node_id] = value

    node = _build(node_cls, index_map_hook=hook)

    node.set_attribute("export", True)
    assert index_map[node.node_id] is True

    node.set_attribute("export", False)
    assert index_map[node.node_id] is False

    node.set_attribute("export", True)
    assert index_map[node.node_id] is True
