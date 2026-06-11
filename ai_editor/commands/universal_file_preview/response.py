"""
Response envelope assembly for universal_file_preview.

Builds the uniform top-level ResponseEnvelope (C-012) returned by
UniversalFilePreviewCommand on every successful request.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .models import NavigationResult


def build_envelope(
    navigation_result: NavigationResult,
    raw_selector: str | list | None,
    session_origin: str | None,
) -> dict[str, Any]:
    """
    Build the ResponseEnvelope (C-012) from a NavigationResult.

    The envelope shape is constant regardless of NodeKind and selector form.
    Fields always present:
      focus            - dict with node_kind, node_ref, type, name, attributes;
                       optional focus.text when pre-rendered text exists (C-022)
      selector_applied - normalised selector or None
      total_blocks     - int: total count of blocks in focus block set
      blocks           - list of rendered block dicts (each may include text when set)
    Field present only when session_origin == 'command_created' and
    navigation_result.tree_id is not None:
      tree_id          - str: UUID for reuse by the caller

    Args:
        navigation_result: Output of the NavigationProcedure.
        raw_selector: Original selector value from the caller (for echo-back).
        session_origin: One of 'caller_owned', 'command_created', 'none', or None.

    Returns:
        Dict conforming to ResponseEnvelope (C-012).
    """
    focus = navigation_result.focus_node
    focus_text = focus.attributes.get("text") if focus.attributes else None
    node_ref_out: str | int = focus.node_ref
    if navigation_result.short_id_refs and focus.node_ref.isdigit():
        node_ref_out = int(focus.node_ref)
    focus_dict = {
        "node_kind": focus.node_kind.value,
        "node_ref": node_ref_out,
        "type": focus.type_label,
        "name": focus.name,
        "attributes": {
            k: v for k, v in (focus.attributes or {}).items() if k != "text"
        },
    }
    if focus.is_invalid:
        focus_dict["is_invalid"] = True
    if focus_text is not None:
        focus_dict["text"] = focus_text

    # Normalise selector for echo-back: keep as-is if already str or list;
    # set to None if raw_selector is None.
    selector_applied: str | list | None = raw_selector

    blocks_list = []
    for b in navigation_result.selected_blocks:
        block_ref: str | int = b.node_ref
        if navigation_result.short_id_refs and b.node_ref.isdigit():
            block_ref = int(b.node_ref)
        block_dict: dict[str, Any] = {
            "node_kind": b.node_kind.value,
            "node_ref": block_ref,
            "summary": b.summary,
        }
        if b.text is not None:
            block_dict["text"] = b.text
        blocks_list.append(block_dict)

    envelope: dict[str, Any] = {
        "focus": focus_dict,
        "selector_applied": selector_applied,
        "total_blocks": navigation_result.total_blocks,
        "blocks": blocks_list,
    }

    if session_origin == "command_created" and navigation_result.tree_id is not None:
        envelope["tree_id"] = navigation_result.tree_id

    return envelope
