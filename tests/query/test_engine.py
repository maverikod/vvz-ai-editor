"""Contract tests for the ported tree-query engine's top-level entry point.

Covers concept C-009, atomic step G-018/T-001/A-006:
``tree_engine.query.engine`` (``TreeQueryEngine.query`` and the module-level
``query`` wrapper). The fixture tree and the fake format plugin driving it
are declared inline in this file.

Out of scope, per the atomic step's own prompt: the traversal adapter's own
role-resolution behavior and predicate evaluation's own internal
correctness beyond exercising both through the full query entry point
(covered by sibling test files under this same tactical step).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import dataclasses
import itertools
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import libcst
import pytest

from ai_editor.core.exceptions import QueryParseError
from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.query.engine import TreeQueryEngine, query as query_fn

# Node kinds are namespaced by format, exactly as the real ported engine
# produces them (e.g. "python:FunctionDef"): a bare literal kind is never a
# valid selector token on its own, only a role alias or a "Type:*" pattern
# reaches these. This fixture reuses that namespacing on purpose.
_MODULE_KIND = "python:Module"
_CLASS_KIND = "python:ClassDef"
_FUNC_KIND = "python:FunctionDef"


class _FakePythonPlugin:
    """Minimal duck-typed plugin mirroring the real Python plugin's role
    resolution (module/class unconditional, FunctionDef promoted to
    "method" when its nearest Module/Class/Function ancestor is a class),
    plus a deterministic ``render_fragment`` for the source-inclusion test.

    ``parse_document`` is a spy standing in for "the fixture's own
    source-parsing entry point": the engine must never call it either.
    """

    def __init__(self) -> None:
        self.parse_calls = 0

    def role_for(self, node: Node, ancestors: Sequence[Node] = ()) -> Optional[str]:
        kind = str(node.kind)
        if kind == _MODULE_KIND:
            return "module"
        if kind == _CLASS_KIND:
            return "class"
        if kind == _FUNC_KIND:
            for ancestor in reversed(tuple(ancestors)):
                ancestor_kind = str(ancestor.kind)
                if ancestor_kind == _CLASS_KIND:
                    return "method"
                if ancestor_kind == _FUNC_KIND:
                    return "function"
            return "function"
        return None

    def semantic_role_mapping(self) -> Dict[str, str]:
        return {_MODULE_KIND: "module", _CLASS_KIND: "class", _FUNC_KIND: "function"}

    def render_fragment(self, node: Node) -> str:
        return f"<{node.kind}:{node.fields.get('name', '')}>"

    def parse_document(self, *args: Any, **kwargs: Any) -> None:
        self.parse_calls += 1
        raise AssertionError("query must never reparse the fixture's source")


def _node(counter: "itertools.count[int]", kind: str, fields: Dict[str, Any], children=()) -> Node:
    built = make_node(kind, fields=fields, children=tuple(children))
    return dataclasses.replace(built, node_id=uuid.uuid4(), short_id=next(counter))


@dataclass(frozen=True)
class _Fixture:
    """Bundles the hand-built document, plugin, engine, and the individual
    fixture nodes so tests can assert against known ``node_id`` values.

    Tree shape: one module containing one class with two methods
    ("on_init", "on_click") and one top-level function ("helper") --
    giving exactly module=1, class=1, function=1, method=2 by role.
    """

    document: Document
    plugin: _FakePythonPlugin
    engine: TreeQueryEngine
    module_node: Node
    class_node: Node
    on_init: Node
    on_click: Node
    helper: Node


@pytest.fixture()
def fixture() -> _Fixture:
    counter = itertools.count(1)
    on_init = _node(counter, _FUNC_KIND, {"name": "on_init"})
    on_click = _node(counter, _FUNC_KIND, {"name": "on_click"})
    class_node = _node(counter, _CLASS_KIND, {"name": "Widget"}, (on_init, on_click))
    helper = _node(counter, _FUNC_KIND, {"name": "helper"})
    module_node = _node(counter, _MODULE_KIND, {"name": "mod"}, (class_node, helper))
    document = Document(root=module_node, source_format_id="python")
    plugin = _FakePythonPlugin()
    engine = TreeQueryEngine(document, plugin)
    return _Fixture(
        document=document,
        plugin=plugin,
        engine=engine,
        module_node=module_node,
        class_node=class_node,
        on_init=on_init,
        on_click=on_click,
        helper=helper,
    )


def _ids(matches) -> set:
    return {match.node_id for match in matches}


# ---------------------------------------------------------------------------
# Node-type (role) selector.
# ---------------------------------------------------------------------------


def test_node_type_selector(fixture: _Fixture) -> None:
    assert _ids(fixture.engine.query("module")) == {fixture.module_node.node_id}
    assert _ids(fixture.engine.query("class")) == {fixture.class_node.node_id}
    assert _ids(fixture.engine.query("function")) == {fixture.helper.node_id}
    assert _ids(fixture.engine.query("method")) == {
        fixture.on_init.node_id,
        fixture.on_click.node_id,
    }


# ---------------------------------------------------------------------------
# Universal selector and a "Type:*" prefix/suffix pattern.
# ---------------------------------------------------------------------------


def test_universal_and_type_pattern_selectors(fixture: _Fixture) -> None:
    all_matches = fixture.engine.query("*")
    assert len(all_matches) == 5  # module + class + 2 methods + function

    def_matches = fixture.engine.query("Def:*")
    assert _ids(def_matches) == {
        fixture.class_node.node_id,
        fixture.on_init.node_id,
        fixture.on_click.node_id,
        fixture.helper.node_id,
    }


# ---------------------------------------------------------------------------
# A name search via the "name" attribute predicate.
# ---------------------------------------------------------------------------


def test_name_search(fixture: _Fixture) -> None:
    matches = fixture.engine.query("*[name='helper']")
    assert _ids(matches) == {fixture.helper.node_id}


# ---------------------------------------------------------------------------
# Each supported predicate form, individually.
# ---------------------------------------------------------------------------


def test_predicate_forms_individually(fixture: _Fixture) -> None:
    eq = fixture.engine.query("function[name='helper']")
    assert _ids(eq) == {fixture.helper.node_id}

    ne = fixture.engine.query("method[name!='on_init']")
    assert _ids(ne) == {fixture.on_click.node_id}

    contains = fixture.engine.query("method[name~='lick']")
    assert _ids(contains) == {fixture.on_click.node_id}

    prefix = fixture.engine.query("method[name^='on_']")
    assert _ids(prefix) == {fixture.on_init.node_id, fixture.on_click.node_id}

    suffix = fixture.engine.query("method[name$='init']")
    assert _ids(suffix) == {fixture.on_init.node_id}


# ---------------------------------------------------------------------------
# Two predicates combined on one step (logical AND).
# ---------------------------------------------------------------------------


def test_combined_predicates_on_one_step(fixture: _Fixture) -> None:
    matches = fixture.engine.query("method[name^='on_'][name$='click']")
    assert _ids(matches) == {fixture.on_click.node_id}

    none_match = fixture.engine.query("method[name^='on_'][name$='nonexistent']")
    assert none_match == []


# ---------------------------------------------------------------------------
# Descendant vs. direct-child combinator.
# ---------------------------------------------------------------------------


def test_descendant_and_child_combinators(fixture: _Fixture) -> None:
    # Methods are descendants of the module (through the class) but not its
    # direct children.
    descendant = fixture.engine.query("module method")
    assert _ids(descendant) == {fixture.on_init.node_id, fixture.on_click.node_id}

    direct_child_of_module = fixture.engine.query("module > method")
    assert direct_child_of_module == []

    direct_child_of_class = fixture.engine.query("class > method")
    assert _ids(direct_child_of_class) == {fixture.on_init.node_id, fixture.on_click.node_id}


# ---------------------------------------------------------------------------
# :first, :last, and :nth pseudo-selectors.
# ---------------------------------------------------------------------------


def test_first_last_nth_pseudo_selectors(fixture: _Fixture) -> None:
    first = fixture.engine.query("method:first")
    last = fixture.engine.query("method:last")
    assert len(first) == 1 and len(last) == 1
    assert first[0].node_id != last[0].node_id

    nth0 = fixture.engine.query("method:nth(0)")
    nth1 = fixture.engine.query("method:nth(1)")
    assert nth0[0].node_id == first[0].node_id
    assert nth1[0].node_id == last[0].node_id


# ---------------------------------------------------------------------------
# A complex, multi-step chained selector.
# ---------------------------------------------------------------------------


def test_complex_chained_selector(fixture: _Fixture) -> None:
    chained = fixture.engine.query("module class method[name^='on_']:first")
    assert len(chained) == 1
    assert chained[0].node_id == fixture.on_init.node_id


# ---------------------------------------------------------------------------
# Optional inclusion of source text.
# ---------------------------------------------------------------------------


def test_optional_source_inclusion(fixture: _Fixture) -> None:
    without_source = fixture.engine.query("function[name='helper']")
    assert without_source[0].source is None

    with_source = fixture.engine.query("function[name='helper']", include_source=True)
    assert with_source[0].source == f"<{_FUNC_KIND}:helper>"


# ---------------------------------------------------------------------------
# Querying never reparses the fixture's source.
# ---------------------------------------------------------------------------


def test_query_never_reparses_source(fixture: _Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("libcst.parse_module must never be called by a query")

    monkeypatch.setattr(libcst, "parse_module", _boom)

    matches = fixture.engine.query("module class method[name^='on_']:first", include_source=True)

    assert len(matches) == 1
    assert fixture.plugin.parse_calls == 0
    # Sanity: the module-level convenience wrapper takes the same path.
    same = query_fn(fixture.document, fixture.plugin, "method")
    assert len(same) == 2


# ---------------------------------------------------------------------------
# A malformed selector raises the legacy QueryParseError, by class identity.
# ---------------------------------------------------------------------------


def test_malformed_selector_raises_legacy_exception(fixture: _Fixture) -> None:
    for bad_selector in ("[[[", "class[name=", "???"):
        with pytest.raises(QueryParseError) as excinfo:
            fixture.engine.query(bad_selector)
        assert type(excinfo.value) is QueryParseError


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
