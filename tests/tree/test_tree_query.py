"""Unit tests for ai_editor.tree.tree_query (G-004)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.tree.contracts import NodeId
from ai_editor.tree.tree_query import (
    NoMatch,
    NonUniqueMatch,
    QueryMode,
    TreeQuery,
    TreeQueryError,
    TreeQueryFilters,
    TreeQueryMatch,
)


def _make_tree_query() -> TreeQuery:
    def short_id_mapper(meta: object) -> NodeId:
        return NodeId(getattr(meta, "short_id"))

    loader = MagicMock(return_value=SimpleNamespace(tree_id="tree-abc"))
    return TreeQuery(tree_loader=loader, short_id_mapper=short_id_mapper)


@patch("ai_editor.core.cst_tree.tree_finder.find_nodes")
def test_simple_mode_applies_filters(mock_find_nodes: MagicMock) -> None:
    meta = SimpleNamespace(short_id=7, code="def foo(): pass")
    mock_find_nodes.return_value = [meta]
    query = _make_tree_query()

    result = query.search(
        source_path=Path("module.py"),
        mode=QueryMode.SIMPLE,
        filters=TreeQueryFilters(node_type="FunctionDef", name="foo"),
        include_code=True,
    )

    assert result == [TreeQueryMatch(short_id=NodeId(7), source_text="def foo(): pass")]
    mock_find_nodes.assert_called_once_with(
        "tree-abc",
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
        qualname=None,
        start_line=None,
        end_line=None,
        include_code=True,
    )


@patch("ai_editor.core.cst_tree.tree_finder.find_nodes")
def test_require_one_no_match(mock_find_nodes: MagicMock) -> None:
    mock_find_nodes.return_value = []
    query = _make_tree_query()

    result = query.search(
        source_path=Path("module.py"),
        mode=QueryMode.SIMPLE,
        require_one=True,
    )

    assert isinstance(result, NoMatch)


@patch("ai_editor.core.cst_tree.tree_finder.find_nodes")
def test_require_one_single_match(mock_find_nodes: MagicMock) -> None:
    mock_find_nodes.return_value = [SimpleNamespace(short_id=2)]
    query = _make_tree_query()

    result = query.search(
        source_path=Path("module.py"),
        mode=QueryMode.SIMPLE,
        require_one=True,
    )

    assert result == TreeQueryMatch(short_id=NodeId(2))


@patch("ai_editor.core.cst_tree.tree_finder.find_nodes")
def test_require_one_non_unique_match(mock_find_nodes: MagicMock) -> None:
    mock_find_nodes.return_value = [
        SimpleNamespace(short_id=1),
        SimpleNamespace(short_id=2),
    ]
    query = _make_tree_query()

    result = query.search(
        source_path=Path("module.py"),
        mode=QueryMode.SIMPLE,
        require_one=True,
    )

    assert isinstance(result, NonUniqueMatch)
    assert result.candidates == [NodeId(1), NodeId(2)]


def test_line_range_guard_rejects_non_python() -> None:
    query = _make_tree_query()

    with pytest.raises(TreeQueryError, match="Python only"):
        query.search(
            source_path=Path("data.json"),
            mode=QueryMode.SIMPLE,
            filters=TreeQueryFilters(start_line=1, end_line=3),
        )


@patch("ai_editor.tree.tree_query.CstQuerySelector")
def test_xpath_mode_calls_cst_query_selector(mock_selector_cls: MagicMock) -> None:
    mock_selector = MagicMock()
    mock_selector.selector = "//FunctionDef[@name='foo']"
    mock_selector.evaluate.return_value = [NodeId(42)]
    mock_selector_cls.parse.return_value = mock_selector
    query = _make_tree_query()

    result = query.search(
        source_path=Path("module.py"),
        mode=QueryMode.XPATH,
        selector="//FunctionDef[@name='foo']",
    )

    mock_selector_cls.parse.assert_called_once_with("//FunctionDef[@name='foo']")
    mock_selector.evaluate.assert_called_once()
    assert result == [TreeQueryMatch(short_id=NodeId(42))]
