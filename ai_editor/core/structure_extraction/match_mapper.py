"""
Map grep line matches to structure blocks and preview payloads.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_editor.core.structure_extraction.extractor import (
    extract_structure,
    find_smallest_block_containing_line,
)
from ai_editor.core.structure_extraction.stable_tree import TreeResolutionStats

_UNSTABLE_ID_KEYS = (
    "block_id",
    "block_type",
    "node_ref",
    "selector",
    "preview",
    "name",
    "qualname",
    "start_line",
    "end_line",
)


@dataclass
class EnrichmentCounters:
    enrichment_skipped: int = 0
    enrichment_failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "enrichment_skipped": self.enrichment_skipped,
            "enrichment_failed": self.enrichment_failed,
        }


@dataclass
class EnrichmentPolicy:
    ensure_persisted_tree: bool = True
    stable_ids_required: bool = True


def _clear_unstable_ids(row: Dict[str, Any]) -> None:
    for key in _UNSTABLE_ID_KEYS:
        row.pop(key, None)


def _set_line_only(
    row: Dict[str, Any],
    status: str,
    *,
    grep_source: Optional[str] = None,
) -> None:
    _clear_unstable_ids(row)
    row["enrichment_status"] = status
    if grep_source is not None:
        row["grep_source"] = grep_source


def enrich_match_row(
    row: Dict[str, Any],
    *,
    file_path: str,
    content: str,
    source: str = "disk",
    session_id: Optional[str] = None,
    policy: EnrichmentPolicy | None = None,
    tree_stats: TreeResolutionStats | None = None,
) -> None:
    """Enrich a single grep match row."""
    enrich_matches_for_file(
        [row],
        file_path=file_path,
        content=content,
        source=source,
        session_id=session_id,
        max_rows=1,
        policy=policy,
        tree_stats=tree_stats,
    )


def enrich_matches_for_file(
    matches: List[Dict[str, Any]],
    *,
    file_path: str,
    content: str,
    source: str = "disk",
    session_id: Optional[str] = None,
    max_rows: int,
    policy: EnrichmentPolicy | None = None,
    tree_stats: TreeResolutionStats | None = None,
    counters: EnrichmentCounters | None = None,
    preview_file_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Enrich up to ``max_rows`` matches; return document warnings for caller."""
    policy = policy or EnrichmentPolicy()
    warnings_out: List[Dict[str, Any]] = []
    if max_rows <= 0:
        if counters is not None:
            counters.enrichment_skipped += len(matches)
        for row in matches:
            _set_line_only(row, "skipped_budget", grep_source=source)
        return warnings_out

    document = extract_structure(
        file_path=file_path,
        content=content,
        source=source,
        session_id=session_id,
        include_text=False,
        ensure_persisted_tree=policy.ensure_persisted_tree,
        stable_ids_required=policy.stable_ids_required,
        tree_stats=tree_stats,
        preview_file_path=preview_file_path,
    )
    for w in document.warnings:
        warnings_out.append(
            {"code": w.code, "message": w.message, "file_path": w.file_path}
        )

    stable_ok = document.ids_stable or not policy.stable_ids_required
    if policy.stable_ids_required and not stable_ok:
        if counters is not None:
            counters.enrichment_skipped += min(len(matches), max_rows)
        for i, row in enumerate(matches):
            if i >= max_rows:
                break
            _set_line_only(row, "skipped_tree_not_persisted", grep_source=source)
        return warnings_out

    enriched = 0
    for i, row in enumerate(matches):
        if i >= max_rows:
            if counters is not None:
                counters.enrichment_skipped += 1
            _set_line_only(row, "skipped_budget", grep_source=source)
            continue
        _apply_block_to_row(row, document, int(row["line_number"]), source=source)
        enriched += 1
    if counters is not None and enriched < len(matches):
        counters.enrichment_skipped += len(matches) - enriched
    return warnings_out


def _apply_block_to_row(
    row: Dict[str, Any],
    document: Any,
    line_number: int,
    *,
    source: str,
) -> None:
    block = find_smallest_block_containing_line(document, line_number)
    if block is None or not block.node_ref:
        _set_line_only(row, "skipped_extractor_error", grep_source=source)
        return
    row["block_id"] = block.block_id
    row["block_type"] = block.node_type
    row["node_ref"] = block.node_ref
    row["selector"] = block.path or block.node_ref
    row["name"] = block.name
    row["qualname"] = block.qualname
    row["start_line"] = block.start_line
    row["end_line"] = block.end_line
    row["enrichment_status"] = "enriched"
    row["grep_source"] = source
    if block.preview is not None:
        row["preview"] = block.preview.as_dict()
    if document.session_id:
        row["session_id"] = document.session_id
