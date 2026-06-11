"""
Logical block listing for CST module tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from .models import BlockInfo


def _block_id(kind: str, qualname: str, start_line: int, end_line: int) -> str:
    # Stable enough for edit workflows; if code moves, user refreshes via list_cst_blocks.
    return f"{kind}:{qualname}:{start_line}-{end_line}"


def list_cst_blocks(source: str) -> list[BlockInfo]:
    """
    List replaceable statement blocks with stable ids.

    We focus on *logical blocks*:
    - top-level classes/functions
    - class methods
    - any statement by line-range selector (still supported via range)
    """
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    blocks: list[BlockInfo] = []

    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None:
            continue
        if isinstance(stmt, cst.FunctionDef):
            qual = stmt.name.value
            blocks.append(
                BlockInfo(
                    block_id=_block_id("function", qual, pos.start.line, pos.end.line),
                    kind="function",
                    qualname=qual,
                    start_line=pos.start.line,
                    end_line=pos.end.line,
                )
            )
        elif isinstance(stmt, cst.ClassDef):
            class_name = stmt.name.value
            blocks.append(
                BlockInfo(
                    block_id=_block_id(
                        "class", class_name, pos.start.line, pos.end.line
                    ),
                    kind="class",
                    qualname=class_name,
                    start_line=pos.start.line,
                    end_line=pos.end.line,
                )
            )
            # Methods
            for cstmt in stmt.body.body:
                if not isinstance(cstmt, cst.FunctionDef):
                    continue
                mpos = positions.get(cstmt)
                if mpos is None:
                    continue
                qual = f"{class_name}.{cstmt.name.value}"
                blocks.append(
                    BlockInfo(
                        block_id=_block_id(
                            "method", qual, mpos.start.line, mpos.end.line
                        ),
                        kind="method",
                        qualname=qual,
                        start_line=mpos.start.line,
                        end_line=mpos.end.line,
                    )
                )

    return blocks


def _line_count(start_line: int, end_line: int) -> int:
    """Return number of lines (inclusive)."""
    return max(0, end_line - start_line + 1)


def list_file_structure(source: str, *, include_functions: bool = True) -> dict:
    """
    List top-level classes with their first-level methods and optional top-level
    functions, with start_line, end_line, and line_count for each.

    Uses the same CST-based extraction as list_cst_blocks so line numbers
    are consistent. Only direct class body methods are included (no nested
    classes or nested functions).

    Args:
        source: Python source code string.
        include_functions: If True, include top-level functions in the result.

    Returns:
        Dict with keys:
        - classes: list of {
            name, start_line, end_line, line_count,
            methods: list of { name, start_line, end_line, line_count }
          }
        - functions: list of { name, start_line, end_line, line_count }
          (empty if include_functions is False)
    """
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    classes_out: list[dict] = []
    functions_out: list[dict] = []

    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None:
            continue
        if isinstance(stmt, cst.FunctionDef):
            if not include_functions:
                continue
            name = stmt.name.value
            functions_out.append(
                {
                    "name": name,
                    "start_line": pos.start.line,
                    "end_line": pos.end.line,
                    "line_count": _line_count(pos.start.line, pos.end.line),
                }
            )
        elif isinstance(stmt, cst.ClassDef):
            class_name = stmt.name.value
            methods_out: list[dict] = []
            for cstmt in stmt.body.body:
                if not isinstance(cstmt, cst.FunctionDef):
                    continue
                mpos = positions.get(cstmt)
                if mpos is None:
                    continue
                mname = cstmt.name.value
                methods_out.append(
                    {
                        "name": mname,
                        "start_line": mpos.start.line,
                        "end_line": mpos.end.line,
                        "line_count": _line_count(mpos.start.line, mpos.end.line),
                    }
                )
            classes_out.append(
                {
                    "name": class_name,
                    "start_line": pos.start.line,
                    "end_line": pos.end.line,
                    "line_count": _line_count(pos.start.line, pos.end.line),
                    "methods": methods_out,
                }
            )

    return {"classes": classes_out, "functions": functions_out}
