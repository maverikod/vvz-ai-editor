"""
Validation and parsing for CST replace-ops (selectors and ops).

Builds Selector/ReplaceOp from request params. Used by run_ops_mode and tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..core.cst_module import ReplaceOp, Selector
from ..core.uuid_validation import is_valid_uuid4

# Selector kinds supported by apply_replace_ops (for validation and docs).
SUPPORTED_SELECTOR_KINDS = frozenset(
    {
        "module",
        "function",
        "class",
        "method",
        "range",
        "block_id",
        "node_id",
        "cst_query",
    }
)


def selector_from_dict(d: Dict[str, Any]) -> Selector:
    """
    Build Selector from request dict and validate required fields per kind.

    Raises:
        ValueError: For unknown kind or missing required fields.
    """
    if not isinstance(d, dict):
        raise ValueError("selector must be an object")
    kind = d.get("kind")
    if not kind or not isinstance(kind, str):
        raise ValueError("selector.kind is required and must be a string")
    if kind not in SUPPORTED_SELECTOR_KINDS:
        raise ValueError(
            f"Unsupported selector kind: {kind}. "
            f"Supported: {sorted(SUPPORTED_SELECTOR_KINDS)}"
        )
    name = d.get("name")
    start_line = d.get("start_line")
    start_col = d.get("start_col")
    end_line = d.get("end_line")
    end_col = d.get("end_col")
    block_id = d.get("block_id")
    node_id = d.get("node_id")
    query = d.get("query")
    match_index = d.get("match_index")

    if kind == "range":
        if start_line is None or end_line is None:
            raise ValueError("selector kind 'range' requires start_line and end_line")
    elif kind == "block_id":
        if not block_id:
            raise ValueError("selector kind 'block_id' requires block_id")
    elif kind == "node_id":
        if not node_id:
            raise ValueError("selector kind 'node_id' requires node_id")
        if not is_valid_uuid4(str(node_id)):
            raise ValueError(
                "selector kind 'node_id' requires a valid UUID4; invalid value"
            )
    elif kind == "cst_query":
        if not query:
            raise ValueError("selector kind 'cst_query' requires query")
        if match_index is not None and (
            not isinstance(match_index, int) or match_index < 0
        ):
            raise ValueError("selector match_index must be a non-negative integer")
    elif kind in ("function", "class", "method"):
        if not name:
            raise ValueError(f"selector kind '{kind}' requires name")

    return Selector(
        kind=kind,
        name=name if name else None,
        start_line=int(start_line) if start_line is not None else None,
        start_col=int(start_col) if start_col is not None else None,
        end_line=int(end_line) if end_line is not None else None,
        end_col=int(end_col) if end_col is not None else None,
        block_id=str(block_id) if block_id else None,
        node_id=str(node_id) if node_id else None,
        query=str(query) if query else None,
        match_index=int(match_index) if match_index is not None else None,
    )


def ops_from_params(ops_list: Any) -> List[ReplaceOp]:
    """
    Build list of ReplaceOp from request ops array.

    Each item: { "selector": { kind, ... }, "new_code": str, optional "file_docstring" }.

    Raises:
        ValueError: If ops_list is invalid or items lack required fields.
    """
    if not isinstance(ops_list, list) or len(ops_list) == 0:
        raise ValueError("ops must be a non-empty array")
    result: List[ReplaceOp] = []
    for i, item in enumerate(ops_list):
        if not isinstance(item, dict):
            raise ValueError(f"ops[{i}] must be an object")
        sel_dict = item.get("selector")
        new_code = item.get("new_code")
        if sel_dict is None:
            raise ValueError(f"ops[{i}].selector is required")
        if new_code is None:
            raise ValueError(f"ops[{i}].new_code is required")
        new_code = str(new_code)
        file_docstring = item.get("file_docstring")
        if file_docstring is not None:
            file_docstring = str(file_docstring)
        sel = selector_from_dict(sel_dict)
        result.append(
            ReplaceOp(
                selector=sel,
                new_code=new_code,
                file_docstring=file_docstring,
            )
        )
    return result
