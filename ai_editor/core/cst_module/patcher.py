"""
Module patcher implementation for CST module tools.

This is the core logic used by `run_ops_mode` (Python handler / cst_apply_buffer).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from ...cst_query import query_source
from ..exceptions import CSTModulePatchError
from ..uuid_validation import is_valid_uuid4
from .blocks import list_cst_blocks
from .models import BlockInfo, ReplaceOp, Selector
from .utils import move_module_imports_to_top


def _parse_snippet_as_module_body(snippet: str) -> list[cst.BaseStatement]:
    """
    Parse a snippet into a list of module-level statements.

    Handles code with indentation by normalizing indentation before parsing.
    This allows replacing code blocks inside functions/classes using range selector.

    Args:
        snippet: Code snippet to parse (may have indentation).

    Returns:
        List of CST statements.
    """
    if not snippet.strip():
        return []

    # Normalize indentation: find minimum common indentation and remove it
    lines = snippet.splitlines()
    if not lines:
        return []

    # Find minimum indentation (excluding empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # Skip empty lines
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent

    # If all lines are empty or no indentation found, use original
    if min_indent is None or min_indent == 0:
        normalized = snippet
    else:
        # Remove minimum indentation from all lines
        normalized_lines = []
        for line in lines:
            if line.strip():  # Non-empty line
                if len(line) >= min_indent:
                    normalized_lines.append(line[min_indent:])
                else:
                    normalized_lines.append(line)
            else:  # Empty line
                normalized_lines.append("")
        normalized = "\n".join(normalized_lines)

    # Try parsing as module first
    try:
        mod = cst.parse_module(normalized)
        return list(mod.body)
    except cst.ParserSyntaxError:
        # If parsing as module fails, try wrapping in a function body
        # This handles cases where code is a statement sequence (not valid module-level)
        # Add proper indentation for function body (4 spaces)
        indented_lines = []
        for line in normalized.splitlines():
            if line.strip():
                indented_lines.append("    " + line)
            else:
                indented_lines.append("")
        func_body = "\n".join(indented_lines)
        func_wrapper = f"def _temp():\n{func_body}"

        try:
            mod = cst.parse_module(func_wrapper)
            if mod.body and isinstance(mod.body[0], cst.FunctionDef):
                func = mod.body[0]
                if isinstance(func.body, cst.IndentedBlock):
                    return list(func.body.body)
        except Exception:
            # If function wrapper also fails, re-raise with better context
            pass

        # Last resort: provide helpful error message
        raise CSTModulePatchError(
            "Failed to parse code snippet as statements. "
            "Code must be valid Python statements. "
            "Ensure the snippet can be parsed as module-level code or function body."
        )


def _narrowest_stmt_line_span_containing_range(
    module: cst.Module,
    positions: Mapping[cst.CSTNode, Any],
    us: int,
    ue: int,
) -> Optional[tuple[int, int]]:
    """
    Map a user line range [us, ue] to the (start_line, end_line) span of the
    narrowest ``BaseStatement`` that fully contains that range.

    ``kind: range`` without columns used to register replacements under the
    user's tuple only; ``_StatementListRewriter`` matches ``PositionProvider``
    spans on each statement. A multi-line ``SimpleStatementLine`` therefore
    never matched (e.g. user (110, 110) vs statement (110, 112)), yielding
    ``replaced`` > 0 with an empty diff. Resolving to the real statement span
    fixes that while preferring the innermost statement when several nest
    (narrowest line span wins).
    """
    if us > ue:
        return None

    best: Optional[tuple[int, int, int]] = None  # (span_len, start_line, end_line)

    def _consider(stmt: cst.BaseStatement) -> None:
        nonlocal best
        pos = positions.get(stmt)
        if pos is None or not hasattr(pos, "start") or not hasattr(pos, "end"):
            return
        sl, el = int(pos.start.line), int(pos.end.line)
        if sl > us or el < ue:
            return
        span_len = el - sl
        if best is None or span_len < best[0] or (span_len == best[0] and sl < best[1]):
            best = (span_len, sl, el)

    class _Collect(cst.CSTVisitor):
        def visit_Module(self, node: cst.Module) -> bool:
            for s in node.body:
                _consider(s)
            return True

        def visit_IndentedBlock(self, node: cst.IndentedBlock) -> bool:
            for s in node.body:
                _consider(s)
            return True

    module.visit(_Collect())
    if best is None:
        return None
    return (best[1], best[2])


def _copy_outer_trivia_to_replacements(
    original: cst.BaseStatement,
    replacements: list[cst.BaseStatement],
) -> list[cst.BaseStatement]:
    """
    Preserve LibCST layout before a replaced statement.

    Parsed replacement snippets default to empty ``leading_lines``; physical
    blank lines immediately above the statement live there on the original node.
    Copy ``leading_lines`` onto the first replacement so range/block/function/
    method/cst_query replacements do not drop a blank line above the edit.

    We intentionally do **not** copy ``trailing_whitespace`` from the original:
    the replacement's own trailing trivia (including end-of-line ``# type:
    ignore`` comments) must stay intact.
    """
    if not replacements:
        return replacements
    leading = original.leading_lines
    if len(replacements) == 1:
        sole = replacements[0]
        return [sole.with_changes(leading_lines=leading)]
    first = replacements[0].with_changes(leading_lines=leading)
    return [first, *replacements[1:]]


class _StatementListRewriter(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        stmt_by_span: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        stmt_by_lines: dict[tuple[int, int], list[cst.BaseStatement]],
        small_by_span: dict[tuple[int, int, int, int], list[cst.BaseSmallStatement]],
    ):
        self._stmt_by_span = stmt_by_span
        self._stmt_by_lines = stmt_by_lines
        self._small_by_span = small_by_span

    def _rewrite_body(
        self,
        original_body: list[cst.BaseStatement],
        updated_body: list[cst.BaseStatement],
    ) -> list[cst.BaseStatement]:
        new_body: list[cst.BaseStatement] = []
        for original_stmt, updated_stmt in zip(original_body, updated_body):
            pos = self.get_metadata(PositionProvider, original_stmt, None)
            if pos is None:
                new_body.append(updated_stmt)
                continue
            span_key = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)
            line_key = (pos.start.line, pos.end.line)
            if span_key in self._stmt_by_span:
                new_body.extend(
                    _copy_outer_trivia_to_replacements(
                        original_stmt, self._stmt_by_span[span_key]
                    )
                )
            elif line_key in self._stmt_by_lines:
                new_body.extend(
                    _copy_outer_trivia_to_replacements(
                        original_stmt, self._stmt_by_lines[line_key]
                    )
                )
            else:
                new_body.append(updated_stmt)
        return new_body

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        return updated_node.with_changes(
            body=self._rewrite_body(list(original_node.body), list(updated_node.body))
        )

    def leave_IndentedBlock(
        self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
    ) -> cst.IndentedBlock:
        return updated_node.with_changes(
            body=self._rewrite_body(list(original_node.body), list(updated_node.body))
        )

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.SimpleStatementLine:
        new_small: list[cst.BaseSmallStatement] = []
        for original_s, updated_s in zip(original_node.body, updated_node.body):
            pos = self.get_metadata(PositionProvider, original_s, None)
            if pos is None:
                new_small.append(updated_s)
                continue
            span_key = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)
            if span_key in self._small_by_span:
                new_small.extend(self._small_by_span[span_key])
            else:
                new_small.append(updated_s)

        if not new_small:
            raise CSTModulePatchError(
                "Cannot delete all small statements from a SimpleStatementLine; "
                "target the whole statement line instead."
            )
        return updated_node.with_changes(body=new_small)


_NODE_ID_RE = re.compile(
    r"^(?P<kind>[^:]+):(?P<qualname>[^:]*):(?P<type>[^:]+):"
    r"(?P<sl>\d+):(?P<sc>\d+)-(?P<el>\d+):(?P<ec>\d+)$"
)


def _parse_node_id(node_id: str) -> tuple[str, tuple[int, int, int, int]]:
    """
    Parse node_id returned by `query_cst`.

    Format:
        "{kind}:{qualname}:{node_type}:{sl}:{sc}-{el}:{ec}"
    """
    m = _NODE_ID_RE.match(node_id.strip())
    if not m:
        raise CSTModulePatchError(f"Invalid node_id: {node_id}")
    kind = m.group("kind")
    return kind, (
        int(m.group("sl")),
        int(m.group("sc")),
        int(m.group("el")),
        int(m.group("ec")),
    )


def _parse_small_stmt_snippet(snippet: str) -> list[cst.BaseSmallStatement]:
    if not snippet.strip():
        return []
    mod = cst.parse_module(snippet)
    if len(mod.body) != 1 or not isinstance(mod.body[0], cst.SimpleStatementLine):
        raise CSTModulePatchError(
            "Small-statement replacement must be a single SimpleStatementLine (e.g. 'return 1')"
        )
    return list(mod.body[0].body)


def apply_replace_ops(source: str, ops: list[ReplaceOp]) -> tuple[str, dict[str, Any]]:
    """
    Apply replace operations to blocks in `source`.

    If source is empty and there's a "module" selector, create module from scratch.
    If file_docstring is set on any op, the module-level docstring is updated (or added).

    Returns:
        (new_source, stats)
    """
    # Handle module creation from scratch
    for op in ops:
        if op.selector.kind == "module":
            if source and source.strip():
                # File exists -- treat file_docstring as a module docstring update.
                # Fall through to the normal path below (file_docstring handled there).
                break
            # Validate required parameters - both must be present and non-empty
            if not op.file_docstring or not op.file_docstring.strip():
                raise CSTModulePatchError(
                    "file_docstring is required and must not be empty when creating module from scratch"
                )
            if not op.new_code or not op.new_code.strip():
                raise CSTModulePatchError(
                    "new_code (first node) is required and must not be empty when creating module from scratch"
                )

            # Parse first node
            first_node_module = cst.parse_module(op.new_code)
            if not first_node_module.body:
                raise CSTModulePatchError(
                    "new_code must contain at least one node (function or class)"
                )

            # Create module with docstring and first node
            # LibCST docstring format: triple-quoted string
            docstring_value = op.file_docstring.strip()
            # Ensure it's properly quoted (handle if already has quotes)
            if not (
                docstring_value.startswith('"""') or docstring_value.startswith("'''")
            ):
                docstring_value = f'"""{docstring_value}"""'

            docstring_stmt = cst.SimpleStatementLine(
                body=[cst.Expr(value=cst.SimpleString(value=docstring_value))]
            )

            # Build module body: docstring + first node
            module_body: list[cst.BaseStatement] = [docstring_stmt]
            module_body.extend(first_node_module.body)

            # Create module
            new_module = cst.Module(body=module_body)

            # Normalize imports (will move imports after docstring)
            new_module = move_module_imports_to_top(new_module)

            stats = {
                "replaced": 0,
                "removed": 0,
                "created": 1,
                "unmatched": [],
            }
            return (new_module.code, stats)

    # Normal path: apply replacements to existing source
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    # Apply file_docstring update if any op carries it.
    # Find the first op that has file_docstring set.
    new_file_docstring: Optional[str] = None
    for op in ops:
        if op.file_docstring and op.file_docstring.strip():
            new_file_docstring = op.file_docstring.strip()
            break

    if new_file_docstring is not None:
        # Ensure triple-quoted
        if not (
            new_file_docstring.startswith('"""') or new_file_docstring.startswith("'''")
        ):
            new_file_docstring = f'"""{new_file_docstring}"""'
        docstring_stmt = cst.SimpleStatementLine(
            body=[cst.Expr(value=cst.SimpleString(value=new_file_docstring))]
        )
        body = list(module.body)
        # Check if first statement is already a module docstring (Expr with SimpleString)
        if (
            body
            and isinstance(body[0], cst.SimpleStatementLine)
            and len(body[0].body) == 1
            and isinstance(body[0].body[0], cst.Expr)
            and isinstance(
                body[0].body[0].value,
                (cst.SimpleString, cst.ConcatenatedString, cst.FormattedString),
            )
        ):
            # Replace existing docstring, preserve trailing whitespace of original
            body[0] = docstring_stmt.with_changes(leading_lines=body[0].leading_lines)
        else:
            # Insert new docstring at top
            body.insert(0, docstring_stmt)
        module = module.with_changes(body=body)
        wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    blocks = list_cst_blocks(source)
    blocks_by_id = {b.block_id: b for b in blocks}
    blocks_by_kind_name: dict[tuple[str, str], BlockInfo] = {
        (b.kind, b.qualname): b for b in blocks
    }

    position_map = wrapper.resolve(PositionProvider)

    replaced = 0
    removed = 0
    unmatched: list[Selector] = []

    stmt_replacements_by_span: dict[
        tuple[int, int, int, int], list[cst.BaseStatement]
    ] = {}
    stmt_replacements_by_lines: dict[tuple[int, int], list[cst.BaseStatement]] = {}
    small_replacements_by_span: dict[
        tuple[int, int, int, int], list[cst.BaseSmallStatement]
    ] = {}

    for op in ops:
        sel = op.selector
        target: Optional[BlockInfo] = None

        if sel.kind == "module":
            # kind=module with existing source: file_docstring already handled above.
            # new_code is ignored in this path (use specific selectors instead).
            continue

        if sel.kind == "block_id" and sel.block_id:
            target = blocks_by_id.get(sel.block_id)
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if sel.kind in ("function", "class") and sel.name:
            target = blocks_by_kind_name.get((sel.kind, sel.name))
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if sel.kind == "method" and sel.name:
            target = blocks_by_kind_name.get(("method", sel.name))
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if (
            sel.kind == "range"
            and sel.start_line is not None
            and sel.end_line is not None
        ):
            if sel.start_col is not None and sel.end_col is not None:
                span_key = (sel.start_line, sel.start_col, sel.end_line, sel.end_col)
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_span[span_key] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            else:
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                resolved = _narrowest_stmt_line_span_containing_range(
                    module, position_map, sel.start_line, sel.end_line
                )
                if resolved is None:
                    unmatched.append(sel)
                    continue
                stmt_replacements_by_lines[resolved] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            continue

        if sel.kind == "node_id" and sel.node_id:
            if not is_valid_uuid4(sel.node_id):
                raise CSTModulePatchError("node_id must be a valid UUID4 for mutation")
            # UUID4 node_id is resolved to span by the caller (run_ops_mode) using
            # tree_id and tree.metadata_map; the caller replaces node_id selector
            # with range selector before calling apply_replace_ops. So we should
            # not reach here with UUID4. If we do, reject (no fallback).
            raise CSTModulePatchError(
                "node_id (UUID4) must be resolved to range by caller using tree_id; "
                "pass tree_id when using ops with node_id selector"
            )

        if sel.kind == "cst_query" and sel.query:
            matches = query_source(source, sel.query, include_code=False)
            if not matches:
                unmatched.append(sel)
                continue
            idx = sel.match_index
            if idx is None:
                if len(matches) != 1:
                    raise CSTModulePatchError(
                        f"Selector matched {len(matches)} nodes; use :nth() or match_index"
                    )
                idx = 0
            if idx < 0 or idx >= len(matches):
                raise CSTModulePatchError(
                    f"match_index {idx} out of bounds for {len(matches)} matches"
                )
            m = matches[idx]
            span_key = (m.start_line, m.start_col, m.end_line, m.end_col)
            if m.kind in ("stmt", "function", "class", "method"):
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_span[span_key] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            elif m.kind == "import":
                # Import/ImportFrom live in SimpleStatementLine; use line range for match
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_lines[(m.start_line, m.end_line)] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            elif m.kind == "smallstmt":
                new_small = _parse_small_stmt_snippet(op.new_code)
                small_replacements_by_span[span_key] = new_small
                replaced += 1 if new_small else 0
                removed += 0 if new_small else 1
            else:
                raise CSTModulePatchError(
                    f"cst_query replacement supports only stmt/smallstmt/function/class/method/import matches, got {m.kind}"
                )
            continue

        raise CSTModulePatchError(f"Unsupported selector kind: {sel.kind}")

    patched = wrapper.visit(
        _StatementListRewriter(
            stmt_by_span=stmt_replacements_by_span,
            stmt_by_lines=stmt_replacements_by_lines,
            small_by_span=small_replacements_by_span,
        )
    )
    patched = move_module_imports_to_top(patched)
    new_source = patched.code

    stats = {
        "replaced": replaced,
        "removed": removed,
        "created": 0,
        "unmatched": [
            {
                "kind": s.kind,
                "name": s.name,
                "start_line": s.start_line,
                "start_col": s.start_col,
                "end_line": s.end_line,
                "end_col": s.end_col,
                "block_id": s.block_id,
                "node_id": s.node_id,
                "query": s.query,
                "match_index": s.match_index,
            }
            for s in unmatched
        ],
    }
    return new_source, stats
