"""
Helpers for CST modify tree command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import libcst as cst

from ..core.cst_tree.models import ROOT_NODE_ID_SENTINEL
from ..core.cst_tree.node_id_markers import build_exact_key_to_id_from_metadata
from ..core.cst_tree.tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES
from ..cst_query import query_source


class InvalidNodeIdError(ValueError):
    """Raised when a mutation target ID is missing, empty, or not valid UUID4."""

    pass


def _is_valid_uuid4(value: Optional[str]) -> bool:
    """Return True if value is non-empty and valid UUID4 string; otherwise False."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        u = uuid.UUID(s, version=4)
        return str(u) == s
    except (ValueError, TypeError):
        return False


def _require_uuid4_mutation_target(
    value: Optional[str],
    field_name: str,
    *,
    allow_root: bool = False,
) -> None:
    """
    Validate mutation target ID: must be non-empty and UUID4 (or __root__ if allowed).
    Raises InvalidNodeIdError on failure (fail-fast).
    """
    if not value or not isinstance(value, str):
        raise InvalidNodeIdError(
            f"{field_name} is required and must be a non-empty UUID4 string; got empty or non-string"
        )
    s = value.strip()
    if not s:
        raise InvalidNodeIdError(
            f"{field_name} must be a non-empty UUID4 string; got empty or whitespace"
        )
    if allow_root and s == ROOT_NODE_ID_SENTINEL:
        return
    if not _is_valid_uuid4(s):
        raise InvalidNodeIdError(
            f"{field_name} must be a valid UUID4 (e.g. from cst_find_node or cst_get_node_info); got {s!r}"
        )


def _find_tree_node_id_by_position(
    tree: Any, start_line: int, start_col: int, end_line: int, end_col: int
) -> Optional[str]:
    """Find tree's node_id for metadata matching given position."""
    for nid, meta in tree.metadata_map.items():
        if (
            meta.start_line == start_line
            and meta.start_col == start_col
            and meta.end_line == end_line
            and meta.end_col == end_col
        ):
            return str(nid)
    return None


def _resolve_to_replaceable_node_id(tree: Any, node_id: str) -> str:
    """
    Resolve node_id to the replaceable ancestor (direct child of Module or
    IndentedBlock) for statement-level replace/delete.

    LibCST expression nodes (``Call``, ``Await``, ``Attribute``, …) and
    fine-grained leaves (``Param``, ``Name``, ``Annotation``) keep their
    ``node_id`` so the modifier replaces the exact indexed node.
    """
    meta = tree.metadata_map.get(node_id)
    node = tree.node_map.get(node_id)
    if node is not None and isinstance(node, cst.BaseExpression):
        return node_id
    if meta and (getattr(meta, "type", "") or "") in FINE_GRAINED_REPLACE_NODE_TYPES:
        return node_id
    if not meta or not getattr(meta, "parent_id", None):
        return node_id
    current_id = node_id
    while True:
        meta = tree.metadata_map.get(current_id)
        if not meta:
            return node_id
        parent_id = getattr(meta, "parent_id", None)
        if not parent_id:
            return current_id
        parent_meta = tree.metadata_map.get(parent_id)
        if not parent_meta:
            return current_id
        parent_type = getattr(parent_meta, "type", "") or ""
        if parent_type in ("Module", "IndentedBlock"):
            return current_id
        current_id = parent_id


def _expand_replace_many_operations(
    operations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Expand replace_many ops into multiple replace ops.
    Each replacement can use either 'selector' (CSTQuery string) or 'node_id' (UUID4).
    Returns a flat list of replace ops. Does not validate tree or selector matches.
    """
    expanded: List[Dict[str, Any]] = []
    for op in operations:
        if op.get("action") == "replace_many":
            replacements = op.get("replacements")
            if not isinstance(replacements, list) or len(replacements) == 0:
                raise ValueError("replace_many requires non-empty list 'replacements'")
            for i, r in enumerate(replacements):
                if not isinstance(r, dict):
                    raise ValueError(
                        f"replace_many.replacements[{i}] must be an object"
                    )
                sel = r.get("selector")
                node_id = r.get("node_id")
                if not sel and not node_id:
                    raise ValueError(
                        f"replace_many.replacements[{i}] must have 'selector' or 'node_id'"
                    )
                if sel and node_id:
                    raise ValueError(
                        f"replace_many.replacements[{i}] must have exactly one of 'selector' or 'node_id', not both"
                    )
                code = r.get("code")
                code_lines = r.get("code_lines")
                if not code and not code_lines:
                    raise ValueError(
                        f"replace_many.replacements[{i}] must have 'code' or 'code_lines'"
                    )
                expanded_op: Dict[str, Any] = {
                    "action": "replace",
                    "match_index": r.get("match_index"),
                    "code": code,
                    "code_lines": code_lines,
                }
                if node_id:
                    expanded_op["node_id"] = node_id
                else:
                    expanded_op["selector"] = sel
                expanded.append(expanded_op)
        else:
            expanded.append(op)
    return expanded


def _resolve_selector_to_tree_node_ids(
    tree: Any, selector: str, match_index: Optional[int], replace_all: bool
) -> List[str]:
    """
    Resolve selector to tree's node_ids (UUIDs in node_map).
    Uses query_source with the tree's persisted UUID mapping.
    """
    matches = query_source(
        tree.module.code,
        selector,
        include_code=False,
        node_ids_by_exact_key=build_exact_key_to_id_from_metadata(tree.metadata_map),
    )
    if not matches:
        return []
    node_ids: List[str] = []
    if replace_all:
        for m in matches:
            if m.node_id in tree.metadata_map:
                node_ids.append(m.node_id)
    else:
        idx = match_index if match_index is not None else 0
        if 0 <= idx < len(matches):
            m = matches[idx]
            if m.node_id in tree.metadata_map:
                node_ids.append(m.node_id)
    return node_ids
