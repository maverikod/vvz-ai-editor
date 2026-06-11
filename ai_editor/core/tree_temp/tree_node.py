"""TreeNode entity for tree-temp Sidecar (JSON/YAML); implements persistence-facing shape for C-001.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, cast

TreeNodeType = Literal["object", "array", "string", "number", "boolean", "null"]
TREE_NODE_TYPES: frozenset[str] = frozenset(
    {"object", "array", "string", "number", "boolean", "null"}
)


def _optional_str(field_name: str, raw: object) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} must be str or null when present")
    return raw


def _is_uuid_v4_string(value: str) -> bool:
    """Return True if value parses as a UUID with version 4."""
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


@dataclass
class TreeNode:
    """One structured-tree node with Sidecar-stable identity (C-001)."""

    stable_id: str
    type: TreeNodeType
    key: Optional[str] = None
    value: Any = None
    children: Optional[List["TreeNode"]] = None
    comment_before: Optional[str] = None
    comment_inline: Optional[str] = None


def validate_node_constraints(node: TreeNode) -> None:
    """Validate TreeNode fields against C-001 type discriminator rules; raise ValueError on violation."""
    if node.type not in TREE_NODE_TYPES:
        raise ValueError(f"invalid TreeNode.type: {node.type!r}")
    if (
        not isinstance(node.stable_id, str)
        or not node.stable_id.strip()
        or not _is_uuid_v4_string(node.stable_id)
    ):
        raise ValueError("stable_id must be a UUID version 4 string")
    if node.type in ("object", "array"):
        if node.value is not None:
            raise ValueError("container nodes must not set value")
        if node.children is None:
            raise ValueError("container nodes require children list")
        if not isinstance(node.children, list):
            raise ValueError("children must be a list")
        for child in node.children:
            if not isinstance(child, TreeNode):
                raise ValueError("children must be TreeNode instances")
    if node.type == "string":
        if node.children is not None:
            raise ValueError("scalar string node must not set children")
        if not isinstance(node.value, str):
            raise ValueError("string node value must be str")
    elif node.type == "number":
        if node.children is not None:
            raise ValueError("scalar number node must not set children")
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("number node value must be int or float (not bool)")
    elif node.type == "boolean":
        if node.children is not None:
            raise ValueError("scalar boolean node must not set children")
        if not isinstance(node.value, bool):
            raise ValueError("boolean node value must be bool")
    elif node.type == "null":
        if node.children is not None:
            raise ValueError("null node must not set children")
        if node.value is not None:
            raise ValueError("null node value must be Python None")
    if node.comment_before is not None and not isinstance(node.comment_before, str):
        raise ValueError("comment_before must be str or None")
    if node.comment_inline is not None and not isinstance(node.comment_inline, str):
        raise ValueError("comment_inline must be str or None")
    if node.key is not None and not isinstance(node.key, str):
        raise ValueError("key must be str or None")


def tree_node_to_json_dict(node: TreeNode) -> Dict[str, Any]:
    """Serialize TreeNode to a JSON-object-compatible dict for Sidecar root arrays (recursive)."""
    validate_node_constraints(node)
    out: Dict[str, Any] = {"stable_id": node.stable_id, "type": node.type}
    if node.key is not None:
        out["key"] = node.key
    if node.comment_before is not None:
        out["comment_before"] = node.comment_before
    if node.comment_inline is not None:
        out["comment_inline"] = node.comment_inline
    if node.type in ("object", "array"):
        out["children"] = [
            tree_node_to_json_dict(ch) for ch in cast(List[TreeNode], node.children)
        ]
    elif node.type in ("string", "number", "boolean", "null"):
        out["value"] = node.value
    return out


def tree_node_from_json_dict(data: Dict[str, Any]) -> TreeNode:
    """Deserialize dict from Sidecar JSON into TreeNode; strict keys for node objects."""
    if not isinstance(data, dict):
        raise TypeError("TreeNode JSON must be an object")
    allowed = {
        "stable_id",
        "type",
        "key",
        "value",
        "children",
        "comment_before",
        "comment_inline",
    }
    extras = set(data.keys()) - allowed
    if extras:
        raise ValueError("unexpected keys on TreeNode object: " + repr(sorted(extras)))
    sid_raw = data.get("stable_id")
    if not isinstance(sid_raw, str):
        raise ValueError("missing or invalid stable_id")
    nodetype_raw = data.get("type")
    if not isinstance(nodetype_raw, str):
        raise ValueError("missing or invalid type")
    if nodetype_raw not in TREE_NODE_TYPES:
        raise ValueError(f"invalid TreeNode.type: {nodetype_raw!r}")

    nodetype: TreeNodeType = cast(TreeNodeType, nodetype_raw)
    key_opt = None if "key" not in data else _optional_str("key", data["key"])
    cb = (
        None
        if "comment_before" not in data
        else _optional_str("comment_before", data["comment_before"])
    )
    ci = (
        None
        if "comment_inline" not in data
        else _optional_str("comment_inline", data["comment_inline"])
    )

    if nodetype in ("object", "array"):
        if "value" in data and data["value"] is not None:
            raise ValueError("container node must not carry non-null value")
        ch_raw = data.get("children")
        if not isinstance(ch_raw, list):
            raise ValueError("container node requires children list")
        children = [tree_node_from_json_dict(item) for item in ch_raw]
        return TreeNode(
            stable_id=sid_raw,
            type=nodetype,
            key=key_opt,
            value=None,
            children=children,
            comment_before=cb,
            comment_inline=ci,
        )

    if "children" in data and data["children"] is not None:
        raise ValueError("scalar node must not set children")

    if "value" not in data:
        raise ValueError("scalar node requires value key")

    val = data["value"]
    value: Any
    if nodetype == "string":
        if not isinstance(val, str):
            raise ValueError("string node value must be str")
        value = val
    elif nodetype == "number":
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("number node value must be int or float (not bool)")
        value = val
    elif nodetype == "boolean":
        if not isinstance(val, bool):
            raise ValueError("boolean node value must be bool")
        value = val
    elif nodetype == "null":
        if val is not None:
            raise ValueError("null node value must be Python None")
        value = None
    else:
        raise ValueError(f"invalid TreeNode.type: {nodetype_raw!r}")

    return TreeNode(
        stable_id=sid_raw,
        type=nodetype,
        key=key_opt,
        value=value,
        children=None,
        comment_before=cb,
        comment_inline=ci,
    )


def new_uuid_str() -> str:
    """Return a canonical UUID version 4 string for TreeNode.stable_id."""
    return str(uuid.uuid4())


def kind_as_str(node: TreeNode) -> str:
    """Return the C-001 type discriminator as a lowercase string."""
    return str(node.type)


def validate_tree_instance(node: TreeNode, *, member_of_object: bool) -> None:
    """Validate a TreeNode subtree using JSON round-trip shape rules (C-001)."""
    from ai_editor.core.tree_temp.json_source_serializer import validate_tree_json

    try:
        validate_tree_json(node, object_member=member_of_object)
    except ValueError as exc:
        raise ValueError(f"TreeNode_contract: {exc}") from exc
