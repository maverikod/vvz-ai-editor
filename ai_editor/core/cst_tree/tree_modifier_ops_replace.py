"""
Replace nodes and ranges in CST module (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, cast

import libcst as cst

from .models import CSTTree
from .tree_modifier_ops_find import (
    delete_node,
    find_leaf_node_in_module_by_position,
    find_node_in_module_by_position,
    resolve_replace_target_to_current_module,
    _resolve_structural_node_from_map,
)
from .tree_modifier_ops_parse import (
    FINE_GRAINED_REPLACE_NODE_TYPES,
    replacement_text_includes_decorators,
    parse_annotation_snippet,
    parse_code_snippet,
    parse_code_snippet_for_def_replace,
    parse_param_snippet,
)
from ai_editor.commands.universal_file_edit.errors import (
    public_edit_operation_remediation,
)


def replace_node(
    module: cst.Module, tree: CSTTree, node_id: str, new_code: str
) -> cst.Module:
    """Replace a node in module with one or more statements or a leaf node."""
    metadata = tree.metadata_map.get(node_id)
    # Resolve target node: prefer node_map for class/function (stable name match),
    # then position lookup for fine-grained leaves and stale module nodes.
    node: Optional[cst.CSTNode] = _resolve_structural_node_from_map(
        tree, node_id, metadata
    )
    if node is None and metadata and hasattr(metadata, "start_line"):
        _resolved_id = tree.node_id_aliases.get(node_id, node_id)
        _cand = tree.node_map.get(_resolved_id) or tree.node_map.get(node_id)
        _use_leaf = (_cand is not None and isinstance(_cand, cst.BaseExpression)) or (
            (getattr(metadata, "type", "") or "") in FINE_GRAINED_REPLACE_NODE_TYPES
        )
        if _use_leaf:
            node = find_leaf_node_in_module_by_position(
                module,
                metadata.start_line,
                metadata.start_col,
                metadata.end_line,
                metadata.end_col,
                preferred_type=metadata.type,
            )
        if node is None:
            node = find_node_in_module_by_position(
                module,
                metadata.start_line,
                metadata.start_col,
                metadata.end_line,
                metadata.end_col,
                preferred_type=metadata.type,
            )
    if node is None:
        node = tree.node_map.get(node_id)
    if not node:
        node_info = (
            f"Node type: {metadata.type if metadata else 'unknown'}, "
            if metadata
            else ""
        )
        available = list(tree.node_map.keys())[:5]
        raise ValueError(
            f"Node not found: {node_id}. {node_info}"
            f"Available nodes (first 5): {available}"
        )

    node = resolve_replace_target_to_current_module(module, node, metadata)

    stripped = new_code.strip()
    if not stripped:
        return delete_node(module, tree, node_id)

    replacements_list: List[cst.CSTNode]
    if isinstance(node, cst.Name):
        replacements_list = [cst.parse_expression(stripped)]
    elif isinstance(node, cst.Param):
        replacements_list = [parse_param_snippet(code=new_code)]
    elif isinstance(node, cst.Annotation):
        replacements_list = [parse_annotation_snippet(code=new_code)]
    elif isinstance(node, cst.BaseExpression):
        try:
            replacements_list = [cst.parse_expression(stripped)]
        except cst.ParserSyntaxError as exc:
            raise ValueError(f"Invalid expression syntax for replace: {exc}") from exc
    elif isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        replacements_list = cast(
            List[cst.CSTNode],
            list(
                parse_code_snippet_for_def_replace(
                    new_code, tree=tree, target_metadata=metadata
                )
            ),
        )
    else:
        replacements_list = cast(List[cst.CSTNode], list(parse_code_snippet(new_code)))

    if (
        len(replacements_list) == 1
        and isinstance(node, (cst.FunctionDef, cst.ClassDef))
        and isinstance(replacements_list[0], (cst.FunctionDef, cst.ClassDef))
        and not replacement_text_includes_decorators(new_code)
    ):
        old_def = node
        new_def = replacements_list[0]
        if old_def.decorators:
            replacements_list = [new_def.with_changes(decorators=old_def.decorators)]

    node_type = metadata.type if metadata else "unknown"
    parent_id = metadata.parent_id if metadata else None
    parent_metadata = tree.metadata_map.get(parent_id) if parent_id else None
    parent_type = parent_metadata.type if parent_metadata else "unknown"

    class NodeReplacer(cst.CSTTransformer):
        def __init__(self, target_node: cst.CSTNode, replacements: list[cst.CSTNode]):
            self.target_node = target_node
            self.replacements = replacements
            self.replaced = False
            self.visited_blocks: list[tuple[str, cst.IndentedBlock]] = []

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel:
            if original_node is self.target_node:
                if len(self.replacements) == 1:
                    self.replaced = True
                    repl = self.replacements[0]
                    if (
                        hasattr(original_node, "leading_lines")
                        and hasattr(repl, "leading_lines")
                        and not repl.leading_lines
                        and original_node.leading_lines
                    ):
                        repl = repl.with_changes(
                            leading_lines=original_node.leading_lines
                        )
                    return repl
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level replacements
            if original_node is self.target_node or any(
                stmt is self.target_node for stmt in original_node.body
            ):
                new_body: list[cst.BaseStatement] = []
                for stmt in original_node.body:
                    if stmt is self.target_node:
                        repls = list(cast(List[cst.BaseStatement], self.replacements))
                        if (
                            repls
                            and hasattr(stmt, "leading_lines")
                            and hasattr(repls[0], "leading_lines")
                            and not repls[0].leading_lines
                            and stmt.leading_lines
                        ):
                            repls[0] = repls[0].with_changes(
                                leading_lines=stmt.leading_lines
                            )
                        new_body.extend(repls)
                        self.replaced = True
                    else:
                        new_body.append(stmt)
                if self.replaced:
                    return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level replacements (including multiple statements)
            # Check both original and updated body to handle nested cases
            body_to_check = original_node.body
            if any(stmt is self.target_node for stmt in body_to_check):
                new_body: list[cst.BaseStatement] = []
                for stmt in body_to_check:
                    if stmt is self.target_node:
                        repls = list(cast(List[cst.BaseStatement], self.replacements))
                        if (
                            repls
                            and hasattr(stmt, "leading_lines")
                            and hasattr(repls[0], "leading_lines")
                            and not repls[0].leading_lines
                            and stmt.leading_lines
                        ):
                            repls[0] = repls[0].with_changes(
                                leading_lines=stmt.leading_lines
                            )
                        new_body.extend(repls)
                        self.replaced = True
                    else:
                        new_body.append(stmt)
                if self.replaced:
                    return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_SimpleStatementLine(
            self,
            original_node: cst.SimpleStatementLine,
            updated_node: cst.SimpleStatementLine,
        ) -> cst.SimpleStatementLine:
            # If replacing SimpleStatementLine with multiple statements,
            # we need to replace it at the parent level (IndentedBlock/Module)
            # This is handled in leave_IndentedBlock/leave_Module
            # Mark that we visited this node to help with debugging
            if original_node is self.target_node and len(self.replacements) > 1:
                # This will be handled by parent's leave_IndentedBlock/leave_Module
                return updated_node
            return updated_node

    replacer = NodeReplacer(node, replacements_list)
    result = module.visit(replacer)
    if not replacer.replaced:
        # Provide detailed error message with context (node type, parent, line range, hint)
        start_line = getattr(metadata, "start_line", None)
        end_line = getattr(metadata, "end_line", None)
        line_range = (
            f"start_line={start_line}, end_line={end_line}"
            if start_line is not None and end_line is not None
            else "line range unknown"
        )
        suggestion = ""
        if node_type == "SimpleStatementLine" and len(replacements_list) > 1:
            suggestion = (
                " Hint: Replacing SimpleStatementLine with multiple statements requires "
                "the node to be in a Module or IndentedBlock body. "
                f"{public_edit_operation_remediation()} "
                "Alternatively, replace the parent block with universal_file_edit."
            )
        elif node_type in ("Import", "ImportFrom"):
            suggestion = (
                " Hint: Use "
                f"{public_edit_operation_remediation()} to replace the containing "
                "SimpleStatementLine."
            )
        else:
            suggestion = (
                " Hint: Replace only works for direct body statements (e.g. in Module or "
                "IndentedBlock). For inner nodes use "
                f"{public_edit_operation_remediation()} or replace the parent with "
                "universal_file_edit."
            )
        raise ValueError(
            f"Node {node_id} was not replaced. "
            f"Node type: {node_type}, Parent type: {parent_type}, {line_range}.{suggestion}"
        )
    return result


def replace_range(
    module: cst.Module,
    tree: CSTTree,
    start_node_id: str,
    end_node_id: str,
    new_code: str,
) -> cst.Module:
    """Replace a range of consecutive nodes with new code."""
    start_node = tree.node_map.get(start_node_id)
    end_node = tree.node_map.get(end_node_id)
    if not start_node:
        raise ValueError(f"Start node not found: {start_node_id}")
    if not end_node:
        raise ValueError(f"End node not found: {end_node_id}")

    start_metadata = tree.metadata_map.get(start_node_id)
    end_metadata = tree.metadata_map.get(end_node_id)
    start_node = resolve_replace_target_to_current_module(
        module, start_node, start_metadata
    )
    end_node = resolve_replace_target_to_current_module(module, end_node, end_metadata)

    start_parent_id = start_metadata.parent_id if start_metadata else None
    end_parent_id = end_metadata.parent_id if end_metadata else None

    # Verify both nodes have the same parent
    if start_parent_id != end_parent_id:
        raise ValueError(
            f"Start and end nodes must have the same parent. "
            f"Start parent: {start_parent_id}, End parent: {end_parent_id}"
        )

    # Parse new code (supports multi-line)
    new_statements = parse_code_snippet(new_code)
    if not new_statements:
        # Empty code means delete the range
        # This would require deleting all nodes in range, which is complex
        # For now, raise an error
        raise ValueError(
            "Cannot replace range with empty code. Use delete operations instead."
        )

    # Use LibCST transformer to replace the range
    class RangeReplacer(cst.CSTTransformer):
        def __init__(
            self,
            start_node: cst.CSTNode,
            end_node: cst.CSTNode,
            replacements: list[cst.BaseStatement],
        ):
            self.start_node = start_node
            self.end_node = end_node
            self.replacements = replacements
            self.replaced = False
            self.in_range = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level range replacements
            body = list(original_node.body)
            start_idx = -1
            end_idx = -1

            # Find start and end indices
            for i, stmt in enumerate(body):
                if stmt is self.start_node:
                    start_idx = i
                if stmt is self.end_node:
                    end_idx = i
                    break  # End node found, stop searching

            if start_idx >= 0 and end_idx >= 0 and start_idx <= end_idx:
                # Replace range
                new_body = (
                    body[:start_idx] + list(self.replacements) + body[end_idx + 1 :]
                )
                self.replaced = True
                return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level range replacements
            body = list(original_node.body)
            start_idx = -1
            end_idx = -1

            # Find start and end indices
            for i, stmt in enumerate(body):
                if stmt is self.start_node:
                    start_idx = i
                if stmt is self.end_node:
                    end_idx = i
                    break  # End node found, stop searching

            if start_idx >= 0 and end_idx >= 0 and start_idx <= end_idx:
                # Replace range
                new_body = (
                    body[:start_idx] + list(self.replacements) + body[end_idx + 1 :]
                )
                self.replaced = True
                return updated_node.with_changes(body=new_body)
            return updated_node

    replacer = RangeReplacer(start_node, end_node, new_statements)
    result = module.visit(replacer)
    if not replacer.replaced:
        # Provide detailed error message (types, line range, hint)
        start_type = start_metadata.type if start_metadata else "unknown"
        end_type = end_metadata.type if end_metadata else "unknown"
        parent_meta = (
            tree.metadata_map.get(start_parent_id) if start_parent_id else None
        )
        parent_type = (
            parent_meta.type
            if parent_meta and hasattr(parent_meta, "type")
            else "unknown"
        )
        start_line = getattr(start_metadata, "start_line", None)
        start_end = getattr(start_metadata, "end_line", None)
        end_start = getattr(end_metadata, "start_line", None)
        end_line = getattr(end_metadata, "end_line", None)
        line_range = "line range unknown"
        if all(x is not None for x in (start_line, start_end, end_start, end_line)):
            line_range = (
                f"start node lines {start_line}-{start_end}, "
                f"end node lines {end_start}-{end_line}"
            )
        hint = (
            " Hint: Both nodes must be consecutive statements in the same parent "
            f"block (Module or IndentedBlock body). {public_edit_operation_remediation()}"
        )
        raise ValueError(
            f"Range from {start_node_id} to {end_node_id} was not replaced. "
            f"Start node type: {start_type}, End node type: {end_type}, "
            f"Parent type: {parent_type}, {line_range}.{hint}"
        )
    return result


def replace_node_header_only(
    module: cst.Module,
    tree: CSTTree,
    node_id: str,
    new_header_code: str,
) -> cst.Module:
    """
    Replace only the header of a ClassDef or FunctionDef node, preserving its body.

    Parses ``new_header_code`` as a stub (with ``pass`` body appended), extracts
    the header attributes (name, bases, keywords, decorators, params, returns,
    lines_after_decorators), then applies them to the existing node so the original
    body is kept intact.

    Args:
        module: The libcst module to modify.
        tree: The CSTTree holding node metadata.
        node_id: Stable node id of the ClassDef or FunctionDef to update.
        new_header_code: Source code of the new header (e.g. ``class Foo(Bar):`` or
            ``def my_func(x: int) -> str:``).  A ``pass`` body is appended internally
            before parsing, so you must NOT include a body in this string.

    Returns:
        Updated cst.Module with the node header replaced.

    Raises:
        ValueError: If node_id is not found, or the node is not a ClassDef/FunctionDef,
            or ``new_header_code`` cannot be parsed.
    """
    from .tree_modifier_ops_find import find_node_by_id

    # --- locate target node ---
    target_cst_node, _ = find_node_by_id(module, node_id, tree)
    if target_cst_node is None:
        raise ValueError(f"Node not found: {node_id}")

    if not isinstance(target_cst_node, (cst.ClassDef, cst.FunctionDef)):
        raise ValueError(
            f"replace_node_header_only supports only ClassDef/FunctionDef, "
            f"got {type(target_cst_node).__name__} for node_id={node_id}"
        )

    # --- parse the new header as a stub ---
    stub_src = new_header_code.rstrip().rstrip(":")
    if isinstance(target_cst_node, cst.ClassDef):
        stub_src = stub_src + ":\n    pass\n"
    else:
        stub_src = stub_src + ":\n    ...\n"

    try:
        parsed: cst.Module = cst.parse_module(stub_src)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Cannot parse new header code: {exc}") from exc

    if not parsed.body:
        raise ValueError("Parsed stub is empty.")

    stub_node = parsed.body[0]
    if not isinstance(stub_node, type(target_cst_node)):
        raise ValueError(
            f"Header type mismatch: expected {type(target_cst_node).__name__}, "
            f"got {type(stub_node).__name__}"
        )

    # --- apply header attributes to existing node, keep original body ---
    if isinstance(target_cst_node, cst.ClassDef):
        stub_node = cast(cst.ClassDef, stub_node)
        target_cst_node = cast(cst.ClassDef, target_cst_node)
        new_node: cst.CSTNode = target_cst_node.with_changes(
            name=stub_node.name,
            bases=stub_node.bases,
            keywords=stub_node.keywords,
            decorators=stub_node.decorators,
            lpar=stub_node.lpar,
            rpar=stub_node.rpar,
            lines_after_decorators=stub_node.lines_after_decorators,
        )
    else:
        stub_node = cast(cst.FunctionDef, stub_node)
        target_cst_node = cast(cst.FunctionDef, target_cst_node)
        new_node = target_cst_node.with_changes(
            name=stub_node.name,
            params=stub_node.params,
            returns=stub_node.returns,
            decorators=stub_node.decorators,
            async_=stub_node.async_,
            lines_after_decorators=stub_node.lines_after_decorators,
        )

    # --- replace node in module tree ---
    class _HeaderReplacer(cst.CSTTransformer):
        """Transformer that replaces the target node with the header-updated node."""

        def __init__(self, old_node: cst.CSTNode, new_node: cst.CSTNode) -> None:
            """
            Initialize the transformer.

            Args:
                old_node: The original CST node to replace.
                new_node: The updated CST node with new header.
            """
            super().__init__()
            self._old = old_node
            self._new = new_node

        def on_leave(
            self,
            original_node: cst.CSTNodeT,
            updated_node: cst.CSTNodeT,
        ) -> cst.CSTNode:
            """
            Replace old node with new node on leave.

            Args:
                original_node: The original node visited.
                updated_node: The updated node after children visit.

            Returns:
                New node if original matches target, else updated node.
            """
            if original_node is self._old:
                return self._new
            return updated_node

    return module.visit(_HeaderReplacer(target_cst_node, new_node))
