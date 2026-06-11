"""
Unified diff helpers for text-like before/after content.

Format-agnostic: callers supply raw text and path labels only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Tuple


def unified_diff_text(
    before: str,
    after: str,
    *,
    before_label: str = "before",
    after_label: str = "after",
    context_lines: int = 3,
) -> str:
    """Return unified diff string (no file I/O; labels appear in diff headers)."""
    bl = before.splitlines(keepends=True)
    al = after.splitlines(keepends=True)
    diff = difflib.unified_diff(
        bl,
        al,
        fromfile=before_label,
        tofile=after_label,
        n=max(0, context_lines),
    )
    return "".join(diff)


def line_delta_ranges(
    before_lines: List[str],
    after_lines: List[str],
) -> List[Tuple[int, int]]:
    """
    Changed line spans in **after** content (1-based inclusive) from SequenceMatcher.

    ``delete`` hunks in the source become empty spans in ``after`` and are omitted.
    """
    sm = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    spans: List[Tuple[int, int]] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if j2 > j1:
            spans.append((j1 + 1, j2))
    return spans


def merge_adjacent_changed_ranges(
    ranges: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Merge overlapping or touching (end + 1 >= start) 1-based spans."""
    if not ranges:
        return []
    sorted_r = sorted(ranges, key=lambda t: (t[0], t[1]))
    out: List[Tuple[int, int]] = [sorted_r[0]]
    for s, e in sorted_r[1:]:
        ps, pe = out[-1]
        if s <= pe + 1:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def changed_line_ranges_for_text(
    before_text: str, after_text: str
) -> List[Tuple[int, int]]:
    """
    Stable 1-based inclusive line ranges in **after** text that differ from **before**.
    """
    b_lines = before_text.splitlines(keepends=False)
    a_lines = after_text.splitlines(keepends=False)
    raw = line_delta_ranges(b_lines, a_lines)
    return merge_adjacent_changed_ranges(raw)


def diff_data_for_text_mutation(
    before_text: str,
    after_text: str,
    *,
    include_diff: bool,
    before_label: str,
    after_label: str,
    context_lines: int = 3,
) -> Dict[str, Any]:
    """
    Single code path for dry-run and apply responses when attaching diff metadata.

    Returns stable keys:

    - ``diff``: unified diff string, or ``""`` when ``include_diff`` is false.
    - ``changed_line_ranges``: list of ``[start_line, end_line]`` (1-based inclusive
      in **after** text); empty when ``include_diff`` is false or there is no change
      in the after text lines.
    """
    if not include_diff:
        return {
            "diff": "",
            "changed_line_ranges": [],
        }

    ranges = changed_line_ranges_for_text(before_text, after_text)
    diff_str = unified_diff_text(
        before_text,
        after_text,
        before_label=before_label,
        after_label=after_label,
        context_lines=context_lines,
    )
    return {
        "diff": diff_str,
        "changed_line_ranges": [[a, b] for a, b in ranges],
    }
