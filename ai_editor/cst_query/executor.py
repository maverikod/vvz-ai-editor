"""
CSTQuery executor for Python source (LibCST).

The executor traverses a LibCST tree, builds a lightweight parent-linked index,
and evaluates a parsed selector against nodes.

This executor prefers persisted UUID4 node identifiers when they are available
from a loaded CST tree or from the file's trailing marker block. It falls back
to the legacy span-based identifier only for raw source that has not been
assigned persisted UUIDs yet.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


from typing import Optional


import libcst as cst


from .ast import Combinator, Predicate, PredicateOp, PseudoKind, Query, SelectorStep

from .index_builder import Match, NodeInfo, build_index, parse_source_for_query

from .parser import parse_selector


def query_source(
    source: str,
    selector: str,
    *,
    include_code: bool = False,
    node_ids_by_exact_key: dict[tuple[int, int, int, int, str], str] | None = None,
) -> list[Match]:
    """
    Query python source using CSTQuery selectors.

    Args:
        source: python module source
        selector: selector string
        include_code: include `code_for_node` snippet for each match (can be large)
    """
    q = parse_selector(selector)
    (
        _logical_source,
        module,
        parents,
        positions,
        persisted_node_ids,
    ) = parse_source_for_query(source)

    nodes = build_index(
        module,
        parents=parents,
        positions=positions,
        persisted_node_ids=persisted_node_ids,
        node_ids_by_exact_key=node_ids_by_exact_key,
    )
    matched = _eval_query(nodes, q)

    out: list[Match] = []
    for info in matched:
        code = module.code_for_node(info.node) if include_code else None
        out.append(
            Match(
                node_id=info.node_id or _legacy_node_id(info),
                kind=info.kind,
                node_type=info.node_type,
                name=info.name,
                qualname=info.qualname,
                start_line=info.start_line,
                start_col=info.start_col,
                end_line=info.end_line,
                end_col=info.end_col,
                code=code,
            )
        )
    return out


def _legacy_node_id(info: NodeInfo) -> str:
    """Fallback ID used only for raw source without persisted UUIDs."""
    q = info.qualname or ""
    return (
        f"{info.kind}:{q}:{info.node_type}:"
        f"{info.start_line}:{info.start_col}-{info.end_line}:{info.end_col}"
    )


def _eval_query(nodes: list[NodeInfo], q: Query) -> list[NodeInfo]:
    parent_map: dict[cst.CSTNode, Optional[cst.CSTNode]] = {
        n.node: n.parent for n in nodes
    }
    current = _apply_step(nodes, q.first)
    for comb, step in q.rest:
        nxt_candidates = _apply_step(nodes, step)
        current = _apply_combinator(
            current, nxt_candidates, comb, parent_map=parent_map
        )
    return current


def _apply_combinator(
    prev: list[NodeInfo],
    nxt: list[NodeInfo],
    comb: Combinator,
    *,
    parent_map: dict[cst.CSTNode, Optional[cst.CSTNode]],
) -> list[NodeInfo]:
    if not prev or not nxt:
        return []
    prev_nodes = {p.node for p in prev}

    if comb == Combinator.CHILD:
        return [n for n in nxt if n.parent in prev_nodes]

    # Descendant (space) and recursive descendant (//): any ancestor match.
    if comb not in (Combinator.DESCENDANT, Combinator.RECURSIVE_DESCENDANT):
        return []
    prev_set = prev_nodes
    out: list[NodeInfo] = []
    for n in nxt:
        p = n.parent
        while p is not None:
            if p in prev_set:
                out.append(n)
                break
            p = parent_map.get(p)
    return out


def _apply_step(nodes: list[NodeInfo], step: SelectorStep) -> list[NodeInfo]:
    matched = [n for n in nodes if _matches_step(n, step)]
    for pseudo in step.pseudos:
        if pseudo.kind == PseudoKind.FIRST:
            matched = matched[:1]
        elif pseudo.kind == PseudoKind.LAST:
            matched = matched[-1:] if matched else []
        elif pseudo.kind == PseudoKind.NTH:
            idx = pseudo.index or 0
            matched = [matched[idx]] if 0 <= idx < len(matched) else []
    return matched


def _matches_step(node: NodeInfo, step: SelectorStep) -> bool:
    if not _matches_node_type(node, step.node_type):
        return False
    for pred in step.predicates:
        if not _matches_predicate(node, pred):
            return False
    # :not(selector) pseudo-class
    if step.not_selector is not None:
        not_matches = _eval_query([node], step.not_selector)
        if not_matches:
            return False
    return True


def _matches_node_type(node: NodeInfo, node_type: str) -> bool:
    if not node_type or node_type == "*":
        return True
    t = node_type.strip()
    # XPath-style modifier: "Def:*" matches FunctionDef, ClassDef; "Function:*" matches FunctionDef
    if t.endswith(":*"):
        part = t[:-2].strip().lower()
        if not part:
            return True
        if part in {
            "module",
            "class",
            "function",
            "method",
            "stmt",
            "smallstmt",
            "import",
            "node",
        }:
            return node.kind == part
        nt = node.node_type.lower()
        return nt.startswith(part) or nt.endswith(part)
    alias = t.lower()
    if alias in {
        "module",
        "class",
        "function",
        "method",
        "stmt",
        "smallstmt",
        "import",
        "node",
    }:
        return node.kind == alias
    return node.node_type.lower() == t.lower()


def _matches_predicate(node: NodeInfo, pred: Predicate) -> bool:
    val = _get_attr(node, pred.attr)
    if val is None:
        return False
    return _compare(str(val), pred.op, pred.value)


def _get_attr(node: NodeInfo, attr: str) -> Optional[str]:
    """Return attribute value for predicate matching. Supports module for ImportFrom."""
    a = attr.lower()
    if a == "type":
        return node.node_type
    if a == "kind":
        return node.kind
    if a == "name":
        return node.name
    if a == "qualname":
        return node.qualname
    if a == "start_line":
        return str(node.start_line)
    if a == "end_line":
        return str(node.end_line)
    if a == "children_count":
        return str(len(getattr(node, "children", None) or []))
    if a == "module" and node.extra_attrs and "module" in node.extra_attrs:
        return node.extra_attrs["module"]
    return None


def _compare(left: str, op: PredicateOp, right: str) -> bool:
    if op == PredicateOp.EQ:
        return left == right
    if op == PredicateOp.NE:
        return left != right
    if op == PredicateOp.CONTAINS:
        return right in left
    if op == PredicateOp.PREFIX:
        return left.startswith(right)
    if op == PredicateOp.SUFFIX:
        return left.endswith(right)
    # Numeric comparisons: GT, LT, GTE, LTE
    if op in (PredicateOp.GT, PredicateOp.LT, PredicateOp.GTE, PredicateOp.LTE):
        try:
            l_num, r_num = int(left), int(right)
        except (ValueError, TypeError):
            return False
        if op == PredicateOp.GT:
            return l_num > r_num
        if op == PredicateOp.LT:
            return l_num < r_num
        if op == PredicateOp.GTE:
            return l_num >= r_num
        if op == PredicateOp.LTE:
            return l_num <= r_num
    return False
