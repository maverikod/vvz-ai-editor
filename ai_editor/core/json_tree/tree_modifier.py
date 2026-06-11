"""
Apply modify operations to an in-memory JSON tree and rebuild index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .json_pointer import (
    delete_at,
    get_value_at,
    insert_into_array,
    insert_into_object,
    insert_into_object_relative,
    set_value_at,
)
from ai_editor.commands.universal_file_edit.insert_position import (
    coalesce_tree_temp_insert_position,
)

from .json_query import resolve_node_id_from_pointer
from .models import ROOT_POINTER, JSONTree
from .tree_builder import _build_index, get_tree

logger = logging.getLogger(__name__)


def _deep_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _pointer_for_node(tree: JSONTree, node_id: str) -> str:
    p = tree.pointer_by_id.get(node_id)
    if p is None:
        raise KeyError(f"Unknown node_id: {node_id}")
    return p


def modify_tree(tree_id: str, operations: List[Dict[str, Any]]) -> JSONTree:
    """
    Apply operations in order; rebuild index after each operation.

    Supported actions:
    - replace: node_id (optional if json_pointer set), json_pointer (optional), value
    - delete: node_id or json_pointer
    - insert: parent_node_id or parent_json_pointer, value, key (object) or index (array, optional);
      sibling-relative: before_node_id / after_node_id (array), before_key / after_key (object)
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    for op in operations:
        action = (op.get("action") or "").lower()
        if action == "replace":
            _op_replace(tree, op)
        elif action == "delete":
            _op_delete(tree, op)
        elif action == "insert":
            _op_insert(tree, op)
        else:
            raise ValueError(f"Unknown action: {action!r}")

        _build_index(tree)

    return tree


def _resolve_pointer(tree: JSONTree, op: Dict[str, Any]) -> str:
    if "json_pointer" in op:
        return str(op["json_pointer"])
    if op.get("node_id"):
        return _pointer_for_node(tree, str(op["node_id"]))
    raise ValueError("Operation requires json_pointer or node_id")


def _resolve_parent_pointer(tree: JSONTree, op: Dict[str, Any]) -> str:
    if "parent_json_pointer" in op:
        return str(op["parent_json_pointer"])
    if op.get("parent_node_id"):
        return _pointer_for_node(tree, str(op["parent_node_id"]))
    raise ValueError("insert requires parent_node_id or parent_json_pointer")


def _op_replace(tree: JSONTree, op: Dict[str, Any]) -> None:
    pointer = _resolve_pointer(tree, op)
    if "value" not in op:
        raise ValueError("replace requires value")
    value = _deep_json_value(op["value"])
    if pointer == ROOT_POINTER:
        tree.root_data = value
        return
    set_value_at(tree.root_data, pointer, value)


def _op_delete(tree: JSONTree, op: Dict[str, Any]) -> None:
    pointer = _resolve_pointer(tree, op)
    if pointer == ROOT_POINTER:
        raise ValueError("Cannot delete root document")
    delete_at(tree.root_data, pointer)


def _array_insert_index_from_sibling(
    tree: JSONTree,
    *,
    before_node_id: Optional[str],
    after_node_id: Optional[str],
) -> int:
    sibling_id = before_node_id if before_node_id is not None else after_node_id
    if sibling_id is None:
        raise ValueError("before_node_id or after_node_id required")
    sibling_pointer = _pointer_for_node(tree, sibling_id)
    idx_str = sibling_pointer.rsplit("/", 1)[-1]
    if not idx_str.isdigit():
        raise ValueError(
            f"Sibling node_id {sibling_id!r} is not an array element (pointer {sibling_pointer!r})"
        )
    idx = int(idx_str)
    return idx if before_node_id is not None else idx + 1


def _coalesce_insert_pointer_sibling_ids(tree: JSONTree, op: Dict[str, Any]) -> None:
    """Map ``before_json_pointer`` / ``after_json_pointer`` to sibling node ids."""
    before_ptr = op.get("before_json_pointer")
    after_ptr = op.get("after_json_pointer")
    if before_ptr is not None and after_ptr is not None:
        raise ValueError(
            "before_json_pointer and after_json_pointer are mutually exclusive"
        )
    if before_ptr is not None:
        if op.get("before_node_id"):
            raise ValueError(
                "before_json_pointer and before_node_id are mutually exclusive"
            )
        nid = resolve_node_id_from_pointer(tree, str(before_ptr))
        if nid is None:
            raise ValueError(f"json_pointer not found: {before_ptr!r}")
        op["before_node_id"] = nid
    if after_ptr is not None:
        if op.get("after_node_id"):
            raise ValueError(
                "after_json_pointer and after_node_id are mutually exclusive"
            )
        nid = resolve_node_id_from_pointer(tree, str(after_ptr))
        if nid is None:
            raise ValueError(f"json_pointer not found: {after_ptr!r}")
        op["after_node_id"] = nid


def _validate_insert_sibling_options(op: Dict[str, Any], parent_kind: str) -> None:
    before_nid = op.get("before_node_id")
    after_nid = op.get("after_node_id")
    idx = op.get("index")
    before_key = op.get("before_key")
    after_key = op.get("after_key")

    if before_nid and after_nid:
        raise ValueError("before_node_id and after_node_id are mutually exclusive")
    if before_key and after_key:
        raise ValueError("before_key and after_key are mutually exclusive")
    if parent_kind == "array":
        if (before_nid or after_nid) and idx is not None:
            raise ValueError(
                "before_node_id/after_node_id and index are mutually exclusive"
            )
        if before_key or after_key:
            raise ValueError("before_key/after_key apply only to object parents")
    elif parent_kind == "object":
        if before_nid or after_nid:
            raise ValueError("before_node_id/after_node_id apply only to array parents")
    else:
        raise TypeError("insert parent must be object or array")


def _op_insert(tree: JSONTree, op: Dict[str, Any]) -> None:
    if "value" not in op:
        raise ValueError("insert requires value")
    coalesce_tree_temp_insert_position(op)
    parent_pointer = _resolve_parent_pointer(tree, op)
    value = _deep_json_value(op["value"])
    parent_val = get_value_at(tree.root_data, parent_pointer)

    if isinstance(parent_val, dict):
        _validate_insert_sibling_options(op, "object")
        key = op.get("key")
        if key is None or not isinstance(key, str):
            raise ValueError("insert into object requires string key")
        before_key = op.get("before_key")
        after_key = op.get("after_key")
        if before_key is not None or after_key is not None:
            insert_into_object_relative(
                tree.root_data,
                parent_pointer,
                key,
                value,
                before_key=before_key if isinstance(before_key, str) else None,
                after_key=after_key if isinstance(after_key, str) else None,
            )
        else:
            insert_into_object(tree.root_data, parent_pointer, key, value)
        return

    if isinstance(parent_val, list):
        _coalesce_insert_pointer_sibling_ids(tree, op)
        _validate_insert_sibling_options(op, "array")
        before_nid = op.get("before_node_id")
        after_nid = op.get("after_node_id")
        idx = op.get("index")
        if before_nid or after_nid:
            insert_idx = _array_insert_index_from_sibling(
                tree,
                before_node_id=str(before_nid) if before_nid else None,
                after_node_id=str(after_nid) if after_nid else None,
            )
            insert_into_array(tree.root_data, parent_pointer, value, insert_idx)
        elif idx is None:
            insert_into_array(tree.root_data, parent_pointer, value, None)
        else:
            if not isinstance(idx, int):
                raise ValueError("insert into array requires integer index when set")
            insert_into_array(tree.root_data, parent_pointer, value, idx)
        return

    raise TypeError("insert parent must be object or array")
