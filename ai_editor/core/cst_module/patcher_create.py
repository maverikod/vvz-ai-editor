"""
Create operations for CST module patching.

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
from .models import BlockInfo, CreateOp, Selector
from .patcher import _parse_node_id, _parse_snippet_as_module_body
from .utils import move_module_imports_to_top


class _CreateRewriter(cst.CSTTransformer):
    """Rewriter that creates new nodes at specified positions."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        create_after: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        create_before: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        create_at_end: list[cst.BaseStatement],
        create_at_end_of_class: dict[
            tuple[int, int, int, int], list[cst.BaseStatement]
        ],
        create_at_end_of_function: dict[
            tuple[int, int, int, int], list[cst.BaseStatement]
        ],
    ):
        self._create_after = create_after
        self._create_before = create_before
        self._create_at_end = create_at_end
        self._create_at_end_of_class = create_at_end_of_class
        self._create_at_end_of_function = create_at_end_of_function

    def _rewrite_body_with_creations(
        self, original_body: list[cst.BaseStatement]
    ) -> list[cst.BaseStatement]:
        """Rewrite body with creations."""
        new_body: list[cst.BaseStatement] = []

        for stmt in original_body:
            pos = self.get_metadata(PositionProvider, stmt, None)
            if pos is None:
                new_body.append(stmt)
                continue

            span = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)

            # Create before this node
            if span in self._create_before:
                new_body.extend(self._create_before[span])

            # Add original node
            new_body.append(stmt)

            # Create after this node
            if span in self._create_after:
                new_body.extend(self._create_after[span])

            # Create at end of class/function
            if isinstance(stmt, cst.ClassDef) and span in self._create_at_end_of_class:
                # Need to modify the class body
                if isinstance(stmt.body, cst.IndentedBlock):
                    new_body[-1] = stmt.with_changes(
                        body=stmt.body.with_changes(
                            body=list(stmt.body.body)
                            + self._create_at_end_of_class[span]
                        )
                    )
            # NOTE:
            # This project pins a LibCST build where async functions are represented
            # as `cst.FunctionDef` with an `asynchronous` modifier, and the
            # top-level `cst.AsyncFunctionDef` node does not exist.
            elif (
                isinstance(stmt, cst.FunctionDef)
                and span in self._create_at_end_of_function
            ):
                # Need to modify the function body
                if isinstance(stmt.body, cst.IndentedBlock):
                    new_body[-1] = stmt.with_changes(
                        body=stmt.body.with_changes(
                            body=list(stmt.body.body)
                            + self._create_at_end_of_function[span]
                        )
                    )

        # Add creations at the end
        new_body.extend(self._create_at_end)

        return new_body

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        return updated_node.with_changes(
            body=self._rewrite_body_with_creations(list(original_node.body))
        )


def apply_create_ops(source: str, ops: list[CreateOp]) -> tuple[str, dict[str, Any]]:
    """
    Apply create operations to add new nodes.

    Args:
        source: Source code (can be empty for end_of_module)
        ops: List of create operations

    Returns:
        (new_source, stats)
    """
    # Handle empty source - create module from scratch
    if not source.strip():
        # Only allow end_of_module for empty source
        for op in ops:
            if op.position != "end_of_module":
                raise CSTModulePatchError(
                    "Cannot create nodes at specific positions in empty source; "
                    "use position='end_of_module' or provide existing source"
                )

        # Create module with all new nodes
        new_stmts: list[cst.BaseStatement] = []
        for op in ops:
            if op.position == "end_of_module":
                new_stmts.extend(_parse_snippet_as_module_body(op.new_code))

        if not new_stmts:
            raise CSTModulePatchError("No nodes to create")

        new_module = cst.Module(body=new_stmts)
        new_module = move_module_imports_to_top(new_module)

        stats = {
            "created": len(new_stmts),
            "unmatched": [],
        }
        return (new_module.code, stats)

    # Normal path: create in existing source
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    blocks = list_cst_blocks(source)
    blocks_by_id = {b.block_id: b for b in blocks}
    blocks_by_kind_name: dict[tuple[str, str], BlockInfo] = {
        (b.kind, b.qualname): b for b in blocks
    }

    create_after: dict[tuple[int, int, int, int], list[cst.BaseStatement]] = {}
    create_before: dict[tuple[int, int, int, int], list[cst.BaseStatement]] = {}
    create_at_end: list[cst.BaseStatement] = []
    create_at_end_of_class: dict[tuple[int, int, int, int], list[cst.BaseStatement]] = (
        {}
    )
    create_at_end_of_function: dict[
        tuple[int, int, int, int], list[cst.BaseStatement]
    ] = {}

    created = 0
    unmatched: list[Selector] = []

    for op in ops:
        new_stmts = _parse_snippet_as_module_body(op.new_code)
        if not new_stmts:
            continue

        # Handle end_of_module
        if op.position == "end_of_module":
            create_at_end.extend(new_stmts)
            created += len(new_stmts)
            continue

        # Need selector for other positions
        if op.selector is None:
            unmatched.append(None)
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

        # Route to appropriate dict based on position
        if op.position == "after_selector":
            if span_key not in create_after:
                create_after[span_key] = []
            create_after[span_key].extend(new_stmts)
        elif op.position == "before_selector":
            if span_key not in create_before:
                create_before[span_key] = []
            create_before[span_key].extend(new_stmts)
        elif op.position == "end_of_class":
            if target and target.kind == "class":
                if span_key not in create_at_end_of_class:
                    create_at_end_of_class[span_key] = []
                create_at_end_of_class[span_key].extend(new_stmts)
            else:
                unmatched.append(sel)
                continue
        elif op.position == "end_of_function":
            if target and target.kind in ("function", "method"):
                if span_key not in create_at_end_of_function:
                    create_at_end_of_function[span_key] = []
                create_at_end_of_function[span_key].extend(new_stmts)
            else:
                unmatched.append(sel)
                continue
        else:
            raise CSTModulePatchError(f"Unsupported create position: {op.position}")

        created += len(new_stmts)

    patched = wrapper.visit(
        _CreateRewriter(
            create_after=create_after,
            create_before=create_before,
            create_at_end=create_at_end,
            create_at_end_of_class=create_at_end_of_class,
            create_at_end_of_function=create_at_end_of_function,
        )
    )
    patched = move_module_imports_to_top(patched)
    new_source = patched.code

    stats = {
        "created": created,
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
