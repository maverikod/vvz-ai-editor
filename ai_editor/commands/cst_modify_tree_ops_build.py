"""
Build list of TreeOperation from raw operation dicts for cst_modify_tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.cst_tree.models import TreeOperation, TreeOperationType
from ..core.cst_tree.tree_metadata import _resolve_node_id
from ..cst_query import QueryParseError

from .cst_modify_tree_helpers import (
    InvalidNodeIdError,
    _require_uuid4_mutation_target,
    _resolve_selector_to_tree_node_ids,
    _resolve_to_replaceable_node_id,
)


def build_tree_operations(
    original_tree: Any,
    operations: List[Dict[str, Any]],
) -> Tuple[Optional[List[TreeOperation]], Optional[ErrorResult]]:
    """
    Validate and build a sorted list of TreeOperation from raw operation dicts.
    Returns (tree_operations, None) on success, (None, error_result) on validation error.
    """
    tree_operations: List[TreeOperation] = []
    for op_dict in operations:
        op_dict = dict(op_dict)
        for ref_field in (
            "node_id",
            "parent_node_id",
            "target_node_id",
            "start_node_id",
            "end_node_id",
        ):
            raw = op_dict.get(ref_field)
            if isinstance(raw, str) and raw.strip():
                op_dict[ref_field] = _resolve_node_id(original_tree, raw.strip())
        action_str = op_dict.get("action")
        if action_str == "replace":
            action = TreeOperationType.REPLACE
        elif action_str == "replace_range":
            action = TreeOperationType.REPLACE_RANGE
        elif action_str == "insert":
            action = TreeOperationType.INSERT
        elif action_str == "delete":
            action = TreeOperationType.DELETE
        elif action_str == "move":
            action = TreeOperationType.MOVE
        else:
            return (
                None,
                ErrorResult(
                    message=f"Invalid action: {action_str}",
                    code="INVALID_ACTION",
                    details={"action": action_str},
                ),
            )

        try:
            if action == TreeOperationType.REPLACE_RANGE:
                start_nid = op_dict.get("start_node_id")
                end_nid = op_dict.get("end_node_id")
                if not start_nid or not end_nid:
                    raise InvalidNodeIdError(
                        "replace_range requires start_node_id and end_node_id (both non-empty UUID4)"
                    )
                _require_uuid4_mutation_target(start_nid, "start_node_id")
                _require_uuid4_mutation_target(end_nid, "end_node_id")
            elif action == TreeOperationType.INSERT:
                parent_nid = op_dict.get("parent_node_id")
                target_nid = op_dict.get("target_node_id")
                if parent_nid is not None and parent_nid != "":
                    _require_uuid4_mutation_target(
                        parent_nid, "parent_node_id", allow_root=True
                    )
                if target_nid:
                    _require_uuid4_mutation_target(target_nid, "target_node_id")
            elif action == TreeOperationType.MOVE:
                move_node_id = op_dict.get("node_id")
                _require_uuid4_mutation_target(move_node_id, "node_id")
                parent_nid = op_dict.get("parent_node_id")
                if parent_nid is not None and parent_nid != "":
                    _require_uuid4_mutation_target(
                        parent_nid, "parent_node_id", allow_root=True
                    )
        except InvalidNodeIdError as e:
            return (
                None,
                ErrorResult(
                    message=str(e),
                    code="INVALID_NODE_ID",
                    details={
                        "action": action_str,
                        "hint": "Use UUID4 node_id from cst_find_node or cst_get_node_info",
                    },
                ),
            )

        pos_val = op_dict.get("position")
        position_str: Optional[str] = None
        position_after_index: Optional[int] = None
        if isinstance(pos_val, dict) and "after" in pos_val:
            position_str = "after"
            try:
                position_after_index = int(pos_val["after"])
            except (TypeError, ValueError):
                position_after_index = None
        elif isinstance(pos_val, str):
            position_str = pos_val

        node_ids_to_use: List[str] = []
        op_node_id = op_dict.get("node_id")
        selector = op_dict.get("selector")
        if action in (TreeOperationType.REPLACE, TreeOperationType.DELETE):
            has_node_id = bool(op_node_id)
            has_selector = bool(selector)
            if has_node_id and has_selector:
                return (
                    None,
                    ErrorResult(
                        message=(
                            "For replace/delete provide exactly one of node_id or selector, not both."
                        ),
                        code="INVALID_OPERATION",
                        details={
                            "action": action_str,
                            "hint": "Use either node_id or selector, not both.",
                        },
                    ),
                )
            if not has_node_id and not has_selector:
                return (
                    None,
                    ErrorResult(
                        message=(
                            "For replace/delete provide either node_id or selector."
                        ),
                        code="INVALID_OPERATION",
                        details={
                            "action": action_str,
                            "hint": "Use node_id (from cst_find_node) or selector (CSTQuery).",
                        },
                    ),
                )
        if op_node_id:
            try:
                _require_uuid4_mutation_target(op_node_id, "node_id")
            except InvalidNodeIdError as e:
                return (
                    None,
                    ErrorResult(
                        message=str(e),
                        code="INVALID_NODE_ID",
                        details={
                            "action": action_str,
                            "hint": "Use UUID4 node_id from cst_find_node or cst_get_node_info",
                        },
                    ),
                )
            node_ids_to_use = [op_node_id]
        elif selector and action in (
            TreeOperationType.REPLACE,
            TreeOperationType.DELETE,
        ):
            try:
                node_ids_to_use = _resolve_selector_to_tree_node_ids(
                    original_tree,
                    selector,
                    op_dict.get("match_index"),
                    op_dict.get("replace_all", False),
                )
            except QueryParseError as e:
                return (
                    None,
                    ErrorResult(
                        message=f"Invalid selector: {e}",
                        code="SELECTOR_PARSE_ERROR",
                        details={"selector": selector, "error": str(e)},
                    ),
                )
            if not node_ids_to_use:
                return (
                    None,
                    ErrorResult(
                        message=f"Selector matched no nodes: {selector}",
                        code="SELECTOR_NO_MATCH",
                        details={"selector": selector},
                    ),
                )
        elif action == TreeOperationType.REPLACE_RANGE:
            tree_operations.append(
                TreeOperation(
                    action=action,
                    node_id="",
                    code=op_dict.get("code"),
                    code_lines=op_dict.get("code_lines"),
                    position=position_str,
                    position_after_index=position_after_index,
                    parent_node_id=op_dict.get("parent_node_id"),
                    target_node_id=op_dict.get("target_node_id"),
                    start_node_id=op_dict.get("start_node_id"),
                    end_node_id=op_dict.get("end_node_id"),
                    replace_all_child_nodes=bool(
                        op_dict.get("replace_all_child_nodes", False)
                    ),
                )
            )
            continue
        else:
            node_ids_to_use = [op_dict.get("node_id", "")]

        for nid in node_ids_to_use:
            if action in (TreeOperationType.REPLACE, TreeOperationType.DELETE):
                nid = _resolve_to_replaceable_node_id(original_tree, nid)
            tree_operations.append(
                TreeOperation(
                    action=action,
                    node_id=nid,
                    code=op_dict.get("code"),
                    code_lines=op_dict.get("code_lines"),
                    position=position_str,
                    position_after_index=position_after_index,
                    parent_node_id=op_dict.get("parent_node_id"),
                    target_node_id=op_dict.get("target_node_id"),
                    start_node_id=op_dict.get("start_node_id"),
                    end_node_id=op_dict.get("end_node_id"),
                    replace_all_child_nodes=bool(
                        op_dict.get("replace_all_child_nodes", False)
                    ),
                )
            )

    def _replace_delete_sort_key(op: TreeOperation) -> tuple:
        if (
            op.action
            in (
                TreeOperationType.REPLACE,
                TreeOperationType.DELETE,
            )
            and op.node_id
        ):
            meta = original_tree.metadata_map.get(
                _resolve_node_id(original_tree, op.node_id)
            )
            line = getattr(meta, "start_line", None) or 0
            return (0, -line)
        return (1, 0)

    tree_operations.sort(key=_replace_delete_sort_key)
    return (tree_operations, None)
