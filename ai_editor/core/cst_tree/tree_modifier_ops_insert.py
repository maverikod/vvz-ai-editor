"""
Insert nodes into CST module (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import logging

from typing import List, Optional, Union, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider


from .models import CSTTree
from .node_stable_id import get_stable_id

from .tree_modifier_ops_find import resolve_insert_parent_node

from .tree_modifier_ops_parse import (
    parse_code_snippet_for_insert,
    parse_code_snippet_or_comment,
)


logger = logging.getLogger(__name__)


def _count_leading_blank_lines(raw: str) -> int:
    """Count empty lines before the first non-empty line in a snippet."""
    n_leading_blanks = 0
    for ln in raw.splitlines():
        if ln.strip() == "":
            n_leading_blanks += 1
        else:
            break
    return n_leading_blanks


def _count_blank_leading_lines_on_statement(stmt: cst.CSTNode) -> int:
    """Count leading EmptyLine nodes without comments on a definitional statement."""
    if not isinstance(stmt, (cst.FunctionDef, cst.ClassDef)):
        return 0
    n = 0
    for el in stmt.leading_lines:
        if el.comment is not None:
            break
        n += 1
    return n


def _apply_insert_leading_blank_lines(
    statements: List[Union[cst.BaseStatement, cst.EmptyLine]],
    raw_code: str,
) -> List[Union[cst.BaseStatement, cst.EmptyLine]]:
    """
    Attach leading empty lines from the snippet onto the first FunctionDef/ClassDef.

    Parsed modules drop module-level EmptyLine nodes; blank separation belongs on
    ``leading_lines`` of the first definitional statement instead.
    """
    n_leading_blanks = _count_leading_blank_lines(raw_code)
    if n_leading_blanks <= 0 or not statements:
        return statements

    stmt_list: List[Union[cst.BaseStatement, cst.EmptyLine]] = [
        s for s in statements if not isinstance(s, cst.EmptyLine)
    ]
    if not stmt_list:
        return statements

    first = stmt_list[0]
    if not isinstance(first, (cst.FunctionDef, cst.ClassDef)):
        return stmt_list

    existing_blank = _count_blank_leading_lines_on_statement(first)
    to_add = max(0, n_leading_blanks - existing_blank)
    if to_add <= 0:
        return stmt_list

    extra = [cst.EmptyLine()] * to_add
    stmt_list[0] = first.with_changes(
        leading_lines=list(extra) + list(first.leading_lines)
    )
    return stmt_list


def insert_node_at_position(
    module: cst.Module,
    tree: CSTTree,
    parent_node_id: str,
    new_code: str,
    position: str = "last",
    position_after_index: Optional[int] = None,
    parsed_statements: Optional[List[cst.BaseStatement]] = None,
) -> cst.Module:
    """
    Insert one or more nodes at a precise index in parent's body.

    position: "first" (index 0), "last" (append), or "after" (after sibling at position_after_index).
    If position is "after" and position_after_index is out of range, treat as last.
    Resolves parent from current module by position when possible (batch insert).
    Supports: Module, IndentedBlock, or any compound statement whose body is IndentedBlock
    (FunctionDef, ClassDef, If, For, While, With, Try, ExceptHandler, Else, Finally, MatchCase).
    Does NOT support: SimpleStatementSuite (one-liners), Match (use MatchCase instead).
    """
    parent_node = resolve_insert_parent_node(module, tree, parent_node_id)
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    if parsed_statements is not None:
        new_statements = cast(
            List[Union[cst.BaseStatement, cst.EmptyLine]], parsed_statements
        )
    else:
        new_statements = parse_code_snippet_for_insert(
            tree, parent_node_id, code=new_code
        )
        new_statements = _apply_insert_leading_blank_lines(new_statements, new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    if isinstance(parent_node, cst.Module):
        body = list(parent_node.body)
    elif isinstance(parent_node, cst.IndentedBlock):
        body = list(parent_node.body)  # type: ignore[arg-type]
    elif isinstance(parent_node, cst.SimpleStatementSuite):
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"is a one-liner block (SimpleStatementSuite). "
            f"Expand the block to IndentedBlock first, then insert."
        )
    elif isinstance(parent_node, cst.Match):
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"is a Match statement. Use MatchCase node as parent_node_id instead."
        )
    elif hasattr(parent_node, "body") and isinstance(
        getattr(parent_node, "body", None), cst.IndentedBlock
    ):
        body = list(parent_node.body.body)  # type: ignore[arg-type]
    else:
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"has no insertable statement body. "
            f"Supported: Module, IndentedBlock, or any node whose body is IndentedBlock."
        )

    pos = position.strip().lower()
    if pos == "first":
        insert_index = 0
    elif pos == "after" and position_after_index is not None:
        insert_index = min(position_after_index + 1, len(body))
    else:
        insert_index = len(body)

    new_body = body[:insert_index] + list(new_statements) + body[insert_index:]

    class PositionInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_parent: cst.CSTNode,
            replacement_body: list[cst.BaseStatement],
        ):
            self.target_parent = target_parent
            self.replacement_body = replacement_body
            self.done = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def leave_FunctionDef(
            self,
            original_node: cst.FunctionDef,
            updated_node: cst.FunctionDef,
        ) -> cst.FunctionDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            updated_node = super().on_leave(original_node, updated_node)
            if original_node is self.target_parent and not self.done:
                body_attr = getattr(updated_node, "body", None)
                if isinstance(body_attr, cst.IndentedBlock):
                    self.done = True
                    return updated_node.with_changes(
                        body=body_attr.with_changes(body=self.replacement_body)
                    )
            return updated_node

    inserter = PositionInserter(parent_node, cast(list, new_body))
    result = module.visit(inserter)
    if not inserter.done:
        raise ValueError(f"Nodes were not inserted into parent {parent_node_id}")
    return result


def insert_node(
    module: cst.Module, tree: CSTTree, parent_node_id: str, new_code: str, position: str
) -> cst.Module:
    """Insert one or more nodes into module (used when target_node_id is set)."""
    parent_node = tree.node_map.get(parent_node_id)
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    # Parse new code (supports multi-line); allow comment-only (EmptyLine with Comment)
    new_statements = parse_code_snippet_for_insert(tree, parent_node_id, code=new_code)
    new_statements = _apply_insert_leading_blank_lines(new_statements, new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    # Use LibCST transformer to insert the nodes
    class NodeInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_parent: cst.CSTNode,
            new_statements: list[cst.BaseStatement],
            position: str,
        ):
            self.target_parent = target_parent
            self.new_statements = new_statements
            self.position = position
            self.inserted = False

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self.target_parent:
                # Insert nodes into parent's body
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    if isinstance(updated_node.body, cst.IndentedBlock):
                        body_list: list[cst.BaseStatement] = list(
                            updated_node.body.body
                        )
                        if self.position == "before":
                            body_list = list(self.new_statements) + body_list
                        else:  # after
                            body_list = body_list + list(self.new_statements)
                        self.inserted = True
                        return updated_node.with_changes(
                            body=cst.IndentedBlock(body=body_list)
                        )
                elif isinstance(updated_node, cst.Module):
                    # Insert at module level
                    body_list = list(updated_node.body)
                    if self.position == "before":
                        body_list = list(self.new_statements) + body_list
                    else:  # after
                        body_list = body_list + list(self.new_statements)
                    self.inserted = True
                    return updated_node.with_changes(body=body_list)
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions
            if original_node is self.target_parent:
                body_list: list[cst.BaseStatement] = list(updated_node.body)
                if self.position == "before":
                    body_list = list(self.new_statements) + body_list
                else:  # after
                    body_list = body_list + list(self.new_statements)
                self.inserted = True
                return updated_node.with_changes(body=body_list)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level insertions
            # Check if this block's parent is the target parent
            # This handles cases where we insert into nested blocks
            # The actual insertion is handled in on_leave for FunctionDef/ClassDef
            # But we also need to handle direct IndentedBlock insertions
            return updated_node

    inserter = NodeInserter(parent_node, cast(list, new_statements), position)
    result = module.visit(inserter)
    if not inserter.inserted:
        raise ValueError(f"Nodes were not inserted into {parent_node_id}")
    return result


def insert_node_relative(
    module: cst.Module,
    tree: CSTTree,
    target_node_id: str,
    parent_node_id: str,
    new_code: str,
    position: str,
) -> cst.Module:
    """Insert nodes before/after a target node in its parent's body.

    The target_node_id is automatically normalized: if it points to a node
    that is not a direct child of the body (e.g. Import inside SimpleStatementLine,
    or Name inside FunctionDef), we walk up parent_id in metadata_map until we
    find an ancestor that IS a direct statement-level child of some body.
    This means callers never need to manually pick the 'right level' — any
    node_id from anywhere in the subtree works correctly.
    """
    # ── 1. Resolve stale UUIDs via aliases ──────────────────────────────────
    resolved_target = tree.node_id_aliases.get(target_node_id, target_node_id)
    target_metadata = tree.metadata_map.get(resolved_target) or tree.metadata_map.get(
        target_node_id
    )
    if target_metadata is None:
        raise ValueError(f"Target node not found: {target_node_id}")

    # ── 2. Build module positions once ──────────────────────────────────────
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    # ── 3. Helper: get body list from any container node ────────────────────
    def _get_body(node: cst.CSTNode) -> Optional[list]:
        if isinstance(node, cst.Module):
            return list(node.body)
        if isinstance(node, cst.IndentedBlock):
            return list(node.body)
        body_attr = getattr(node, "body", None)
        if isinstance(body_attr, cst.IndentedBlock):
            return list(body_attr.body)
        return None

    # ── 4. Resolve parent node ───────────────────────────────────────────────
    resolved_parent = tree.node_id_aliases.get(parent_node_id, parent_node_id)
    parent_metadata = tree.metadata_map.get(resolved_parent) or tree.metadata_map.get(
        parent_node_id
    )
    parent_node: Optional[cst.CSTNode] = None
    parent_node = resolve_insert_parent_node(module, tree, resolved_parent)
    if parent_node is None:
        parent_node = tree.node_map.get(resolved_parent) or tree.node_map.get(
            parent_node_id
        )
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    body = _get_body(parent_node)
    if body is None:
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            "has no insertable statement body."
        )

    # ── 5. Normalize target to statement level ───────────────────────────────
    # Prefer stable_id on body FunctionDef/ClassDef (metadata positions can be stale
    # after embed_stable_ids_into_tree replaces tree.module without re-indexing).
    def _find_in_body_by_stable(stable_id: Optional[str]) -> int:
        if not stable_id:
            return -1
        for i, stmt in enumerate(body):
            if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)):
                stmt_stable = get_stable_id(stmt)
                if stmt_stable and stmt_stable == stable_id:
                    return i
        return -1

    def _find_in_body_by_position(meta_start_line: int, meta_start_col: int) -> int:
        """Return index of body element whose fresh CST position matches, or -1."""
        for i, stmt in enumerate(body):
            pos = positions.get(stmt)
            if pos is None:
                continue
            if pos.start.line == meta_start_line and pos.start.column == meta_start_col:
                return i
        return -1

    # Start from the given target and walk up until we hit the body level
    current_meta = target_metadata
    target_index = -1
    while current_meta is not None:
        target_index = _find_in_body_by_stable(current_meta.stable_id)
        if target_index < 0:
            target_index = _find_in_body_by_position(
                current_meta.start_line, current_meta.start_col
            )
        if target_index >= 0:
            break
        # Not found at this level — go one level up
        parent_id_up = current_meta.parent_id
        if parent_id_up is None:
            break
        current_meta = tree.metadata_map.get(parent_id_up)
        if current_meta is None:
            break
        # Stop only when we have walked above the parent body container.
        # resolved_parent is the container whose body we search; stopping there
        # is premature before the target statement is found.
        parent_of_container_id = None
        if resolved_parent:
            container_meta = tree.metadata_map.get(resolved_parent)
            if container_meta is not None:
                parent_of_container_id = container_meta.parent_id
        if parent_of_container_id and current_meta.node_id == parent_of_container_id:
            break

    if target_index < 0:
        parent_type = type(parent_node).__name__
        raise ValueError(
            f"Cannot find target node {target_node_id} (or any of its ancestors) "
            f"as a direct statement in parent {parent_node_id} ({parent_type}). "
            f"Target type: {target_metadata.type}, "
            f"target position: {target_metadata.start_line}:{target_metadata.start_col}."
        )

    # ── 6. Build new body and apply ─────────────────────────────────────────
    new_statements = parse_code_snippet_for_insert(tree, resolved_parent, code=new_code)
    new_statements = _apply_insert_leading_blank_lines(new_statements, new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    insert_at = target_index if position == "before" else target_index + 1
    new_body = body[:insert_at] + list(new_statements) + body[insert_at:]

    class PositionInserter(cst.CSTTransformer):
        def __init__(self, target_parent: cst.CSTNode, replacement_body: list) -> None:
            self.target_parent = target_parent
            self.replacement_body = replacement_body
            self.done = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.FunctionDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_IndentedBlock(
            self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
        ) -> cst.IndentedBlock:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

    inserter = PositionInserter(parent_node, cast(list, new_body))
    result = module.visit(inserter)
    if not inserter.done:
        raise ValueError(f"Nodes were not inserted into parent {parent_node_id}")
    return result
