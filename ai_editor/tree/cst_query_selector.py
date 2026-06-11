"""
CstQuerySelector — XPath-compatible tree query selector (C-019).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, List, Sequence

from ai_editor.cst_query.parser import parse_selector
from ai_editor.core.exceptions import QueryParseError
from ai_editor.tree.contracts import NodeId

_UUID_NODE_REF = re.compile(r"[0-9a-f-]{36}", re.IGNORECASE)


class CstQuerySelectorError(ValueError):
    """Malformed or unsupported selector string."""


@dataclass(frozen=True)
class CstQuerySelector:
    selector: str

    @classmethod
    def parse(cls, raw: str) -> CstQuerySelector:
        if not isinstance(raw, str):
            raise CstQuerySelectorError("selector must be a non-empty string")
        stripped = raw.strip()
        if not stripped:
            raise CstQuerySelectorError("selector must be a non-empty string")
        if _UUID_NODE_REF.search(stripped):
            raise CstQuerySelectorError(
                "selector must not contain UUID node references"
            )

        try:
            parse_selector(stripped)
        except QueryParseError as exc:
            raise CstQuerySelectorError(str(exc)) from exc

        return cls(selector=stripped)

    def evaluate(
        self,
        tree: Any,
        *,
        short_id_mapper: Callable[[Any], NodeId],
    ) -> List[NodeId]:
        engine_matches = self._run_engine(tree)
        seen: set[NodeId] = set()
        result: List[NodeId] = []
        for match in engine_matches:
            sid = short_id_mapper(match)
            if sid not in seen:
                seen.add(sid)
                result.append(sid)
        return result

    def _run_engine(self, tree: Any) -> Sequence[Any]:
        if hasattr(tree, "tree_id"):
            from ai_editor.core.cst_tree.tree_finder import find_nodes

            return find_nodes(
                tree.tree_id,
                query=self.selector,
                search_type="xpath",
            )

        module = getattr(tree, "module", None)
        node_ids_by_exact_key = getattr(tree, "node_ids_by_exact_key", None)
        if module is not None and node_ids_by_exact_key is not None:
            from ai_editor.cst_query.executor import query_source

            return query_source(
                module.code,
                self.selector,
                include_code=False,
                node_ids_by_exact_key=node_ids_by_exact_key,
            )

        raise ValueError(
            "tree must expose tree_id or module/node_ids_by_exact_key attributes"
        )
