"""
TreeQuery — structural search returning integer short_ids (C-018).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Union

from ai_editor.tree.contracts import NodeId, validate_short_id
from ai_editor.tree.cst_query_selector import (
    CstQuerySelector,
    CstQuerySelectorError,
)


class QueryMode(str, Enum):
    SIMPLE = "simple"
    XPATH = "xpath"


@dataclass(frozen=True)
class TreeQueryMatch:
    short_id: NodeId
    source_text: Optional[str] = None  # set when include_code and Python


@dataclass(frozen=True)
class NoMatch:
    message: str = "no nodes matched query"


@dataclass(frozen=True)
class NonUniqueMatch:
    candidates: List[NodeId]
    message: str = "query matched multiple nodes"


RequireOneResult = Union[TreeQueryMatch, NoMatch, NonUniqueMatch]


class TreeQueryError(ValueError):
    """Invalid query parameters or unsupported filter combination."""


@dataclass(frozen=True)
class TreeQueryFilters:
    node_type: Optional[str] = None
    name: Optional[str] = None
    qualified_name: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None


def _is_python_format(source_path: Path) -> bool:
    return source_path.suffix.lower() == ".py"


def _validated_node_id(value: NodeId) -> NodeId:
    return validate_short_id(int(value))


def _matches_from_metadata(
    metadata_list: Sequence[Any],
    short_id_mapper: Callable[[Any], NodeId],
    *,
    include_code: bool,
    is_python: bool,
) -> List[TreeQueryMatch]:
    matches: List[TreeQueryMatch] = []
    seen: set[NodeId] = set()
    for meta in metadata_list:
        sid = _validated_node_id(short_id_mapper(meta))
        if sid in seen:
            continue
        seen.add(sid)
        source_text: Optional[str] = None
        if include_code and is_python:
            source_text = getattr(meta, "code", None)
        matches.append(TreeQueryMatch(short_id=sid, source_text=source_text))
    return matches


def _code_by_short_id_from_xpath(
    tree_id: str,
    selector: str,
    short_id_mapper: Callable[[Any], NodeId],
) -> dict[NodeId, Optional[str]]:
    from ai_editor.core.cst_tree.tree_finder import find_nodes

    metadata_list = find_nodes(
        tree_id,
        query=selector,
        search_type="xpath",
        include_code=True,
    )
    result: dict[NodeId, Optional[str]] = {}
    for meta in metadata_list:
        sid = _validated_node_id(short_id_mapper(meta))
        if sid not in result:
            result[sid] = getattr(meta, "code", None)
    return result


class TreeQuery:
    def __init__(
        self,
        *,
        tree_loader: Callable[[Path, Optional[str]], Any],
        short_id_mapper: Callable[[Any], NodeId],
    ) -> None:
        self._tree_loader = tree_loader
        self._short_id_mapper = short_id_mapper

    def search(
        self,
        *,
        source_path: Path,
        mode: QueryMode,
        filters: Optional[TreeQueryFilters] = None,
        selector: Optional[str] = None,
        session_id: Optional[str] = None,
        include_code: bool = False,
        require_one: bool = False,
    ) -> Union[List[TreeQueryMatch], RequireOneResult]:
        tree = self._tree_loader(source_path, session_id)
        is_python = _is_python_format(source_path)

        if mode == QueryMode.SIMPLE:
            matches = self._search_simple(
                tree,
                source_path=source_path,
                filters=filters,
                include_code=include_code,
                is_python=is_python,
            )
        elif mode == QueryMode.XPATH:
            matches = self._search_xpath(
                tree,
                source_path=source_path,
                selector=selector,
                include_code=include_code,
                is_python=is_python,
            )
        else:
            raise TreeQueryError(f"unsupported query mode: {mode!r}")

        if require_one:
            return self._apply_require_one(matches)
        return matches

    def _search_simple(
        self,
        tree: Any,
        *,
        source_path: Path,
        filters: Optional[TreeQueryFilters],
        include_code: bool,
        is_python: bool,
    ) -> List[TreeQueryMatch]:
        active = filters or TreeQueryFilters()
        if (
            active.start_line is not None or active.end_line is not None
        ) and not is_python:
            raise TreeQueryError("line range filters are Python only")

        tree_id = getattr(tree, "tree_id", None)
        if not tree_id:
            raise TreeQueryError("simple search requires a tree with tree_id")

        from ai_editor.core.cst_tree.tree_finder import find_nodes

        metadata_list = find_nodes(
            str(tree_id),
            search_type="simple",
            node_type=active.node_type,
            name=active.name,
            qualname=active.qualified_name,
            start_line=active.start_line,
            end_line=active.end_line,
            include_code=include_code and is_python,
        )
        return _matches_from_metadata(
            metadata_list,
            self._short_id_mapper,
            include_code=include_code,
            is_python=is_python,
        )

    def _search_xpath(
        self,
        tree: Any,
        *,
        source_path: Path,
        selector: Optional[str],
        include_code: bool,
        is_python: bool,
    ) -> List[TreeQueryMatch]:
        try:
            sel = CstQuerySelector.parse(selector or "")
        except CstQuerySelectorError:
            raise

        short_ids = sel.evaluate(tree, short_id_mapper=self._short_id_mapper)
        validated_ids = [_validated_node_id(sid) for sid in short_ids]

        if include_code and is_python:
            tree_id = getattr(tree, "tree_id", None)
            if tree_id:
                code_by_sid = _code_by_short_id_from_xpath(
                    str(tree_id),
                    sel.selector,
                    self._short_id_mapper,
                )
                return [
                    TreeQueryMatch(
                        short_id=sid,
                        source_text=code_by_sid.get(sid),
                    )
                    for sid in validated_ids
                ]

        return [TreeQueryMatch(short_id=sid) for sid in validated_ids]

    @staticmethod
    def _apply_require_one(
        matches: List[TreeQueryMatch],
    ) -> RequireOneResult:
        if len(matches) == 0:
            return NoMatch()
        if len(matches) == 1:
            return matches[0]
        return NonUniqueMatch(
            candidates=[match.short_id for match in matches],
        )
