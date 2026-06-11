"""
Marker hide/restore cycle for EditSession valid-tree mutations (C-012).

Denudes the TREE section via FormatHandler.unmark, preserves CHECKSUMS/MAP,
restores markers via handler.mark + NodeIdMap.build with prior_map.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_editor.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    MapSection,
    NodeIdMap,
    NodeIdMapError,
    TreeSections,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from ai_editor.tree.handler_registry import HandlerRegistry

MARKER_CYCLE_ERROR = "MARKER_CYCLE_ERROR"


@dataclass(frozen=True)
class MarkerEditState:
    """Preserved CHECKSUMS and MAP sections during hide/unhide (C-012)."""

    checksums_section: ChecksumsSection
    map_section: MapSection


def denude_marked_tree(
    *,
    source_abs: Path,
    marked_tree: str,
) -> tuple[str, MarkerEditState]:
    """Strip short_id markers from TREE section; preserve CHECKSUMS and MAP."""
    sections = parse_tree_file(marked_tree)
    handler = HandlerRegistry.default_registry().resolve(source_abs)
    denuded = handler.unmark(sections.tree)
    state = MarkerEditState(
        checksums_section=sections.checksums,
        map_section=sections.map,
    )
    return denuded, state


def restore_marked_tree(
    *,
    source_abs: Path,
    denuded_after_mutation: str,
    state: MarkerEditState,
) -> str:
    """Re-embed short_id markers; preserve MAP bytes and UUID4 entries (C-012)."""
    handler = HandlerRegistry.default_registry().resolve(source_abs)
    file_path = source_abs.name
    candidate_marked = handler.mark(denuded_after_mutation)
    parsed_nodes = handler.parse_content(Path(file_path), denuded_after_mutation)
    discovered_nodes: list[DiscoveredNode] = [
        DiscoveredNode(
            marker_short_id=int(node.short_id),
            kind=node.kind,
            content_fingerprint=compute_content_fingerprint(node.content),
            attributes=dict(node.attributes),
        )
        for node in parsed_nodes
    ]
    source_sha256 = state.checksums_section["source_sha256"]
    if not discovered_nodes:
        built_sections = TreeSections(
            checksums=state.checksums_section,
            map=state.map_section,
            tree=candidate_marked,
        )
        return serialize_tree_file(built_sections)
    try:
        built_sections, id_map = NodeIdMap.build(
            tree_marked_text=candidate_marked,
            discovered_nodes=discovered_nodes,
            source_sha256=source_sha256,
            prior_map=state.map_section,
        )
        final_sections = id_map.validate_and_repair(
            tree_marked_text=candidate_marked,
            discovered_nodes=discovered_nodes,
            checksums=built_sections.checksums,
        )
    except NodeIdMapError as exc:
        raise ValueError(f"{MARKER_CYCLE_ERROR}: {exc}") from exc
    return serialize_tree_file(final_sections)
