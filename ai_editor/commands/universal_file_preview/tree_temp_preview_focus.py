"""
Resolves universal_file_preview drill-down focus for tree-temp Sidecar stable_id (C-009).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import (
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
)

from ai_editor.core.tree_temp.tree_node import TreeNode

from .models import Node, NodeKind

TREE_TEMP_SIDECAR_STABLE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_CONTAINER_TYPES: frozenset[str] = frozenset({"object", "array"})
_SCALAR_TYPES: frozenset[str] = frozenset({"string", "number", "boolean", "null"})


class TreeTempPreviewResolveError(ValueError):
    """stable_id absent from indexed Sidecar-backed tree."""

    ...


EffectiveFocusMode = Literal[
    "root_view", "container_drill_down", "scalar_node_ref_effective_focus"
]


@dataclass(frozen=True)
class TreeTempPreviewFocus:
    """Effective container whose ``children`` form the ordered block list."""

    container: TreeNode
    effective_mode: EffectiveFocusMode
    navigation_context: dict[str, object]


def looks_like_sidecar_stable_id(node_ref: str | None) -> bool:
    """True when ``node_ref`` matches UUID layout used by Sidecar ``stable_id``."""
    if not isinstance(node_ref, str):
        return False
    stripped = node_ref.strip()
    if not stripped:
        return False
    return TREE_TEMP_SIDECAR_STABLE_UUID_RE.fullmatch(stripped) is not None


def _index_forest_parent_maps(
    roots: Iterable[TreeNode],
) -> Tuple[Mapping[str, TreeNode], Mapping[str, Optional[TreeNode]]]:
    by_id: MutableMapping[str, TreeNode] = {}
    parents: MutableMapping[str, Optional[TreeNode]] = {}

    def visit(node: TreeNode, parent: Optional[TreeNode]) -> None:
        by_id[node.stable_id] = node
        parents[node.stable_id] = parent
        if node.children:
            for ch in node.children:
                visit(ch, node)

    for r in roots:
        visit(r, None)

    return by_id, parents


def _ancestor_depth_hint(
    container: TreeNode, parents: Mapping[str, Optional[TreeNode]]
) -> int:
    hops = 0
    cur: Optional[TreeNode] = container
    while cur is not None:
        pid = parents.get(cur.stable_id)
        if pid is None:
            break
        cur = pid
        hops += 1
    return hops


def _synthetic_roots_container(roots: List[TreeNode]) -> TreeNode:
    """
    Synthetic object container wrapping one or more Sidecar roots.

    Used solely for preview block enumeration when ``root_view`` is requested
    (no ``node_ref`` or scalar ref with no qualifying ancestor).
    """

    cid = str(uuid.uuid4())
    return TreeNode(
        stable_id=cid,
        type="object",
        key=None,
        value=None,
        children=list(roots),
        comment_before=None,
        comment_inline=None,
    )


def _root_view_focus(roots: List[TreeNode]) -> TreeTempPreviewFocus:
    if len(roots) == 1 and roots[0].type in _CONTAINER_TYPES:
        return TreeTempPreviewFocus(
            container=roots[0],
            effective_mode="root_view",
            navigation_context={
                "resolved_stable_id": None,
                "effective_focus_stable_id": roots[0].stable_id,
                "depth_hint": 0,
            },
        )
    wrap = _synthetic_roots_container(roots)
    return TreeTempPreviewFocus(
        container=wrap,
        effective_mode="root_view",
        navigation_context={
            "resolved_stable_id": None,
            "effective_focus_stable_id": None,
            "depth_hint": 0,
        },
    )


def resolve_tree_temp_preview_focus(
    *,
    roots: List[TreeNode],
    node_ref: Optional[str],
) -> TreeTempPreviewFocus:
    """
    Return the effective Sidecar-backed container whose children define blocks.

    When ``node_ref`` is falsy after strip (or yields ``root_view`` per policy):
    synthesize one object-shaped container wrapping ``roots``. Its children mirror
    the handler's conceptual root-node children for previews.
    """
    if not roots:
        wrap = TreeNode(
            stable_id=str(uuid.uuid4()),
            type="object",
            key=None,
            value=None,
            children=[],
            comment_before=None,
            comment_inline=None,
        )
        return TreeTempPreviewFocus(
            container=wrap,
            effective_mode="root_view",
            navigation_context={
                "resolved_stable_id": None,
                "effective_focus_stable_id": None,
                "depth_hint": 0,
            },
        )

    trimmed = node_ref.strip() if isinstance(node_ref, str) else ""
    if not trimmed:
        return _root_view_focus(roots)

    by_id, parents = _index_forest_parent_maps(roots)

    resolved = by_id.get(trimmed)
    if resolved is None:
        raise TreeTempPreviewResolveError(
            f"UNKNOWN_STABLE_ID: {trimmed!r} not present in Sidecar-backed tree."
        )

    if resolved.type in _CONTAINER_TYPES:
        dh = _ancestor_depth_hint(resolved, parents)
        return TreeTempPreviewFocus(
            container=resolved,
            effective_mode="container_drill_down",
            navigation_context={
                "resolved_stable_id": trimmed,
                "effective_focus_stable_id": resolved.stable_id,
                "depth_hint": dh,
            },
        )

    if resolved.type not in _SCALAR_TYPES:
        return _root_view_focus(roots)

    cur_scalar: Optional[TreeNode] = resolved
    walk_up_hops = 0
    ancestor: Optional[TreeNode] = None
    while cur_scalar is not None:
        if cur_scalar.type in _CONTAINER_TYPES:
            ancestor = cur_scalar
            break
        nxt_scalar = parents.get(cur_scalar.stable_id)
        if nxt_scalar is None:
            break
        cur_scalar = nxt_scalar
        walk_up_hops += 1

    if ancestor is None:
        return _root_view_focus(roots)

    dh = _ancestor_depth_hint(ancestor, parents) + walk_up_hops

    return TreeTempPreviewFocus(
        container=ancestor,
        effective_mode="scalar_node_ref_effective_focus",
        navigation_context={
            "resolved_stable_id": trimmed,
            "effective_focus_stable_id": ancestor.stable_id,
            "depth_hint": dh,
        },
    )


def tree_temp_preview_children_to_preview_nodes(
    tree_children: List[TreeNode],
) -> List[Node]:
    """
    Map Sidecar TreeNode children to preview ``models.Node`` rows (TREE_NODE).

    ``node_ref`` on each preview node is each child's ``stable_id`` for drill-down.
    """
    out: List[Node] = []
    for tn in tree_children:
        attrs: Dict[str, object] = {
            "tree_preview_child_count": len(tn.children or []),
            "tree_stable_type": tn.type,
        }
        if tn.type == "string" and tn.value is not None:
            attrs["value"] = str(tn.value)
        elif tn.type == "number" and tn.value is not None:
            attrs["value"] = str(tn.value)
        elif tn.type == "boolean":
            attrs["value"] = "true" if tn.value else "false"
        elif tn.type == "null":
            attrs["value"] = "null"
        elif tn.type in _CONTAINER_TYPES:
            attrs["value"] = ""
        else:
            attrs["value"] = ""

        out.append(
            Node(
                node_kind=NodeKind.TREE_NODE,
                node_ref=tn.stable_id,
                type_label=str(tn.type),
                name=tn.key,
                attributes=attrs,
            )
        )

    return out
