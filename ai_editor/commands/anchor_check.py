"""
Anchor verification for line-range replace commands.

An anchor is a short fingerprint that lets the server verify the caller's
line numbers point at the expected content before any write is performed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import libcst as cst

from ..core.cst_tree.tree_sidecar import (
    read_sidecar_payload,
    verify_sidecar_against_source,
)

logger = logging.getLogger(__name__)

_ANCHOR_LEN = 5


def _nonws(s: str, n: int, *, from_end: bool = False) -> str:
    """Return first or last n non-whitespace characters from s."""
    chars = [c for c in s if not c.isspace()]
    selected = chars[-n:] if from_end else chars[:n]
    return "".join(selected)


def compute_text_anchor(
    lines: list[str],
    start_line: int,
    end_line: int,
) -> dict[str, str]:
    """Return anchor_head and anchor_tail for a 1-based inclusive line range."""
    low = max(0, start_line - 1)
    high = max(0, end_line - 1)
    first = lines[low] if low < len(lines) else ""
    last = lines[high] if high < len(lines) else ""
    return {
        "anchor_head": _nonws(first, _ANCHOR_LEN),
        "anchor_tail": _nonws(last, _ANCHOR_LEN, from_end=True),
    }


class AnchorMismatch(Exception):
    """Raised when an anchor check fails."""

    def __init__(self, message: str, details: dict[str, Any]):
        super().__init__(message)
        self.details = details


def check_text_anchor(
    all_lines: list[str],
    start_line: int,
    end_line: int,
    anchor_head: Optional[str],
    anchor_tail: Optional[str],
) -> None:
    """
    Verify text anchor values against actual file lines.

    The command layer enforces that anchor_head and anchor_tail are supplied
    together. This helper remains tolerant so existing internal callers can
    validate one side when needed.
    """
    if anchor_head is None and anchor_tail is None:
        return

    actual = compute_text_anchor(all_lines, start_line, end_line)

    if anchor_head is not None and actual["anchor_head"] != anchor_head:
        raise AnchorMismatch(
            f"anchor_head mismatch at lines {start_line}-{end_line}: "
            f"expected {anchor_head!r}, got {actual['anchor_head']!r}",
            {
                "start_line": start_line,
                "end_line": end_line,
                "anchor_field": "anchor_head",
                "expected": anchor_head,
                "actual": actual["anchor_head"],
            },
        )

    if anchor_tail is not None and actual["anchor_tail"] != anchor_tail:
        raise AnchorMismatch(
            f"anchor_tail mismatch at lines {start_line}-{end_line}: "
            f"expected {anchor_tail!r}, got {actual['anchor_tail']!r}",
            {
                "start_line": start_line,
                "end_line": end_line,
                "anchor_field": "anchor_tail",
                "expected": anchor_tail,
                "actual": actual["anchor_tail"],
            },
        )


def _best_sidecar_node_at_line(
    metadata_map: dict[str, Any],
    start_line: int,
    metadata_node_order: Optional[list[Any]] = None,
) -> Optional[dict[str, Any]]:
    ordered_values: list[Any] = []
    seen_keys: set[str] = set()
    if metadata_node_order:
        for raw_key in metadata_node_order:
            key = str(raw_key)
            if key in metadata_map:
                ordered_values.append(metadata_map[key])
                seen_keys.add(key)
    ordered_values.extend(
        raw for key, raw in metadata_map.items() if str(key) not in seen_keys
    )

    candidates: list[dict[str, Any]] = []
    for raw in ordered_values:
        if not isinstance(raw, dict):
            continue
        try:
            node_start = int(raw["start_line"])
            node_end = int(raw["end_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if node_start <= start_line <= node_end:
            candidates.append(raw)

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda item: (
            int(item["end_line"]) - int(item["start_line"]),
            int(item["start_line"]),
        ),
    )


def check_cst_anchor(
    absolute_path: Path,
    start_line: int,
    anchor_node_id: str,
) -> None:
    """
    Verify that the CST node at start_line has the given stable_id.

    When the sidecar is absent or unusable, the check degrades gracefully with a
    warning to preserve compatibility with files that have not been CST-loaded.
    """
    try:
        source = absolute_path.read_text(encoding="utf-8", errors="replace")
        cst.parse_module(source)
    except Exception as e:
        raise AnchorMismatch(
            f"CST parse failed during anchor check: {e}",
            {
                "start_line": start_line,
                "anchor_node_id": anchor_node_id,
                "parse_error": str(e),
            },
        ) from e

    payload = read_sidecar_payload(absolute_path)
    if payload is None:
        logger.warning(
            "anchor_node_id check: sidecar not found for %s, skipping stable_id verify",
            absolute_path,
        )
        return

    if not verify_sidecar_against_source(source, payload):
        logger.warning(
            "anchor_node_id check: sidecar is stale for %s, skipping stable_id verify",
            absolute_path,
        )
        return

    metadata_map = payload.get("metadata_map")
    if not isinstance(metadata_map, dict):
        logger.warning(
            "anchor_node_id check: malformed sidecar for %s, skipping stable_id verify",
            absolute_path,
        )
        return

    order_raw = payload.get("metadata_node_order")
    metadata_node_order = order_raw if isinstance(order_raw, list) else None
    node = _best_sidecar_node_at_line(metadata_map, start_line, metadata_node_order)
    if node is None:
        raise AnchorMismatch(
            f"No CST node found at line {start_line}",
            {
                "start_line": start_line,
                "anchor_field": "anchor_node_id",
                "expected": anchor_node_id,
                "actual": None,
            },
        )

    found_stable_id = node.get("stable_id")
    if not isinstance(found_stable_id, str):
        logger.warning(
            "anchor_node_id check: sidecar entry has no stable_id for %s line %d",
            absolute_path,
            start_line,
        )
        return

    if found_stable_id != anchor_node_id:
        raise AnchorMismatch(
            f"anchor_node_id mismatch at line {start_line}: "
            f"expected {anchor_node_id!r}, got {found_stable_id!r}",
            {
                "start_line": start_line,
                "anchor_field": "anchor_node_id",
                "expected": anchor_node_id,
                "actual": found_stable_id,
            },
        )
