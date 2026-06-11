"""
BlockHandler (C-008) — five rendering rules, one per NodeKind (C-004).

Chosen by the block's own NodeKind, not the parent's kind.
A BlockHandler never includes the block's own children's content.
Set is closed under this plan: five rules only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .models import Node, NodeKind


def render_block(node: Node, value_preview_len: int) -> dict[str, Any]:
    """
    Render a Node using the BlockHandler rule for its own NodeKind (C-008).

    Args:
        node: The block node to render.
        value_preview_len: Max length for any inline scalar value or name
                         (from PreviewBudget C-013).

    Returns:
        Compact summary dict. Keys depend on NodeKind:
          scalar    -> {value: str (truncated)}
          lines     -> {line_count: int, first_line: str (truncated)}
          sequence  -> {element_count: int, element_kinds: list[str]}
          mapping   -> {key_count: int, key_names: list[str] (each truncated)}
          tree_node -> {type: str, name: str|None, attributes: dict,
                        child_count: int}
    """
    vpl = value_preview_len
    kind = node.node_kind
    if kind is NodeKind.SCALAR:
        return _render_scalar(node, vpl)
    if kind is NodeKind.LINES:
        return _render_lines(node, vpl)
    if kind is NodeKind.SEQUENCE:
        return _render_sequence(node, vpl)
    if kind is NodeKind.MAPPING:
        return _render_mapping(node, vpl)
    if kind is NodeKind.TREE_NODE:
        return _render_tree_node(node, vpl)
    raise ValueError(f"Unhandled NodeKind: {kind!r}")


def _render_scalar(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 1: truncated value. No children content."""
    value = node.attributes.get("value") or node.name or node.type_label or ""
    return {"value": value[:vpl]}


def _render_lines(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 2: total line count and first line truncated."""
    children = node.children
    first = children[0].attributes.get("value", "") if children else ""
    return {"line_count": len(children), "first_line": first[:vpl]}


def _render_sequence(node: Node, vpl: int) -> dict[str, Any]:  # noqa: ARG001
    """Rule 3: element count and coarse element-kind summary."""
    children = node.children
    kinds = sorted({c.node_kind.value for c in children})
    return {"element_count": len(children), "element_kinds": kinds}


def _render_mapping(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 4: key count, key name list (each truncated), and leaf scalar values.

    Two cases:

    1. The node is a YAML mapping **entry** whose value is a primitive scalar.
       Such nodes carry ``value`` (and ``value_kind``) in their own
       ``attributes`` and have zero children.  We surface the value inline
       so the caller sees it without a separate drill-down call.

    2. The node is a regular mapping (dict root or nested object).  We list
       its children's names and, for any child that itself is a scalar entry
       (``attributes['value']`` present), include the value in ``key_values``
       at the matching index.  Children that are nested mappings or sequences
       get ``None`` at that position.
    """
    attrs = node.attributes or {}
    # Case 1: leaf mapping entry — value already in attributes.
    if "value" in attrs and not node.children:
        val = attrs["value"]
        return {
            "key_count": 0,
            "key_names": [],
            "key_values": [],
            "value": str(val)[:vpl],
            "value_kind": attrs.get("value_kind", "str"),
        }
    # Case 2: regular mapping — enumerate children.
    children = node.children
    keys: list[str] = []
    values: list[str | None] = []
    for c in children:
        keys.append(c.name[:vpl] if c.name else "")
        raw_val = (c.attributes or {}).get("value")
        values.append(str(raw_val)[:vpl] if raw_val is not None else None)
    return {"key_count": len(children), "key_names": keys, "key_values": values}


def _render_tree_node(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 5: type, optional name, attributes, child count.

    When node.attributes carries a 'text' key (pre-rendered by
    PythonNodeRenderer C-022), it is promoted to a top-level 'text'
    field in the summary and excluded from the 'attributes' dict.
    """
    text = node.attributes.get("text") if node.attributes else None
    attrs = {k: v for k, v in (node.attributes or {}).items() if k != "text"}
    preview_children = attrs.pop("tree_preview_child_count", None)
    resolved_child_count = (
        preview_children if isinstance(preview_children, int) else len(node.children)
    )
    summary: dict[str, Any] = {
        "type": (node.type_label or "")[:vpl],
        "name": node.name[:vpl] if node.name else None,
        "attributes": attrs,
        "child_count": resolved_child_count,
    }
    if text is not None:
        summary["text"] = text
    return summary
