"""Compatibility tests: ported ``tree_engine.query`` engine vs. the legacy,
unchanged ``ai_editor.cst_query`` engine (concept C-009, G-018/T-001/A-007).

Scope, per {p005}: this file migrates a representative subset of the
existing legacy cst_query test scenarios onto the ported engine, proving the
port preserves *observable* behavior for the same Python source and the same
selector text. It builds one common-tree ``Document`` (via
``tree_engine.plugins.python.plugin.PythonFormatPlugin``) and runs each
selector through ``tree_engine.query.engine.TreeQueryEngine.query`` --
the ported entry point -- then runs the identical selector through the
legacy, unchanged ``ai_editor.cst_query.executor.query_source`` against the
identical source, and compares the outcome: match count, matched node type
(namespace-qualified), and semantic role/kind. Malformed selectors are
checked to raise the identical exception *class*
(``ai_editor.core.exceptions.QueryParseError``, imported unchanged) on both
engines.

Known, verified engine-shape difference this file works around rather than
papers over (per this step's instruction to report what cannot be compared
instead of faking agreement): ``tree_engine.query.results.build_query_match``
reads a node's display name off a plain ``name`` attribute and its position
off a plain ``range`` attribute. For nodes built by the Python format
plugin, LibCST's own "name" field (e.g. ``FunctionDef.name``) is imported as
a nested common-model ``Node`` (kind ``python:Name``), not a scalar, and the
base ``tree_engine.core.nodes.Node`` carries no line/column ``range`` at
all -- so ``QueryMatch.name`` is always ``""`` and ``QueryMatch.range`` is
always ``None`` for Python-plugin matches today. Predicate evaluation
(``tree_engine.query.predicates.evaluate_predicate``) hits the same wall:
asking for ``name``/``qualname``/``type``/``start_line``/``end_line`` on a
Python node either finds a structural ``Node`` value or no attribute at all,
and raises ``QueryParseError`` -- while the legacy executor resolves every
one of those from its own precomputed ``NodeInfo``. Neither gap is a defect
this test file may fix (it must not touch any module), so:

* Match *identity* is compared via count + namespace-qualified type +
  role/kind (``QueryMatch.kind`` and the legacy ``Match.kind`` alias use the
  identical string vocabulary -- ``function``/``method``/``class``/
  ``module`` -- so this axis is genuinely, not superficially, comparable).
  Legacy names are asserted too, as ground truth that the fixture and
  selector under test identify the expected constructs, but the ported
  side's ``QueryMatch.name`` is never asserted to equal them.
* Predicate scenarios use the ``kind`` attribute, the one legacy predicate
  attribute that also resolves without raising on the ported engine for
  *every* node (``kind`` is a mandatory, always-present field on the common
  ``Node`` dataclass) -- even though its value differs in shape (a raw,
  namespaced kind string such as ``python:FunctionDef`` vs. the legacy's
  resolved alias such as ``function``). Selector/value pairs below were
  picked, and empirically verified, to agree on the resulting match set
  despite that shape difference (see the module comments beside each list).
  Predicates on ``name``/``qualname``/``type``/numeric attributes are out of
  scope here for that reason -- they cannot be compared without faking
  agreement, and are exactly the gap called out above.
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

from ai_editor.core.exceptions import QueryParseError
from ai_editor.cst_query.executor import query_source
from ai_editor.cst_query.parser import parse_selector

from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.query.engine import TreeQueryEngine
from tree_engine.query.results import QueryMatch

# One fixture shared by every scenario category below: two classes (one with
# two methods), two top-level functions, and the module itself -- enough
# structure to exercise selector, predicate, combinator, and pseudo-selector
# behavior without needing a second source snippet.
_SOURCE = """class Foo:
    def bar(self):
        pass

    def baz(self):
        return 1


class Empty:
    pass


def standalone():
    pass


def _private():
    pass
"""

_PLUGIN = PythonFormatPlugin()


def _new_matches(selector: str) -> List[QueryMatch]:
    """Run ``selector`` through the ported engine's entry point."""

    document = _PLUGIN.parse_document(_SOURCE)
    return TreeQueryEngine(document, _PLUGIN).query(selector)


def _legacy_matches(selector: str) -> list:
    """Run the identical ``selector`` through the unchanged legacy executor."""

    return query_source(_SOURCE, selector)


def _new_shape(matches: List[QueryMatch]) -> List[Tuple[str, str]]:
    """``(type, kind)`` multiset from the ported engine's own ``QueryMatch``
    records -- ``type`` is already namespace-qualified (``python:...``)."""

    return sorted((m.type, m.kind) for m in matches)


def _legacy_shape(matches: list) -> List[Tuple[str, str]]:
    """Namespace-normalized ``(type, kind)`` multiset from the legacy engine.

    The legacy ``Match.node_type`` is the bare LibCST class name (e.g.
    ``FunctionDef``); the ported ``QueryMatch.type`` is namespace-qualified
    (``python:FunctionDef``), per the port's documented node-kind contract.
    Prefixing the legacy type here is the one normalization this file
    applies -- everything else is compared as given.
    """

    return sorted((f"python:{m.node_type}", m.kind) for m in matches)


