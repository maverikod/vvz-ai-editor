"""
Insert operations for CST module patching.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from ...cst_query import query_source
from .blocks import list_cst_blocks
from ..exceptions import CSTModulePatchError
from .models import BlockInfo, InsertOp, Selector
from .patcher import _parse_node_id, _parse_snippet_as_module_body
from .utils import move_module_imports_to_top


class _InsertRewriter(cst.CSTTransformer):
    """Rewriter that inserts statements before/after target nodes."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        insert_before: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        insert_after: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        insert_at_end: list[cst.BaseStatement],
    ):
        self._insert_before = insert_before
        self._insert_after = insert_after
        self._insert_at_end = insert_at_end

    def _find_insertion_point(
        self, body: list[cst.BaseStatement], target_span: tuple[int, int, int, int]
    ) -> int:
        """Find index in body where target_span node is located."""
        for i, stmt in enumerate(body):
            pos = self.get_metadata(PositionProvider, stmt, None)
            if pos is None:
                continue
            span = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)
            if span == target_span:
                return i
        return -1

    def _span_contains_or_matches(
        self,
        node_span: tuple[int, int, int, int],
        target_span: tuple[int, int, int, int],
    ) -> bool:
        """
        Check if node_span contains or exactly matches target_span.

        This handles cases where target_span is for a BaseSmallStatement inside
        a SimpleStatementLine - we check if the SimpleStatementLine contains it.
        """
        # Exact match
        if node_span == target_span:
            return True

        # Check if node_span contains target_span
        node_sl, node_sc, node_el, node_ec = node_span
        target_sl, target_sc, target_el, target_ec = target_span

        # Target starts after or at node start, and ends before or at node end
        if target_sl > node_sl or (target_sl == node_sl and target_sc >= node_sc):
            if target_el < node_el or (target_el == node_el and target_ec <= node_ec):
                return True

        return False

    def _rewrite_body_with_insertions(
        self, original_body: list[cst.BaseStatement]
    ) -> list[cst.BaseStatement]:
        """Rewrite body with insertions."""
        new_body: list[cst.BaseStatement] = []

        # Process insertions before/after specific nodes
        for i, stmt in enumerate(original_body):
            pos = self.get_metadata(PositionProvider, stmt, None)
            if pos is None:
                new_body.append(stmt)
                continue

            span = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)

            # Check for insertions before/after this node (exact match or contains)
            matched_before = None
            matched_after = None

            for target_span, stmts in self._insert_before.items():
                if self._span_contains_or_matches(span, target_span):
                    matched_before = stmts
                    break

            for target_span, stmts in self._insert_after.items():
                if self._span_contains_or_matches(span, target_span):
                    matched_after = stmts
                    break

            # Insert before this node
            if matched_before:
                new_body.extend(matched_before)

            # Add original node
            new_body.append(stmt)

            # Insert after this node
            if matched_after:
                new_body.extend(matched_after)

        # Add insertions at the end
        new_body.extend(self._insert_at_end)

        return new_body

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        return updated_node.with_changes(
            body=self._rewrite_body_with_insertions(list(original_node.body))
        )

    def leave_IndentedBlock(
        self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
    ) -> cst.IndentedBlock:
        return updated_node.with_changes(
            body=self._rewrite_body_with_insertions(list(original_node.body))
        )


def apply_insert_ops(source: str, ops: list[InsertOp]) -> tuple[str, dict[str, Any]]:
    """
    Apply insert operations to add new nodes.

    Args:
        source: Source code
        ops: List of insert operations

    Returns:
        (new_source, stats)
    """
    if not source.strip():
        raise CSTModulePatchError(
            "Cannot insert into empty source; use create operation instead"
        )

    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    blocks = list_cst_blocks(source)
    blocks_by_id = {b.block_id: b for b in blocks}
    blocks_by_kind_name: dict[tuple[str, str], BlockInfo] = {
        (b.kind, b.qualname): b for b in blocks
    }

    insert_before: dict[tuple[int, int, int, int], list[cst.BaseStatement]] = {}
    insert_after: dict[tuple[int, int, int, int], list[cst.BaseStatement]] = {}
    insert_at_end: list[cst.BaseStatement] = []

    inserted = 0
    unmatched: list[Selector] = []

    for op in ops:
        new_stmts = _parse_snippet_as_module_body(op.new_code)
        if not new_stmts:
            continue

        # If no selector, insert at end
        if op.selector is None:
            insert_at_end.extend(new_stmts)
            inserted += len(new_stmts)
            continue

        sel = op.selector
        target: BlockInfo | None = None
        span_key: tuple[int, int, int, int] | None = None

        # Find target node
        if sel.kind == "block_id" and sel.block_id:
            target = blocks_by_id.get(sel.block_id)
            if target:
                span_key = (target.start_line, 0, target.end_line, 0)
        elif sel.kind in ("function", "class") and sel.name:
            target = blocks_by_kind_name.get((sel.kind, sel.name))
            if target:
                span_key = (target.start_line, 0, target.end_line, 0)
        elif sel.kind == "method" and sel.name:
            target = blocks_by_kind_name.get(("method", sel.name))
            if target:
                span_key = (target.start_line, 0, target.end_line, 0)
        elif sel.kind == "node_id" and sel.node_id:
            _, span_key = _parse_node_id(sel.node_id)
        elif sel.kind == "cst_query" and sel.query:
            matches = query_source(source, sel.query, include_code=False)
            if matches:
                idx = sel.match_index if sel.match_index is not None else 0
                if 0 <= idx < len(matches):
                    m = matches[idx]
                    span_key = (m.start_line, m.start_col, m.end_line, m.end_col)
        elif (
            sel.kind == "range"
            and sel.start_line is not None
            and sel.end_line is not None
        ):
            start_col = sel.start_col if sel.start_col is not None else 0
            end_col = sel.end_col if sel.end_col is not None else 0
            span_key = (sel.start_line, start_col, sel.end_line, end_col)

        if span_key is None:
            unmatched.append(sel)
            continue

        # Insert before or after
        if op.position == "before":
            if span_key not in insert_before:
                insert_before[span_key] = []
            insert_before[span_key].extend(new_stmts)
        else:  # "after" or "end"
            if span_key not in insert_after:
                insert_after[span_key] = []
            insert_after[span_key].extend(new_stmts)

        inserted += len(new_stmts)

    patched = wrapper.visit(
        _InsertRewriter(
            insert_before=insert_before,
            insert_after=insert_after,
            insert_at_end=insert_at_end,
        )
    )
    patched = move_module_imports_to_top(patched)
    new_source = patched.code

    stats = {
        "inserted": inserted,
        "unmatched": [
            {
                "kind": s.kind if s else None,
                "name": s.name if s else None,
                "start_line": s.start_line if s else None,
                "start_col": s.start_col if s else None,
                "end_line": s.end_line if s else None,
                "end_col": s.end_col if s else None,
                "block_id": s.block_id if s else None,
                "node_id": s.node_id if s else None,
                "query": s.query if s else None,
                "match_index": s.match_index if s else None,
            }
            for s in unmatched
        ],
    }
    return new_source, stats