def _assert_same_outcome(selector: str, *, expected_legacy_names: List[str]) -> None:
    """Assert the ported and legacy engines agree on one selector's outcome.

    Agreement is checked on: match count, the namespace-normalized
    ``(type, kind)`` multiset (see :func:`_new_shape`/:func:`_legacy_shape`),
    and that the legacy engine's own matched names are exactly
    ``expected_legacy_names`` -- ground truth confirming the fixture/selector
    identify the intended constructs (see the module docstring for why the
    ported side's ``QueryMatch.name`` is not asserted here).
    """

    new = _new_matches(selector)
    legacy = _legacy_matches(selector)

    assert len(new) == len(legacy), (selector, new, legacy)
    assert _new_shape(new) == _legacy_shape(legacy), (
        selector,
        _new_shape(new),
        _legacy_shape(legacy),
    )
    assert sorted(m.name for m in legacy) == sorted(expected_legacy_names), selector


def test_compat_selector_matching_scenarios() -> None:
    """Role-alias and ``Def:*``-wildcard type selectors match identically.

    Covers the four standard semantic roles the ported adapter resolves
    (function/class/method/module) plus the legacy ``"Type:*"`` wildcard
    pattern, per the port's documented "reach namespaced kinds via role
    aliases or Def:*" contract.
    """

    scenarios = [
        ("function", ["standalone", "_private"]),
        ("class", ["Foo", "Empty"]),
        ("method", ["bar", "baz"]),
        ("module", [None]),
        ("Def:*", ["Foo", "bar", "baz", "Empty", "standalone", "_private"]),
    ]
    for selector, expected_names in scenarios:
        _assert_same_outcome(selector, expected_legacy_names=expected_names)


def test_compat_predicate_matching_scenarios() -> None:
    """Predicates on the ``kind`` attribute agree despite its differing shape.

    ``kind`` is the one legacy predicate attribute that also resolves
    without raising on the ported engine for every node (see the module
    docstring). Each pair below was chosen so the *outcome* -- not the raw
    string -- agrees: two real, non-degenerate positive filters (``~=``
    substring shared between a legacy role alias and the corresponding raw
    namespaced kind: "unc" in both "function" and "FunctionDef"; "lass" in
    both "class" and "ClassDef"), one pass-through ``!=`` (a value that can
    never equal either shape, so every real candidate survives on both
    sides), and one negative case per remaining operator (a value that
    matches neither shape, so both engines agree on zero results).
    """

    positive_scenarios = [
        ("function[kind~='unc']", ["standalone", "_private"]),
        ("class[kind~='lass']", ["Foo", "Empty"]),
        ("function[kind!='zzz_never_matches']", ["standalone", "_private"]),
    ]
    for selector, expected_names in positive_scenarios:
        _assert_same_outcome(selector, expected_legacy_names=expected_names)

    negative_selectors = [
        "*[kind~='zzz_never_matches']",
        "function[kind='zzz_never_matches']",
        "function[kind^='zzz_never_matches']",
        "function[kind$='zzz_never_matches']",
    ]
    for selector in negative_selectors:
        _assert_same_outcome(selector, expected_legacy_names=[])


def test_compat_combinator_scenarios() -> None:
    """Descendant and direct-child combinators agree, including a real
    zero-match agreement for ``class > method``.

    ``class > method`` matches nothing on *either* engine for the same
    structural reason: a method's immediate parent, in both the LibCST tree
    and the ported common-tree model, is the class body wrapper (an
    ``IndentedBlock``/equivalent), not the ``ClassDef`` node itself -- this
    is a genuine agreement, not a vacuous one, and is asserted as such
    rather than skipped.
    """

    scenarios = [
        ("class method", ["bar", "baz"]),
        ("class > method", []),
        ("module > class", ["Foo", "Empty"]),
        ("module > function", ["standalone", "_private"]),
    ]
    for selector, expected_names in scenarios:
        _assert_same_outcome(selector, expected_legacy_names=expected_names)


def test_compat_pseudo_selector_scenarios() -> None:
    """``:first``/``:last``/``:nth``/``:not`` narrow the candidate list
    identically on both engines.

    The ``:not(...)`` cases use the same ``kind~=`` substring trick as the
    predicate category: one predicate that matches every ``function``-role
    candidate on both engines (full exclusion, agreeing at zero), and one
    that matches none (no-op exclusion, agreeing at the unfiltered count).
    """

    scenarios = [
        ("function:first", ["standalone"]),
        ("function:last", ["_private"]),
        ("function:nth(0)", ["standalone"]),
        ("function:not(*[kind~='unc'])", []),
        ("class method:not(*[kind~='zzz_never_matches'])", ["bar", "baz"]),
    ]
    for selector, expected_names in scenarios:
        _assert_same_outcome(selector, expected_legacy_names=expected_names)


def test_compat_malformed_selector_raises_identical_exception() -> None:
    """A malformed selector raises the identical ``QueryParseError`` class
    on both engines -- expected, since both ultimately call the same
    unchanged ``ai_editor.cst_query.parser.parse_selector`` to parse
    selector text; this test guards against a future port accidentally
    wrapping, subclassing, or otherwise renaming that shared exception.
    """

    malformed_selectors = [
        "function[",
        "function:nth()",
        "class >",
        "[name=]bad",
        ":::",
    ]
    for selector in malformed_selectors:
        with pytest.raises(QueryParseError) as legacy_excinfo:
            parse_selector(selector)
        assert type(legacy_excinfo.value) is QueryParseError, selector

        with pytest.raises(QueryParseError) as new_excinfo:
            _new_matches(selector)
        assert type(new_excinfo.value) is QueryParseError, selector

        # Not merely "both raise QueryParseError" (a subclass would satisfy
        # that too) -- the identical class object, so a caller migrating
        # from the legacy engine observes no change in exception type.
        assert type(legacy_excinfo.value) is type(new_excinfo.value)
